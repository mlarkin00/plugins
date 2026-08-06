#!/usr/bin/env python3
"""Render a description-optimization run as markdown.

Previously this emitted a self-contained HTML page which `run_loop.py` wrote to a
temp file, gave a 5-second auto-refresh meta tag, and opened in a browser. That
serves someone watching a browser tab through a long run; in practice the report
was never viewed. Markdown is readable over SSH, diffable between runs, greppable,
and commits next to the results JSON.

The file is rewritten after every iteration, so a long run can still be watched
with `cat`, `tail -f`, or an editor that reloads.

    python -m scripts.generate_report results.json > report.md
"""

import argparse
import json
import sys
from pathlib import Path

VERDICT_NOTE = {
    "improved": "cleared the detection floor",
    "inconclusive": "inside the noise floor — no information",
    "worse": "measurably worse",
    "incumbent": "baseline",
}


def _fmt(x, spec=".3f", dash="—"):
    return dash if x is None else format(x, spec)


def _iterations_table(history: list[dict]) -> str:
    rows = [
        "| # | Positive rate | 95% CI | Δ vs incumbent | MDE | Verdict |",
        "|--:|--------------:|:-------|---------------:|----:|:--------|",
    ]
    for h in history:
        lo, hi = h.get("positive_ci") or (None, None)
        ci = f"{_fmt(lo)}–{_fmt(hi)}" if lo is not None else "—"
        verdict = h.get("verdict", "")
        cell = f"**{verdict}**" if verdict == "improved" else verdict
        rows.append(
            f"| {h['iteration']} | {_fmt(h.get('positive_rate'))} | {ci} "
            f"| {_fmt(h.get('delta'), '+.3f')} | {_fmt(h.get('mde'))} | {cell} |"
        )
    return "\n".join(rows)


def _is_self(fired: str, skill_name: str) -> bool:
    """Whether a fired name refers to the skill under test.

    Three forms count as itself and must never appear as a competitor: the bare
    name, the plugin-qualified form (`active-skills:prompt-design`), and the
    throwaway probe (`prompt-design-skill-0897f105`) that probe mode injects to
    carry the candidate description. Listing the probe as "fired instead" would
    label every successful probe trigger as a loss.
    """
    if not fired or not skill_name:
        return False
    return (
        fired == skill_name
        or fired.endswith(f":{skill_name}")
        or fired.startswith(f"{skill_name}-skill-")
        or f":{skill_name}-skill-" in fired
    )


def _per_query_table(entry: dict, skill_name: str = "", limit: int = 40) -> str:
    positives = [r for r in entry.get("results", []) if r["should_trigger"]]
    if not positives:
        return "_No positive queries in this run._"

    rows = [
        "| Query | Rate | Fired instead |",
        "|:------|-----:|:--------------|",
    ]
    for r in sorted(positives, key=lambda r: r["trigger_rate"])[:limit]:
        # Only name *other* skills. A low rate because a competitor won is a
        # boundary problem; a low rate because nothing fired is a coverage
        # problem. They need opposite fixes, so the distinction has to survive.
        others = sorted({n for n in r.get("fired", []) if n and not _is_self(n, skill_name)})
        losing_to = ", ".join(f"`{n}`" for n in others) if others else "—"
        query = r["query"].replace("|", "\\|")
        if len(query) > 80:
            query = query[:77] + "…"
        rows.append(f"| {query} | {r['trigger_rate']:.2f} | {losing_to} |")
    return "\n".join(rows)


def generate_markdown(data: dict, skill_name: str = "") -> str:
    history = data.get("history", [])
    name = skill_name or data.get("skill_name", "skill")
    runs = data.get("runs_per_query")
    mode = data.get("mode", "?")
    n_pos = history[0].get("positive_observations") if history else None
    n_queries = (
        sum(1 for r in history[0].get("results", []) if r["should_trigger"])
        if history else 0
    )

    out = [f"# Description optimization — {name}", ""]

    meta = [f"Mode `{mode}`"]
    # Only state the multiplication when it actually holds. `results` can be
    # absent or truncated in a stored file, and an arithmetic claim that does not
    # add up is worse than no claim.
    if n_queries and runs and n_pos and n_queries * runs == n_pos:
        meta.append(f"{n_queries} positives × {runs} runs = {n_pos} observations")
    elif n_pos:
        meta.append(f"{n_pos} positive observations")
    if history:
        meta.append(f"MDE {_fmt(history[0].get('mde'))}")
    if data.get("min_effect") is not None:
        meta.append(f"target {data['min_effect']:.3f}")
    out += [" · ".join(meta), ""]
    out += [f"Exit: **{data.get('exit_reason', 'unknown')}** · "
            f"{data.get('sessions_spent', '?')} sessions spent", ""]

    # Verdict
    adopted = [h for h in history if h.get("verdict") == "improved"]
    out += ["## Verdict", ""]
    if not history:
        out += ["No iterations ran.", ""]
    elif adopted:
        out += [
            f"Adopted the description from iteration {adopted[-1]['iteration']} — "
            f"positive rate {_fmt(data.get('best_positive_rate'))}, up from "
            f"{_fmt(history[0].get('positive_rate'))}.",
            "",
        ]
    else:
        out += [
            "**Kept the incumbent.** No candidate cleared the detection floor. "
            "That is a result, not a failure: it means no proposed wording differed "
            "from the original by more than this sample size can resolve.",
            "",
        ]

    out += ["## Iterations", "", _iterations_table(history), ""]
    out += ["Verdicts: " + "; ".join(f"`{k}` — {v}" for k, v in VERDICT_NOTE.items()), ""]

    contaminated = sum(h.get("contaminated_runs", 0) for h in history)
    if contaminated:
        out += [
            f"> **{contaminated} runs were contaminated** — won by an installed copy of "
            f"`{name}` rather than the probe. They are excluded from every rate above. "
            f"Disable the plugin before trusting these numbers.",
            "",
        ]

    # Show the description actually in force -- the most recent iteration whose
    # wording was adopted, not the most recent one measured. When nothing beat
    # the baseline, the baseline is what ships, so that is what to show.
    in_force = [h for h in history if h.get("adopted") and h.get("results")]
    best = in_force[-1] if in_force else (
        [h for h in history if h.get("results")] or [None])[-1]
    if best:
        out += [f"## Per-query detail — iteration {best['iteration']}", "",
                _per_query_table(best, skill_name=name), ""]
        neg = best.get("negative_rate")
        if neg is not None:
            out += [f"Over-triggering on the negative set: **{neg:.3f}**"
                    + ("  (clean)" if not neg else "  — the description is too broad"), ""]
    elif history:
        out += ["_Per-query detail unavailable — no iteration in this run "
                "carries per-query results._", ""]

    out += ["## Descriptions", ""]
    for h in history:
        tag = " (adopted)" if h.get("adopted") and h["iteration"] > 0 else (
            " (baseline)" if h["iteration"] == 0 else "")
        out += [f"### Iteration {h['iteration']}{tag}", "",
                "> " + h["description"].replace("\n", "\n> "), ""]

    return "\n".join(out).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Render optimization results as markdown")
    parser.add_argument("results", help="Path to results.json from run_loop.py")
    parser.add_argument("--skill-name", default="")
    parser.add_argument("-o", "--out", default=None, help="Write here instead of stdout")
    args = parser.parse_args()

    data = json.loads(Path(args.results).read_text())
    md = generate_markdown(data, skill_name=args.skill_name)
    if args.out:
        Path(args.out).write_text(md)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(md)


if __name__ == "__main__":
    main()
