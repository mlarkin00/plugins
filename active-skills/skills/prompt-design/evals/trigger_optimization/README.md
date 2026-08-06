# Trigger optimization — `prompt-design`

22 queries, 10 positive / 12 near-miss. The negatives include the in-repo skills
that compete on overlapping phrasing (`new-prompt`, `skill-creator-enhanced`) plus
the "user wants the output, not a prompt for the output" class, which is the
boundary `prompt-design`'s description is most likely to over-claim.

**Query 11 lost its owner.** "Run the Vertex AI Prompt Optimizer on this prompt and
give me steering hints between iterations" was written as a *routing* negative
against `optimizing-prompts-w-vertex`, removed from this repo 2026-08-06. It stays a
correct negative — `prompt-design` should not claim a request to drive a specific
external tool — but it now tests only non-triggering, not routing. Keep it or
replace it deliberately; do not read a 0.00 on it as evidence the boundary still
works.

## Writing a skill description belongs to `skill-creator-enhanced`

Decided 2026-08-06, and the two queries at the end of the set encode it. "Rewrite
my skill's description so it triggers reliably" reads like prompt work — it shares
almost all of `prompt-design`'s vocabulary — but the artifact wanted is a single
frontmatter sentence whose success metric is a measured trigger rate, not a
TCREI `[TASK]`/`[CONTEXT]`/`[REFERENCES]` block. `skill-creator-enhanced` claims
the task outright ("optimize a skill's description for better triggering
accuracy") and owns the machinery that measures it. `prompt-design` answering
these would hand back the wrong artifact, so they are negatives.

Measured 3 runs each in live mode, 2026-08-06, Claude Code 2.1.x:

| Query | `prompt-design` | What fired |
| :--- | ---: | :--- |
| Figma skill — write a new description + test cases | 0.00 | `skill-creator-enhanced` 3/3 |
| pdf-extract skill — reword an existing description | 0.00 | *nothing*, 3/3 |

Only the first is discriminating. The second is a correct negative but tests
nothing about the boundary, because **no** skill claims it: a query that says
"reword this skill's description so it triggers reliably" in plain words does not
fire `skill-creator-enhanced`, whose description advertises exactly that. That is a
gap in `skill-creator-enhanced`'s description, not in this eval set — filed in
`.agents/TODO.md`. Keep the query; it is the regression test for that fix.

Run in **live mode**, which measures the installed skill against its real
competitors and records which skill actually fired:

```bash
cd skill-creator-enhanced
python3 -m scripts.run_eval \
  --eval-set ../prompt-design/evals/trigger_optimization/eval_set.json \
  --skill-path ../prompt-design \
  --mode live --cwd "$(mktemp -d)" \
  --runs-per-query 10 --num-workers 10 --timeout 120 \
  > results.json
```

The `--cwd` must be an empty directory: a cwd full of source sends the nested
session reading code instead of choosing a skill. Do **not** use probe mode here —
it injects a candidate description under a throwaway name, and the installed
`prompt-design` wins the call instead, which is what made every positive read as
0.00 before 2026-08-06. Probe mode now reports those runs as `unmeasured` rather
than failed. See
`.agents/wiki/evals/run-eval-scores-an-installed-skill-as-a-miss.md`.

## Results, 2026-08-06 — no candidate beat the shipped description

Run against the 20-query version of this set, before the two
`skill-creator-enhanced` negatives were added. The `/20` totals below do not cover
those two queries; re-run before comparing anything to them.

| Run | Description | Total | Positives | Negatives |
| :--- | :--- | ---: | ---: | ---: |
| `eval_results_1_shipped-description.json` | shipped (TCREI rewrite, 2026-07-22) | 14/20 | 4/10 | 10/10 |
| `eval_results_2_rewrite-candidate.json` | rewrite, broader surface + explicit exclusions | 16/20 | 6/10 | 10/10 |
| `eval_results_3_additive-candidate.json` | shipped sentence 1 verbatim + appended coverage | 14/20 | 4/10 | 10/10 |

**The shipped description was kept.** The totals look like a 2-point win for the
rewrite, and they are not: candidates 2 and 3 have the *same* mean positive trigger
rate to three decimal places (0.500 vs 0.500) while 4 of the 10 positives flip by
≥0.66 between them. Candidate 3 contains candidate 1's opening sentence verbatim and
still scores differently on that sentence's own cases. At 3 runs per query the
per-query pass/fail signal is dominated by run-to-run variance.

Full account, and what a conclusive run costs:
`.agents/wiki/evals/three-runs-per-query-cannot-separate-two-descriptions.md`.

## Negatives are the trustworthy half

Every negative held at 0.00 across all three runs except `/new-prompt`, which
touched 0.33 twice. Whatever else is uncertain, `prompt-design` is not
over-triggering, and the Vertex and Cloud Build queries routed to the right skills.

All three runs predate the 2026-08-06 skill removals and were measured with
`optimizing-prompts-w-vertex` installed, which is what the Vertex query routed to.
The `fired` fields in the result JSONs record that competitor by name; they are the
measurement as taken and are left as-is.

## Two queries were rewritten after the first run

`eval_results_1` used shorter forms of the "tighten up our code review bot's system
prompt" and "I've been iterating on this prompt" queries that did not paste the
prompt in. A session with no artifact to work on goes looking for the file, does not
find it, and asks for it — correct behaviour that scores as a non-trigger and tests
nothing. Both now include the prompt inline. Keep eval queries self-contained.
