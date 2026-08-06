#!/usr/bin/env python3
"""Optimize a skill description: measure, decide, propose, repeat.

Three things distinguish this from a naive optimization loop, and all three exist
because the naive version was measured producing confident nonsense.

1. It selects on the **aggregate positive trigger rate**, not per-query pass/fail.
   Discretizing a rate into a checkmark at a 0.5 threshold turns run-to-run
   variance into a verdict. Measured 2026-08-06 on `prompt-design`: two candidate
   descriptions scored 16/20 and 14/20 while their true rates were identical to
   three decimal places.

2. It can return **inconclusive**. A difference smaller than the sample size can
   resolve is not a small win, it is no information. Adopting the higher number
   anyway is what turns an optimization loop into a random walk.

3. It **refuses to start** when the configuration cannot detect an effect worth
   acting on, and says what it would cost to fix that. At the old default of 3
   runs per query over 10 positives, two descriptions had to differ by 25
   percentage points before the difference was readable.

Cheap smoke test (~30 sessions, and `inconclusive` is the correct answer):

    python -m scripts.run_loop --eval-set <path> --skill-path <path> \\
      --runs-per-query 3 --max-iterations 1 --force --yes
"""

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

from scripts import stats
from scripts.generate_report import generate_markdown
from scripts.propose import ProposeError, improve_description
from scripts.run_eval import (find_installed, find_project_root,
                             isolation_settings, plugin_keys_for, run_eval)
from scripts.utils import parse_skill_md


# --------------------------------------------------------------------------
# Preflight
# --------------------------------------------------------------------------

def preflight(
    skill_name: str,
    mode: str,
    n_positives: int,
    runs_per_query: int,
    min_effect: float,
    max_iterations: int,
    force: bool,
    assume_yes: bool,
    out=sys.stderr,
) -> None:
    """Report power and cost before spending anything. Exits if not viable."""
    n_obs = n_positives * runs_per_query
    detectable = stats.mde(n_obs)
    sessions_per_iter = n_obs  # positives dominate; negatives add on top

    print(f"Skill:       {skill_name}", file=out)
    print(f"Mode:        {mode}", file=out)

    installed = find_installed(skill_name)
    if installed and mode == "probe":
        keys = plugin_keys_for(skill_name)
        unmanaged = [path for path, key in installed if not key]
        if keys:
            print(f"Isolation:   '{skill_name}' is installed; hiding "
                  f"{', '.join(keys)} from each run\n"
                  f"             via --settings (this process only -- your "
                  f"environment is untouched).", file=out)
        if unmanaged:
            print(f"\nWARNING: '{skill_name}' is also installed outside any plugin:", file=out)
            for path in unmanaged[:3]:
                print(f"           {path}", file=out)
            print("         Settings cannot disable that copy. Move it aside or "
                  "expect contaminated runs.\n", file=out)

    print(f"Positives:   {n_positives} queries x {runs_per_query} runs "
          f"= {n_obs} observations per arm", file=out)
    print(f"Detectable:  {detectable:.3f} difference (95% CI)", file=out)

    if detectable > min_effect:
        needed = stats.runs_needed(min_effect)
        runs_needed_per_query = -(-needed // n_positives)  # ceil
        msg = (
            f"\nThis configuration cannot detect a {min_effect:.3f} difference.\n"
            f"It would take {runs_needed_per_query} runs per query "
            f"({runs_needed_per_query * n_positives} sessions per arm) to get there,\n"
            f"or raise --min-effect to {detectable:.3f} to accept a coarser answer."
        )
        if not force:
            print(msg, file=out)
            print("\nAborting. Pass --force to run anyway.", file=out)
            sys.exit(2)
        print(msg + "\n\n--force given; continuing. Expect 'inconclusive'.", file=out)
    else:
        print(f"             (<= --min-effect {min_effect:.3f})  OK", file=out)

    print(f"Budget:      ~{sessions_per_iter} sessions per iteration, "
          f"up to {max_iterations} iterations = ~{sessions_per_iter * max_iterations} sessions",
          file=out)

    if assume_yes:
        return
    if not sys.stdin.isatty():
        print("\nNot a terminal and --yes not given; aborting rather than "
              "spending sessions unattended.", file=out)
        sys.exit(2)
    if input("\nProceed? [y/N] ").strip().lower() not in ("y", "yes"):
        print("Aborted.", file=out)
        sys.exit(1)


# --------------------------------------------------------------------------
# Loop
# --------------------------------------------------------------------------

def split_eval_set(eval_set: list[dict], holdout: float, seed: int = 42):
    """Split into train and test, stratified by should_trigger."""
    rng = random.Random(seed)
    trigger = [e for e in eval_set if e["should_trigger"]]
    no_trigger = [e for e in eval_set if not e["should_trigger"]]
    rng.shuffle(trigger)
    rng.shuffle(no_trigger)
    n_t = max(1, int(len(trigger) * holdout))
    n_n = max(1, int(len(no_trigger) * holdout))
    return trigger[n_t:] + no_trigger[n_n:], trigger[:n_t] + no_trigger[:n_n]


def _arm(summary: dict) -> tuple[float, int]:
    return summary["positive_rate"], summary["positive_observations"]


def run_loop(
    eval_set: list[dict],
    skill_path: Path,
    description_override: str | None,
    num_workers: int,
    timeout: int,
    max_iterations: int,
    runs_per_query: int,
    min_effect: float,
    patience: int,
    holdout: float,
    model: str | None,
    mode: str,
    verbose: bool,
    report_path: Path | None = None,
    log_dir: Path | None = None,
) -> dict:
    project_root = find_project_root()
    name, original_description, content = parse_skill_md(skill_path)
    current_description = description_override or original_description

    if holdout > 0:
        train_set, test_set = split_eval_set(eval_set, holdout)
    else:
        train_set, test_set = eval_set, []

    history: list[dict] = []
    incumbent: tuple[float, int] | None = None
    incumbent_description = current_description
    consecutive_flat = 0
    exit_reason = "unknown"
    sessions = 0

    for iteration in range(0, max_iterations + 1):
        if verbose:
            print(f"\n{'=' * 62}\nIteration {iteration}"
                  f"{' (baseline)' if iteration == 0 else ''}\n"
                  f"Description: {current_description[:160]}\n{'=' * 62}",
                  file=sys.stderr)

        t0 = time.time()
        measured = run_eval(
            eval_set=train_set + test_set,
            skill_name=name,
            description=current_description,
            num_workers=num_workers,
            timeout=timeout,
            project_root=project_root,
            runs_per_query=runs_per_query,
            model=model,
            mode=mode,
            isolate=isolation_settings(name) if mode == "probe" else None,
        )
        elapsed = time.time() - t0
        summary = measured["summary"]
        sessions += sum(r["runs"] + r["contaminated"] for r in measured["results"])

        # A probe the installed copy keeps winning is not measuring the
        # candidate. Stop rather than iterate on nothing.
        contaminated = summary["contaminated_runs"]
        if contaminated > 0.25 * max(sessions, 1) and mode == "probe":
            raise SystemExit(
                f"Aborting: {contaminated} runs were won by the installed '{name}' "
                f"skill rather than the probe, so the candidate was never measured. "
                f"Disable the plugin or use --mode live."
            )

        arm = _arm(summary)
        if incumbent is None:
            verdict, delta, adopted = "incumbent", None, True
            incumbent, incumbent_description = arm, current_description
        else:
            cmp = stats.compare(incumbent, arm)
            verdict, delta = cmp["verdict"], cmp["delta"]
            adopted = verdict == "improved"
            if adopted:
                incumbent, incumbent_description = arm, current_description
                consecutive_flat = 0
            else:
                consecutive_flat += 1

        lo, hi = summary["positive_ci"]
        history.append({
            "iteration": iteration,
            "description": current_description,
            "positive_rate": summary["positive_rate"],
            "positive_observations": summary["positive_observations"],
            "positive_ci": [lo, hi],
            "negative_rate": summary["negative_rate"],
            "mde": summary["mde"],
            "contaminated_runs": contaminated,
            "verdict": verdict,
            "delta": delta,
            "adopted": adopted,
            "results": measured["results"],
        })

        if verbose:
            d = f"{delta:+.3f}" if delta is not None else "  —  "
            print(f"  positive rate {summary['positive_rate']:.3f} [{lo:.3f}-{hi:.3f}]"
                  f"  delta {d}  MDE {summary['mde']:.3f}"
                  f"  -> {verdict.upper()}  ({elapsed:.0f}s)", file=sys.stderr)
            if summary["negative_rate"]:
                print(f"  over-triggering: {summary['negative_rate']:.3f}", file=sys.stderr)

        if report_path:
            report_path.write_text(generate_markdown(
                _output(history, original_description, incumbent_description,
                        incumbent, "in progress", len(history), sessions,
                        mode, runs_per_query, min_effect),
                skill_name=name))

        if consecutive_flat >= patience:
            exit_reason = f"no detectable improvement in {patience} consecutive iterations"
            break
        if iteration == max_iterations:
            exit_reason = f"max_iterations ({max_iterations})"
            break

        try:
            current_description = improve_description(
                skill_name=name,
                skill_content=content,
                current_description=incumbent_description,
                eval_results=measured,
                history=[{k: v for k, v in h.items() if k != "results"} for h in history],
                model=model,
                log_dir=log_dir,
                iteration=iteration + 1,
            )
            sessions += 1
        except ProposeError as e:
            exit_reason = f"proposal failed: {e}"
            break

    return _output(history, original_description, incumbent_description, incumbent,
                   exit_reason, len(history), sessions, mode, runs_per_query, min_effect)


def _output(history, original, best_desc, best_arm, exit_reason,
            iterations, sessions, mode, runs_per_query, min_effect) -> dict:
    return {
        "exit_reason": exit_reason,
        "mode": mode,
        "runs_per_query": runs_per_query,
        "min_effect": min_effect,
        "original_description": original,
        "best_description": best_desc,
        "best_positive_rate": best_arm[0] if best_arm else None,
        "best_observations": best_arm[1] if best_arm else None,
        "iterations_run": iterations,
        "sessions_spent": sessions,
        "history": history,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Optimize a skill description")
    parser.add_argument("--eval-set", required=True)
    parser.add_argument("--skill-path", required=True)
    parser.add_argument("--description", default=None, help="Override starting description")
    parser.add_argument("--mode", choices=["live", "probe"], default="probe",
                        help="probe (default) measures candidate descriptions; live can only "
                             "measure the description the skill already ships with")
    parser.add_argument("--num-workers", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--runs-per-query", type=int, default=20,
                        help="Was 3, which cannot separate two descriptions (MDE 0.253)")
    parser.add_argument("--min-effect", type=float, default=0.10,
                        help="Smallest difference worth detecting; preflight aborts if "
                             "the configuration cannot resolve it")
    parser.add_argument("--patience", type=int, default=2,
                        help="Stop after N consecutive iterations with no detectable gain")
    parser.add_argument("--holdout", type=float, default=0.0,
                        help="Fraction held out for testing (0 disables)")
    parser.add_argument("--model", default=None)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--report", default="auto",
                        help="Markdown report path; 'auto' uses --results-dir, 'none' disables")
    parser.add_argument("--results-dir", default=None)
    parser.add_argument("--force", action="store_true", help="Run even if underpowered")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    args = parser.parse_args()

    eval_set = json.loads(Path(args.eval_set).read_text())
    skill_path = Path(args.skill_path)
    if not (skill_path / "SKILL.md").exists():
        print(f"Error: No SKILL.md found at {skill_path}", file=sys.stderr)
        sys.exit(1)

    name, _, _ = parse_skill_md(skill_path)
    n_positives = sum(1 for e in eval_set if e["should_trigger"])
    if not n_positives:
        print("Error: eval set has no should_trigger queries to optimize against.",
              file=sys.stderr)
        sys.exit(1)

    # Live mode answers the installed skill, so it cannot see a candidate
    # description at all. Iterating in live mode would propose new wording and
    # then measure the shipped wording again, reporting 'inconclusive' forever
    # for a reason that has nothing to do with the candidates.
    if args.mode == "live" and args.max_iterations > 0:
        print("Note: --mode live measures the description the skill already ships "
              "with;\n      candidates are not installed, so it cannot evaluate "
              "them. Measuring\n      the baseline once and stopping. Use --mode "
              "probe to optimize.\n", file=sys.stderr)
        args.max_iterations = 0

    preflight(name, args.mode, n_positives, args.runs_per_query, args.min_effect,
              args.max_iterations, args.force, args.yes)

    results_dir = None
    if args.results_dir:
        results_dir = Path(args.results_dir) / time.strftime("%Y-%m-%d_%H%M%S")
        results_dir.mkdir(parents=True, exist_ok=True)

    if args.report == "none":
        report_path = None
    elif args.report == "auto":
        report_path = results_dir / "report.md" if results_dir else None
    else:
        report_path = Path(args.report)

    output = run_loop(
        eval_set=eval_set,
        skill_path=skill_path,
        description_override=args.description,
        num_workers=args.num_workers,
        timeout=args.timeout,
        max_iterations=args.max_iterations,
        runs_per_query=args.runs_per_query,
        min_effect=args.min_effect,
        patience=args.patience,
        holdout=args.holdout,
        model=args.model,
        mode=args.mode,
        verbose=args.verbose,
        report_path=report_path,
        log_dir=results_dir / "logs" if results_dir else None,
    )

    json_output = json.dumps(output, indent=2)
    print(json_output)
    if results_dir:
        (results_dir / "results.json").write_text(json_output)
    if report_path:
        report_path.write_text(generate_markdown(output, skill_name=name))
        print(f"\nReport: {report_path}", file=sys.stderr)

    print(f"\nExit: {output['exit_reason']}", file=sys.stderr)
    print(f"Sessions spent: {output['sessions_spent']}", file=sys.stderr)
    if output["best_positive_rate"] is not None:
        print(f"Best positive rate: {output['best_positive_rate']:.3f}", file=sys.stderr)


if __name__ == "__main__":
    main()
