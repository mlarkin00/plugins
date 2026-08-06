# ADK Evalsets, Criteria, and Pytest Wiring

Verified against adk.dev/evaluate on 2026-08-06. Confirm signatures with a live
doc lookup before coding.

## Contents

1. Evalset file schema
2. Capturing cases in the web UI
3. Criteria catalog and test_config.json
4. Pytest integration
5. Auth for LLM-based criteria
6. User simulation and conformance

## 1. Evalset file schema

An evalset (`<name>.evalset.json`) holds eval cases; each case is a full session:
a conversation of invocations plus initial session state. Structure (abridged):

```json
{
  "eval_set_id": "orders_eval_set",
  "name": "Order-handling evals",
  "eval_cases": [
    {
      "eval_id": "cancel_pending_order",
      "conversation": [
        {
          "invocation_id": "e-…",
          "user_content": {"role": "user", "parts": [{"text": "Cancel my pending order"}]},
          "final_response": {"role": null, "parts": [{"text": "Your pending order 123 is cancelled."}]},
          "intermediate_data": {
            "tool_uses": [
              {"name": "lookup_orders", "args": {"status": "pending"}},
              {"name": "cancel_order", "args": {"order_id": "123"}}
            ],
            "intermediate_responses": []
          }
        }
      ],
      "session_input": {"app_name": "orders_app", "user_id": "user", "state": {}}
    }
  ]
}
```

- `intermediate_data.tool_uses` is the golden trajectory the trajectory criteria
  compare against; `final_response` is the reference for response criteria.
- Multi-turn cases are additional entries in `conversation`.
- `session_input.state` seeds session state — how to test behavior that depends
  on prior context.
- The authoritative schema is the Pydantic `EvalSet` model in the
  `google/adk-python` repo (`src/google/adk/evaluation/eval_set.py`). Older
  hand-maintained formats still run via the CLI, but new files follow the
  Pydantic schema — the web UI writes it automatically.

Simpler single-file variant: `*.test.json` files hold small unit-style cases,
conventionally under `tests/integration/fixture/<agent_name>/`.

## 2. Capturing cases in the web UI

1. `adk web <path_to_agents_folder>` and interact with the agent until it
   produces a session worth keeping.
2. **Eval tab** (right side) → create or select an eval set → **Add current
   session**.
3. Click the case ID to inspect; use the pencil (Edit current eval case) to
   correct agent responses, delete wrong messages, or drop the case. **A captured
   session is observed behavior — edit it into intended behavior before it
   becomes ground truth.**
4. Run selected cases from the tab: the EVALUATION METRIC dialog exposes
   threshold sliders for tool trajectory score and response match score, and the
   eval history records the thresholds used per run.
5. Failures support hover comparison of actual vs expected output, and the Trace
   tab gives per-invocation event/request/response/graph views for debugging.

## 3. Criteria catalog and test_config.json

Defaults when no config is given: `tool_trajectory_avg_score: 1.0` (exact
trajectory match) and `response_match_score: 0.8` (ROUGE-1). Override via
`test_config.json`:

```json
{"criteria": {"tool_trajectory_avg_score": 1.0, "response_match_score": 0.8}}
```

| Criterion | What it scores | Type |
| :--- | :--- | :--- |
| `tool_trajectory_avg_score` | Exact tool-trajectory match | computation |
| `response_match_score` | ROUGE-1 similarity to reference response | computation |
| `final_response_match_v2` | Semantic equivalence to reference | LLM-judged |
| `rubric_based_final_response_quality_v1` | Response quality vs custom rubrics | LLM-judged |
| `rubric_based_tool_use_quality_v1` | Tool-use quality vs custom rubrics (right tool, valid args, order) | LLM-judged |
| `hallucinations_v1` | Groundedness against available context | LLM-judged |
| `safety_v1` | Harmlessness of the response | LLM-judged |
| `multi_turn_task_success_v1` | Conversation-level goal completion | LLM-judged |
| `multi_turn_trajectory_quality_v1` | Whole-conversation trajectory quality | LLM-judged |
| `multi_turn_tool_use_quality_v1` | Tool calls across a conversation | LLM-judged |
| `per_turn_user_simulator_quality_v1` | Simulated-user quality per turn | LLM-judged |

Selection guidance (from the ADK docs): CI/regression → the two computation
criteria (fast, deterministic); trusted reference answers →
`final_response_match_v2`; no reference but definable attributes →
`rubric_based_final_response_quality_v1`; validating tool reasoning →
`rubric_based_tool_use_quality_v1`; groundedness → `hallucinations_v1`; safety →
`safety_v1`; conversational goal/trajectory/tool quality → the `multi_turn_*`
family.

## 4. Pytest integration

```python
from google.adk.evaluation.agent_evaluator import AgentEvaluator
import pytest

@pytest.mark.asyncio
async def test_order_handling():
    await AgentEvaluator.evaluate(
        agent_module="orders_agent",
        eval_dataset_file_path_or_dir="tests/integration/fixture/orders_agent/simple.test.json",
    )
```

`eval_dataset_file_path_or_dir` accepts a file or a directory. Initial session
state can be provided from a file. This is the bridge into any test runner —
`agent-eval-run` covers running it in CI.

## 5. Auth for LLM-based criteria

Every LLM-judged criterion calls the Vertex Gen AI Evaluation Service API.
Authenticate with a `GOOGLE_API_KEY`, or Application Default Credentials plus
`GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`. Without credentials, only
the two computation criteria run — a suite that silently configures only those
is measuring less than its config file suggests.

## 6. User simulation and conformance

- **User simulation** (adk.dev/evaluate/user-sim): an AI model generates user
  turns dynamically for conversation scenarios where fixed prompts are too
  rigid. Only `hallucinations_v1` and `safety_v1` combine with it — criteria
  needing expected tool use or responses don't apply when the conversation is
  generated.
- **`adk conformance`**: replays baseline files to detect behavioral deviations —
  a regression-detection complement to metric-based evals.
