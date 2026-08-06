---
name: agent-eval-run
description: Execute agent evals and act on the results on GCP — run adk eval or pytest eval suites, interpret per-case and aggregate scores, compare a candidate agent against a baseline with statistical quality gates, debug failed trajectories down to the first bad step, wire evals into CI/CD, and extend to production with online evals and observability. Use when the user wants to run or re-run agent evals, see why an agent eval failed, check whether an agent version regressed, add agent evals to a CI/CD or Cloud Build pipeline, gate a deployment on eval results, fix flaky or noisy eval gates, or monitor a deployed agent's quality. Covers the non-determinism discipline these runs need: one run proves nothing, and a score that moved needs a statistical test before it means anything. Not for choosing metrics (use agent-eval-design), authoring evalsets or eval code (use agent-eval-implement), or measuring Claude Code skills (use skill-creator-enhanced).
---

# Agent Eval Run

Execute the eval assets built by `agent-eval-implement`, gate changes on the
results, and keep evaluating after deploy. The through-line is
non-determinism: an agent gives different answers on identical inputs, so a
single run proves nothing — every gating decision below is a statistical
decision over repeated runs.

## Step 1 — Run locally

```bash
adk eval <AGENT_MODULE_PATH> <EVAL_SET_FILE_PATH> \
  [--config_file_path=test_config.json] [--print_detailed_results]
```

- `AGENT_MODULE_PATH` is the directory whose `__init__.py` exposes an `agent`
  module with a `root_agent`.
- Run a subset by suffixing the evalset path:
  `orders.evalset.json:cancel_order,refund_flow`.
- Interactive alternative: `adk web` → Eval tab → select cases → Run Evaluation
  (thresholds set in the metric dialog; history records them per run).
- Pytest-wired evals (`AgentEvaluator`) run under `pytest tests/integration/`.
- `EvalTask`-based suites run as plain Python against the Gen AI evaluation
  service.
- `adk conformance` replays recorded baselines to catch behavioral drift the
  metric suite doesn't score.

## Step 2 — Handle non-determinism before trusting any number

Run the suite (or at minimum its gating metrics) several times per agent
version — 3–5 runs is a practical floor. Then compare *distributions*, not
single numbers. Test selection, worked examples, and threshold guidance:
`references/statistical-gates.md`.

| Metric shape | Comparison test |
| :--- | :--- |
| Pass/fail per case, same cases both versions | McNemar (paired) |
| Continuous (latency, cost, similarity scores) | Paired t-test; Wilcoxon signed-rank if not normal |
| Ordinal rubric scores (1–5 judges) | Wilcoxon signed-rank |
| Complex ratios / small samples | Bootstrap confidence intervals |

A difference whose confidence interval contains zero is noise, whatever the
means say. Gate on "statistically significant regression beyond threshold",
never on "the number went down".

## Step 3 — Wire into CI/CD

Full pipeline patterns: `references/cicd-integration.md`. The shape:

1. **Trigger tiers** — lightweight suite on every commit; the comprehensive
   suite as a PR merge gate; scheduled full runs against fresh data to catch
   drift. For Cloud Build trigger mechanics, the `cloud-build-triggers` skill
   applies.
2. **Reproducibility** — isolated environment per job; pin the dataset version
   and record it with results; environment parity with production for tool/API
   access.
3. **Baseline comparison** — evaluate the candidate, load the stored baseline
   results (current production version, same dataset version), apply the
   statistical tests.
4. **Go/no-go** — thresholds from the eval plan, enforced automatically: breach
   → build fails, merge blocked. Post the metric summary as a PR comment;
   failures link to detailed traces.

## Step 4 — Analyze failures

- Start from instance-level results, not aggregates: which cases, which metric,
  what score. (`--print_detailed_results`; `EvalTask` instance rows carry
  `score`/`explanation` per case.)
- Read the trajectory like a flight recorder and find the **first bad step** —
  wrong tool, hallucinated argument, misread tool output. Everything after it
  is usually noise. The `adk web` Trace tab gives per-invocation
  event/request/response/graph views.
- Cluster failures by pattern (same tool failing, same intent slice, same
  metric) before fixing anything; fix root causes by cluster size, not by case
  order.
- Distinguish *agent regressions* from *judge or dataset problems* — a rubric
  change or dataset edit shifts scores without any agent change (the eval plan's
  versioning discipline makes this checkable).

## Step 5 — Improve and re-arm

- Feed confirmed production failures back into the golden dataset as permanent
  regression cases — the eval suite must grow where reality found holes.
  Authoring those cases is `agent-eval-implement`'s job; invoke it rather than
  hand-editing dataset files, since a case added without its reference
  trajectory silently weakens every trajectory metric.
- `adk optimize` iteratively refines the agent's root instructions against a
  test suite — a mechanical first pass at instruction-level fixes.
- After any fix, rerun the full suite (all runs, both statistics) — a fix that
  helps one cluster can regress another.

When the failures point at the *measurement* rather than the agent — a metric
that never discriminates, a threshold nothing can clear, a judge disagreeing
with human review — that is a design problem, not a run problem. Invoke
`agent-eval-design` to revisit metric choice and thresholds; changing them
here, mid-analysis, is how a gate quietly becomes whatever the agent already
scores.

## Step 6 — Extend to production

Offline suites can't predict live-traffic behavior. Patterns for shadow-mode
deployment, asynchronous scoring of sampled sessions, dashboards, and anomaly
alerts: `references/online-evals.md`. Instrument deployed agents with Cloud
Observability (tracing, logging, metrics) from day one — online evals consume
those traces.

## Gotchas & Anti-Patterns

| Excuse | Reality |
| :--- | :--- |
| "The score dropped 3 points, the candidate is worse." | On one run, that's indistinguishable from noise. Repeated runs + a paired test, or no conclusion. |
| "The score improved, ship it." | Improvements need the same statistics as regressions — half of small "wins" vanish on rerun. |
| "CI reruns the eval until it passes." | Retry-until-green inverts the gate: it selects for lucky runs. Fix the flakiness (more runs, aggregate gating) instead. |
| "Aggregates are down, let me tweak the prompt and rerun." | Without instance-level analysis you're guessing. Find the failing cluster and its first bad step first. |
| "The eval failed but the dataset changed too — probably fine." | A result without a pinned dataset version is unattributable. Re-run candidate and baseline on the same version. |
| "Offline evals pass, so production is covered." | Curated datasets contain zero unknown unknowns. Shadow mode and online scoring exist for what the dataset didn't imagine. |
| "This is about running evals — same as skill benchmarks." | Claude Code skill measurement is skill-creator-enhanced. This skill runs evals for GCP AI agents. |
