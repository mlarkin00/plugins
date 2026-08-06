# Trigger optimization — `prompt-design`

20 queries, 10 positive / 10 near-miss. The negatives include the two in-repo
skills that compete on overlapping phrasing (`optimizing-prompts-w-vertex`,
`new-prompt`) plus the "user wants the output, not a prompt for the output" class,
which is the boundary `prompt-design`'s description is most likely to over-claim.

Run with `.agents/tools/trigger_eval.py`, not `skill-creator-enhanced`'s
`run_eval.py` — the latter scores every positive as a miss for any skill that is
also installed as a plugin. See
`.agents/wiki/evals/run-eval-scores-an-installed-skill-as-a-miss.md`.

## Results, 2026-08-06 — no candidate beat the shipped description

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
over-triggering, and the Vertex and Cloud Build queries route to the right skills.

## Two queries were rewritten after the first run

`eval_results_1` used shorter forms of the "tighten up our code review bot's system
prompt" and "I've been iterating on this prompt" queries that did not paste the
prompt in. A session with no artifact to work on goes looking for the file, does not
find it, and asks for it — correct behaviour that scores as a non-trigger and tests
nothing. Both now include the prompt inline. Keep eval queries self-contained.
