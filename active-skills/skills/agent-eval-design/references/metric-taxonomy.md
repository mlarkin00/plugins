# Agent Eval Metric Taxonomy

Catalog of metric categories with the public GCP metric/criterion names that
implement each. Names verified against adk.dev/evaluate and the Gemini Enterprise
Agent Platform agent-evaluation docs on 2026-08-06 — re-verify with a live doc
lookup before coding against them.

## Contents

1. Outcome metrics
2. Trajectory & tool-use metrics
3. RAG metrics
4. Operational metrics
5. Quality & safety metrics
6. Mapping to public implementations

## 1. Outcome metrics

Judge the final result the user sees.

- **Task success rate** — did the agent achieve the user's goal? For multi-turn
  conversations, ADK's `multi_turn_task_success_v1` scores goal completion across
  the whole session.
- **Reference match** — closeness to a known-good answer. Deterministic:
  `response_match_score` (ROUGE-1 similarity). Semantic: `final_response_match_v2`
  (LLM-judged equivalence — tolerates rephrasing, catches meaning drift).
- **Factual correctness / groundedness** — claims supported by the sources or tool
  outputs available to the agent (`hallucinations_v1`).
- **User satisfaction** — thumbs-up/down or CSAT from real traffic; an online
  metric, planned now and wired in production.

## 2. Trajectory & tool-use metrics

Judge the path: which tools, which arguments, what order, how many steps.

- **Trajectory match family** (compare predicted vs reference tool-call list):
  - `trajectory_exact_match` — same calls, same order, nothing extra.
  - `trajectory_in_order_match` — reference calls present in order; extras allowed.
  - `trajectory_any_order_match` — reference calls present in any order.
  - `trajectory_precision` / `trajectory_recall` — fraction of predicted calls
    that are in the reference / fraction of reference calls that were made.
  - `trajectory_single_tool_use` — was one specific tool used at all (no
    reference trajectory needed).
  - ADK's `tool_trajectory_avg_score` — exact tool-trajectory match averaged over
    the eval set.
- **Tool-use quality** — `rubric_based_tool_use_quality_v1` (LLM-judged against
  custom rubrics: right tool chosen, valid arguments, sane ordering); for
  conversations, `multi_turn_tool_use_quality_v1` and
  `multi_turn_trajectory_quality_v1`.
- **Efficiency** — step count vs the golden trajectory; penalize redundant calls.
  Usually a custom computation metric.

Choosing within the match family: exact match for workflows with one correct
procedure (strictest, brittle to harmless variation); in-order/any-order when
extra exploratory calls are acceptable; precision/recall when partial credit is
more informative than pass/fail.

## 3. RAG metrics

Only for retrieval-backed agents; they separate retriever failures from generator
failures.

- **Faithfulness / groundedness** — answer consistent with retrieved context
  (RAGAS `faithfulness`; ADK `hallucinations_v1`).
- **Answer relevancy** — answer addresses the question (RAGAS `answer_relevancy`).
- **Context precision** — retrieved chunks that matter are ranked high (RAGAS
  `context_precision`).
- **Context recall** — retrieval found everything needed to answer (RAGAS
  `context_recall`; needs ground-truth answers).

Low faithfulness + high context recall → generator problem. High faithfulness +
low context recall → retriever problem.

## 4. Operational metrics

Cost of being right. The Gen AI evaluation service appends `latency_in_seconds`
and `failure` (invocation error) to every agent eval automatically — no
configuration needed.

- **Latency** — per response; track p95, not just mean.
- **Cost** — tokens and billable API calls per task.
- **Tool-call reliability** — technical failure/retry/timeout rate of tool calls,
  as distinct from *wrong* tool calls (a trajectory concern).

## 5. Quality & safety metrics

- **Safety / harmlessness** — `safety_v1` scores responses against safety policy.
- **Hallucination** — `hallucinations_v1` (also listed under outcome; it gates
  both correctness and safety).
- **Response quality without a reference** — `rubric_based_final_response_quality_v1`:
  define attributes of a good response ("concise", "cites the order number",
  "helpful tone") when no trusted reference answer exists.
- **Policy adherence & deflection** — follows data-access and behavioral rules;
  refuses out-of-policy requests gracefully. Encode as adversarial eval cases
  whose expected behavior is the refusal (see `adversarial-testing.md`).
- **Adversarial robustness** — resists prompt injection and jailbreaks; measured
  as safe-refusal rate over the adversarial slice of the dataset.

## 6. Mapping to public implementations

| Where it runs | Metrics available |
| :--- | :--- |
| ADK eval criteria (`adk eval`, pytest `AgentEvaluator`, `adk web`) | `tool_trajectory_avg_score`, `response_match_score`, `final_response_match_v2`, `rubric_based_final_response_quality_v1`, `rubric_based_tool_use_quality_v1`, `hallucinations_v1`, `safety_v1`, `multi_turn_task_success_v1`, `multi_turn_trajectory_quality_v1`, `multi_turn_tool_use_quality_v1`, `per_turn_user_simulator_quality_v1` |
| Gen AI evaluation service (`EvalTask`) | `trajectory_exact_match`, `trajectory_in_order_match`, `trajectory_any_order_match`, `trajectory_precision`, `trajectory_recall`, `trajectory_single_tool_use`, response metrics (e.g., `rouge_l_sum`, `bleu`, pointwise model-based metrics), custom computation metrics; `latency_in_seconds` + `failure` automatic |
| RAGAS (open source, works with Vertex AI models) | `faithfulness`, `answer_relevancy`, `context_precision`, `context_recall` |

ADK's LLM-based criteria (response quality, safety, multi-turn, hallucination)
call the Vertex Gen AI Evaluation Service API under the hood and need GCP
credentials (ADC, or `GOOGLE_CLOUD_PROJECT` + `GOOGLE_CLOUD_LOCATION`).
