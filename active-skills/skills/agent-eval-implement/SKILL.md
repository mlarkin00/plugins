---
name: agent-eval-implement
description: Build the runnable eval assets for an AI agent on GCP — ADK evalset files, pytest eval wiring, Gen AI evaluation service code for trajectory and final-response metrics, custom LLM-as-judge rubrics and scorers, and ground-truth eval datasets in Cloud Storage or BigQuery. Use when the user wants to write, build, create, or add agent evals, an evalset or eval test file, a custom judge or scorer for agent output, or an eval/ground-truth dataset — for an ADK, Vertex AI, Agent Engine, Gemini Enterprise, LangGraph, or LangChain agent. Works from an eval plan produced by agent-eval-design, or standalone when the user names just one asset. Not for choosing which metrics to measure (use agent-eval-design), executing eval runs or CI/CD gating (use agent-eval-run), or creating Claude Code skills (use skill-creator-enhanced).
---

# Agent Eval Implement

Turn a written eval plan into runnable eval assets. If no plan exists — no chosen
metrics, no dataset strategy, no thresholds — invoke `agent-eval-design` first;
implementing without a plan produces evals that measure whatever was easiest to
code.

API names below were verified 2026-08-06. Before writing code against them,
confirm exact signatures with a live doc lookup (google-developer-knowledge MCP
first, context7 second) — this surface is evolving quickly.

## Step 1 — Choose the harness path

| Situation | Path |
| :--- | :--- |
| Agent built with ADK, evals run against the local agent module | **ADK evalsets** — fastest loop, no extra infra (Step 2) |
| Agent deployed on Agent Engine, built with another framework (LangChain, LangGraph, CrewAI), or metrics beyond ADK's criteria needed | **Gen AI evaluation service** via the Vertex AI SDK (Step 3) |
| Both apply | Both compose: ADK evalsets for the fast inner loop, the evaluation service for richer programmatic runs |

## Step 2 — Author ADK evalsets

Full schema, criteria catalog, and pytest wiring: `references/adk-evalsets.md`.

1. **Capture, don't hand-write, the first cases.** Run `adk web
   <agents_folder>`, interact with the agent to produce a good session, then in
   the **Eval tab**: create/select an eval set → **Add current session**. Edit
   the saved case (pencil icon) to trim it to the *intended* behavior — captured
   sessions record what the agent did, which is not yet ground truth.
2. Cases live in a `<name>.evalset.json` file: each eval case is a conversation
   of invocations with `user_content`, expected `final_response`, and
   `intermediate_data.tool_uses` (the golden trajectory).
3. Set criteria in a `test_config.json` next to the evalset — start from the
   plan's thresholds, e.g. `{"criteria": {"tool_trajectory_avg_score": 1.0,
   "response_match_score": 0.8}}`. LLM-based criteria (semantic match, rubrics,
   safety) need GCP credentials — see the reference.
4. Wire into pytest with `AgentEvaluator.evaluate(agent_module=...,
   eval_dataset_file_path_or_dir=...)` so agent evals run wherever unit tests
   run.

## Step 3 — Programmatic eval with the Gen AI evaluation service

Full dataset schema, metric list, and code patterns:
`references/vertex-eval-service.md`.

1. Install: `pip install google-cloud-aiplatform[adk,evaluation]`.
2. **Build the dataset** — for trajectory metrics, each row needs a
   `reference_trajectory` (list of `{"tool_name", "tool_input"}`); import from
   JSONL/CSV in Cloud Storage, a BigQuery table, or a pandas DataFrame. The same
   Cloud Storage/BigQuery dataset feeds console-driven evaluations on the Agent
   Platform, so one dataset serves both SDK and UI runs.
3. **Wrap the agent as a runnable** the service can invoke per row (Agent Engine
   agents and framework templates slot in directly), so `predicted_trajectory`
   and responses are produced during the run.
4. **Configure `EvalTask`** mixing metric kinds: computation-based trajectory
   metrics (`trajectory_exact_match`, `trajectory_precision`, …), response
   metrics, custom computation metrics, and model-based pointwise metrics.

## Step 4 — Build custom LLM-as-judge scorers

When the plan calls for qualities no built-in metric captures — rubric design
rules, a trajectory-judge template, and the calibration procedure:
`references/custom-judges.md`. The non-negotiables: anchored score levels, one
quality per rubric, a judge from a different model family than the agent, and
calibration against a human-labeled sample before the judge gates anything.

## Step 5 — Prepare and version datasets

- Store the golden dataset in the format the harness consumes (evalset JSON for
  ADK; JSONL/CSV/BigQuery for the evaluation service) and version it like code.
- Keep the adversarial slice tagged (see agent-eval-design's
  `adversarial-testing.md`) so per-class safe-refusal rates stay reportable.
- Public demo datasets under
  `gs://cloud-ai-demo-datasets/agent-eval-datasets/` show the expected shape.

## Step 6 — Smoke-test one case end-to-end

Before authoring the full suite, run a single case through the chosen path and
confirm: the agent is invoked, the metric produces a score, and the score lands
where results are read. Every dataset-format and auth problem surfaces on case
one — finding them on case forty means re-running thirty-nine.

Then hand off to `agent-eval-run` for execution, CI/CD gating, and analysis.

## Gotchas & Anti-Patterns

| Excuse | Reality |
| :--- | :--- |
| "I'll write the evalset JSON by hand from scratch." | The schema has nested invocation/tool-use structure that's easy to get subtly wrong. Capture a session in `adk web` and edit it. |
| "The captured session is the expected behavior." | It's the *observed* behavior, bugs included. Edit every captured case into ground truth before it enters the golden set. |
| "I remember the EvalTask/metric API from training data." | The surface is changing fast; a stale signature fails late and confusingly. Verify with a live doc lookup first. |
| "Exact trajectory match for everything — it's the strictest." | Strictest is not safest: agents with multiple valid paths fail spuriously and the suite gets ignored. Match strictness to how procedural the task is (see the metric taxonomy). |
| "The judge rubric can bundle correctness, tone, and efficiency." | Multi-quality rubrics produce uninterpretable middle scores. One rubric per quality, anchored levels. |
| "Skip the smoke test, the suite is almost done." | Auth, schema, and runnable-wiring errors surface on the first case. Prove the pipe with one case before scaling to forty. |
| "No plan exists, but I can pick reasonable metrics while coding." | Metrics chosen during implementation measure what's convenient. Invoke agent-eval-design first — it's a short step. |
