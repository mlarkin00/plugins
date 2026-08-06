#!/usr/bin/env python3
"""Propose an improved skill description from eval results.

Transport is `claude -p` as a subprocess, the same mechanism `run_eval.py` uses.
The previous implementation called the Anthropic API directly via the `anthropic`
SDK, which required `ANTHROPIC_API_KEY`. That is unavailable on any machine
authenticating Claude Code through OAuth -- including the one this skill is
developed on -- so the optimization loop could not run at all. Shelling out
inherits whatever auth the user's `claude` already has.

Two consequences of the change worth knowing:

- The proposing model is now the model the user actually runs, so suggestions are
  representative of the environment the description will be judged in.
- Extended thinking is not requested explicitly. The SDK path asked for a 10k
  token thinking budget; the CLI decides for itself. The prompt asks for
  reasoning either way, so this affects depth, not correctness.

Self-check (costs one session):

    python3 -m scripts.propose --selftest
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts import stats
from scripts.utils import parse_skill_md

CHAR_LIMIT = 1024


class ProposeError(RuntimeError):
    """The CLI failed, timed out, or returned something unusable."""


def call_claude(
    prompt: str, model: str | None = None, timeout: int = 300, cwd: str | None = None
) -> dict:
    """Run one non-interactive `claude -p` turn and return its text plus metadata.

    `--output-format json` emits a JSON *array* of messages, not a single object;
    the text lives in `result` on the last message of type `result`. Verified
    against Claude Code 2.1.x, 2026-08-06.
    """
    cmd = ["claude", "-p", prompt, "--output-format", "json"]
    if model:
        cmd += ["--model", model]

    # Drop CLAUDECODE so this can nest inside a Claude Code session -- the guard
    # exists for interactive terminal conflicts, not for subprocess use.
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    # A temp cwd by default: the prompt already carries the skill content, and a
    # session started in a real repo goes reading code instead of answering.
    temp_cwd = None
    if cwd is None:
        temp_cwd = tempfile.mkdtemp(prefix="propose-")
        cwd = temp_cwd

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            env=env,
            cwd=cwd,
            timeout=timeout,
            stdin=subprocess.DEVNULL,  # else the CLI waits 3s for stdin, per call
        )
    except subprocess.TimeoutExpired as e:
        raise ProposeError(f"claude -p timed out after {timeout}s") from e

    if proc.returncode != 0:
        raise ProposeError(
            f"claude -p exited {proc.returncode}: "
            f"{proc.stderr.decode('utf-8', 'replace')[:500]}"
        )

    raw = proc.stdout.decode("utf-8", "replace")
    try:
        messages = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ProposeError(f"claude -p returned non-JSON: {raw[:500]}") from e

    if not isinstance(messages, list):
        messages = [messages]
    results = [m for m in messages if m.get("type") == "result"]
    if not results:
        raise ProposeError("no result message in claude -p output")

    final = results[-1]
    if final.get("is_error"):
        raise ProposeError(
            f"claude -p reported an error ({final.get('subtype')}): "
            f"{str(final.get('result'))[:500]}"
        )

    text = final.get("result")
    if not isinstance(text, str) or not text.strip():
        raise ProposeError("claude -p returned an empty result")

    return {
        "text": text,
        "cost_usd": final.get("total_cost_usd"),
        "duration_ms": final.get("duration_ms"),
        "num_turns": final.get("num_turns"),
    }


def extract_description(text: str) -> str:
    """Pull the description out of <new_description> tags, tolerating their absence."""
    match = re.search(r"<new_description>(.*?)</new_description>", text, re.DOTALL)
    return (match.group(1) if match else text).strip().strip('"')


def build_prompt(
    skill_name: str,
    skill_content: str,
    current_description: str,
    eval_results: dict,
    history: list[dict],
    test_results: dict | None = None,
) -> str:
    """Construct the improvement prompt.

    Carried over unchanged from the SDK implementation apart from the failure
    lists, which now report trigger rates rather than pass/fail. A query that
    triggered 4 times out of 10 is not a binary failure, and describing it as one
    is what taught the loop to chase noise.
    """
    positives = [r for r in eval_results["results"] if r["should_trigger"]]
    negatives = [r for r in eval_results["results"] if not r["should_trigger"]]
    weak = sorted((r for r in positives if r["trigger_rate"] < 1.0),
                  key=lambda r: r["trigger_rate"])
    leaking = [r for r in negatives if r["trigger_rate"] > 0.0]

    summary = eval_results.get("summary", {})
    rate = summary.get("positive_rate")
    mde = summary.get("mde")
    scores_summary = (
        f"positive trigger rate {rate:.3f}"
        + (f" (differences below {mde:.3f} are not measurable at this sample size)"
           if mde else "")
        if rate is not None
        else f"{summary.get('passed', 0)}/{summary.get('total', 0)} queries passed"
    )

    prompt = f"""You are optimizing a skill description for a Claude Code skill called "{skill_name}". A "skill" is sort of like a prompt, but with progressive disclosure -- there's a title and description that Claude sees when deciding whether to use the skill, and then if it does use the skill, it reads the .md file which has lots more details and potentially links to other resources in the skill folder like helper files and scripts and additional documentation or examples.

The description appears in Claude's "available_skills" list. When a user sends a query, Claude decides whether to invoke the skill based solely on the title and on this description. Your goal is to write a description that triggers for relevant queries, and doesn't trigger for irrelevant ones.

Here's the current description:
<current_description>
"{current_description}"
</current_description>

Current scores ({scores_summary}):
<scores_summary>
"""

    if weak:
        prompt += "WEAK POSITIVES (should trigger; rate shown out of runs):\n"
        for r in weak:
            t, n = stats.counts(r, eval_results.get("runs_per_query"))
            others = sorted({x for x in r.get("fired", []) if x})
            competing = f" -- lost to: {', '.join(others)}" if others else ""
            prompt += (
                f'  - "{r["query"]}" triggered {t}/{n}'
                f" ({r['trigger_rate']:.2f}){competing}\n"
            )
        prompt += "\n"

    if leaking:
        prompt += "OVER-TRIGGERING (should NOT trigger):\n"
        for r in leaking:
            t, n = stats.counts(r, eval_results.get("runs_per_query"))
            prompt += (
                f'  - "{r["query"]}" triggered {t}/{n} ({r["trigger_rate"]:.2f})\n'
            )
        prompt += "\n"

    if history:
        prompt += "PREVIOUS ATTEMPTS (do NOT repeat these — try something structurally different):\n\n"
        for h in history:
            rate_s = (
                f"positive rate {h['positive_rate']:.3f}"
                if h.get("positive_rate") is not None
                else f"train={h.get('train_passed', h.get('passed', 0))}/"
                     f"{h.get('train_total', h.get('total', 0))}"
            )
            verdict = f", verdict={h['verdict']}" if h.get("verdict") else ""
            prompt += f"<attempt {rate_s}{verdict}>\n"
            prompt += f'Description: "{h["description"]}"\n'
            if h.get("note"):
                prompt += f'Note: {h["note"]}\n'
            prompt += "</attempt>\n\n"

    prompt += f"""</scores_summary>

Skill content (for context on what the skill does):
<skill_content>
{skill_content}
</skill_content>

Based on the failures, write a new and improved description that is more likely to trigger correctly. When I say "based on the failures", it's a bit of a tricky line to walk because we don't want to overfit to the specific cases you're seeing. So what I DON'T want you to do is produce an ever-expanding list of specific queries that this skill should or shouldn't trigger for. Instead, try to generalize from the failures to broader categories of user intent and situations where this skill would be useful or not useful. The reason for this is twofold:

1. Avoid overfitting
2. The list might get loooong and it's injected into ALL queries and there might be a lot of skills, so we don't want to blow too much space on any given description.

Concretely, your description should not be more than about 100-200 words, even if that comes at the cost of accuracy.

Here are some tips that we've found to work well in writing these descriptions:
- The skill should be phrased in the imperative -- "Use this skill for" rather than "this skill does"
- The skill description should focus on the user's intent, what they are trying to achieve, vs. the implementation details of how the skill works.
- The description competes with other skills for Claude's attention — make it distinctive and immediately recognizable.
- If a query was lost to a *competing* skill, that is a boundary problem, not a coverage problem: sharpen what makes this skill different rather than widening it.
- If you're getting lots of failures after repeated attempts, change things up. Try different sentence structures or wordings.

I'd encourage you to be creative and mix up the style in different iterations since you'll have multiple opportunities to try different approaches and we'll just grab the highest-scoring one at the end.

Please respond with only the new description text in <new_description> tags, nothing else."""

    return prompt


def improve_description(
    skill_name: str,
    skill_content: str,
    current_description: str,
    eval_results: dict,
    history: list[dict],
    model: str | None = None,
    test_results: dict | None = None,
    log_dir: Path | None = None,
    iteration: int | None = None,
    timeout: int = 300,
    client=None,  # accepted and ignored; kept so old callers do not break
) -> str:
    """Propose one improved description. Returns the description text."""
    prompt = build_prompt(
        skill_name, skill_content, current_description, eval_results, history, test_results
    )

    first = call_claude(prompt, model=model, timeout=timeout)
    text = first["text"]
    description = extract_description(text)

    transcript: dict = {
        "iteration": iteration,
        "prompt": prompt,
        "response": text,
        "parsed_description": description,
        "char_count": len(description),
        "over_limit": len(description) > CHAR_LIMIT,
        "cost_usd": first["cost_usd"],
        "duration_ms": first["duration_ms"],
    }

    if len(description) > CHAR_LIMIT:
        # The SDK version did this as a third conversational turn. `claude -p` is
        # single-shot, so the prior exchange is restated inline -- same
        # information, one turn.
        shorten_prompt = (
            f"{prompt}\n\n"
            f"---\n\n"
            f"You previously answered:\n\n{text}\n\n"
            f"That description is {len(description)} characters, which exceeds the hard "
            f"{CHAR_LIMIT} character limit. Rewrite it to be under {CHAR_LIMIT} characters "
            f"while preserving the most important trigger words and intent coverage. "
            f"Respond with only the new description in <new_description> tags."
        )
        second = call_claude(shorten_prompt, model=model, timeout=timeout)
        shortened = extract_description(second["text"])

        transcript["rewrite_prompt"] = shorten_prompt
        transcript["rewrite_response"] = second["text"]
        transcript["rewrite_description"] = shortened
        transcript["rewrite_char_count"] = len(shortened)
        transcript["cost_usd"] = (first["cost_usd"] or 0) + (second["cost_usd"] or 0)
        description = shortened

    if len(description) > CHAR_LIMIT:
        raise ProposeError(
            f"description still {len(description)} chars after a shortening pass; "
            "refusing to return one that exceeds the frontmatter limit"
        )

    transcript["final_description"] = description

    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / f"improve_iter_{iteration or 'unknown'}.json").write_text(
            json.dumps(transcript, indent=2)
        )

    return description


def _selftest() -> int:
    """Round-trip the transport and the parser. Costs one session."""
    # Parser first -- free.
    assert extract_description("<new_description>abc</new_description>") == "abc"
    assert extract_description('  "bare text"  ') == "bare text"
    assert extract_description("pre <new_description>\n x \n</new_description> post") == "x"
    print("extract_description: ok")

    out = call_claude(
        "Reply with exactly this and nothing else: "
        "<new_description>a test description</new_description>",
        timeout=180,
    )
    got = extract_description(out["text"])
    assert got == "a test description", f"got {got!r}"
    print(f"call_claude: ok  (cost ${out['cost_usd']:.4f}, {out['duration_ms']}ms)")

    try:
        call_claude("hi", timeout=1)
    except ProposeError as e:
        assert "timed out" in str(e), e
        print("timeout handling: ok")
    else:
        raise AssertionError("expected a timeout")

    print("propose.py: all checks passed")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Propose an improved skill description")
    parser.add_argument("--selftest", action="store_true", help="Verify the transport (1 session)")
    parser.add_argument("--eval-results", help="Path to eval results JSON (from run_eval.py)")
    parser.add_argument("--skill-path", help="Path to skill directory")
    parser.add_argument("--history", default=None, help="Path to history JSON (previous attempts)")
    parser.add_argument("--model", default=None, help="Model for the proposing session")
    parser.add_argument("--timeout", type=int, default=300, help="Seconds per proposing session")
    parser.add_argument("--verbose", action="store_true", help="Print progress to stderr")
    args = parser.parse_args()

    if args.selftest:
        sys.exit(_selftest())

    if not args.eval_results or not args.skill_path:
        parser.error("--eval-results and --skill-path are required (or use --selftest)")

    skill_path = Path(args.skill_path)
    if not (skill_path / "SKILL.md").exists():
        print(f"Error: No SKILL.md found at {skill_path}", file=sys.stderr)
        sys.exit(1)

    eval_results = json.loads(Path(args.eval_results).read_text())
    history = json.loads(Path(args.history).read_text()) if args.history else []

    name, _, content = parse_skill_md(skill_path)
    current_description = eval_results["description"]

    if args.verbose:
        print(f"Current: {current_description}", file=sys.stderr)

    try:
        new_description = improve_description(
            skill_name=name,
            skill_content=content,
            current_description=current_description,
            eval_results=eval_results,
            history=history,
            model=args.model,
            timeout=args.timeout,
        )
    except ProposeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print(f"Improved: {new_description}", file=sys.stderr)

    summary = eval_results.get("summary", {})
    print(json.dumps({
        "description": new_description,
        "history": history + [{
            "description": current_description,
            "positive_rate": summary.get("positive_rate"),
            "positive_observations": summary.get("positive_observations"),
            "results": eval_results["results"],
        }],
    }, indent=2))


if __name__ == "__main__":
    main()
