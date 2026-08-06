# Gen AI Evaluation Service for Agents

Programmatic final-response and trajectory evaluation via the Vertex AI SDK.
Verified against the Gemini Enterprise Agent Platform agent-evaluation docs on
2026-08-06 — confirm signatures with a live doc lookup before coding.

Install: `pip install google-cloud-aiplatform[adk,evaluation]`

## Contents

1. Dataset schema
2. Importing datasets
3. Trajectory metrics
4. Running an EvalTask
5. Custom metrics
6. Reading results

## 1. Dataset schema

Trajectory evaluation compares two columns per row:

- `predicted_trajectory` — tool calls the agent actually made (produced during
  the run when a runnable is passed).
- `reference_trajectory` — the golden trajectory; required by every trajectory
  metric except `trajectory_single_tool_use`.

A trajectory is a list of tool calls:

```python
reference_trajectory = [
    [  # row 1: one expected call
        {"tool_name": "set_device_info",
         "tool_input": {"device_id": "device_2", "updates": {"status": "OFF"}}}
    ],
    [  # row 2: two expected calls in order
        {"tool_name": "get_user_preferences", "tool_input": {"user_id": "user_y"}},
        {"tool_name": "set_temperature",
         "tool_input": {"location": "Living Room", "temperature": 23}},
    ],
]
```

Final-response evaluation uses the same schema as model response evaluation
(prompt / response / reference columns).

## 2. Importing datasets

Accepted sources: **JSONL or CSV in Cloud Storage**, a **BigQuery table**, or a
**pandas DataFrame**. Cloud Storage/BigQuery datasets are also what
console-driven evaluations on the Agent Platform consume — maintain one
versioned dataset for both.

Public demo datasets (shape reference, not production use):
`gs://cloud-ai-demo-datasets/agent-eval-datasets/{on-device,customer-support,content-creation}/`
with paired `tools.py` and `eval_dataset.json`.

## 3. Trajectory metrics

| Metric | Scores 1 when… | Output |
| :--- | :--- | :--- |
| `trajectory_exact_match` | predicted == reference: same calls, same order, no extras | 0/1 |
| `trajectory_in_order_match` | reference calls appear in order; extras allowed | 0/1 |
| `trajectory_any_order_match` | reference calls all appear, any order, extras allowed | 0/1 |
| `trajectory_precision` | (predicted calls also in reference) / predicted count | [0,1] |
| `trajectory_recall` | (reference calls also in predicted) / reference count | [0,1] |
| `trajectory_single_tool_use` | a named tool appears anywhere in the trajectory | 0/1 |

`trajectory_single_tool_use` takes a spec: `TrajectorySingleToolUse(tool_name="…")`.
Two operational metrics are appended automatically to every agent eval —
`latency_in_seconds` and `failure` (1 = invocation error).

## 4. Running an EvalTask

Mix computation-based, model-based, and custom metrics in one task; pass the
agent as a `runnable` so predicted trajectories and responses are produced
during evaluation:

```python
single_tool_use_metric = TrajectorySingleToolUse(tool_name="cancel_order")

eval_task = EvalTask(
    dataset=EVAL_DATASET,
    metrics=[
        "rouge_l_sum",
        "trajectory_exact_match",
        "trajectory_precision",
        single_tool_use_metric,
        custom_trajectory_eval_metric,      # CustomMetric (see §5)
        response_follows_trajectory_metric, # PointwiseMetric (see §5)
    ],
)
eval_result = eval_task.evaluate(runnable=RUNNABLE)
```

Agent Engine agents (including LangChain/LangGraph/CrewAI built from its
templates) slot in as the runnable — official notebooks in the
GoogleCloudPlatform/generative-ai repo cover each framework.

## 5. Custom metrics

**Model-based (pointwise judge)** — templated rubric, then a metric:

```python
response_follows_trajectory_prompt_template = PointwiseMetricPromptTemplate(
    criteria={"Follows trajectory":
        "Evaluate whether the agent's response logically follows from the "
        "sequence of actions it took…"},
    rating_rubric={"1": "Follows trajectory", "0": "Does not follow trajectory"},
    input_variables=["prompt", "predicted_trajectory"],
)
response_follows_trajectory_metric = PointwiseMetric(
    metric="response_follows_trajectory",
    metric_prompt_template=response_follows_trajectory_prompt_template,
)
```

Rubric-design rules for these templates: `custom-judges.md`.

**Computation-based** — any Python function over an instance dict:

```python
def essential_tools_present(instance, required_tools=["lookup_orders", "cancel_order"]):
    tools_present = [t["tool_name"] for t in instance["predicted_trajectory"]]
    score = sum(t in tools_present for t in required_tools) / len(required_tools)
    return {"essential_tools_present": score}

custom_trajectory_eval_metric = CustomMetric(
    name="essential_tools_present", metric_function=essential_tools_present)
```

## 6. Reading results

Instance-level rows carry `response`, `score`, `explanation` (for model-based
metrics), `predicted_trajectory`/`reference_trajectory` (trajectory metrics),
plus `latency_in_seconds` and `failure`. Aggregates report `mean` and `standard
deviation` per metric. The standard deviation is not decoration — it feeds the
statistical gating that `agent-eval-run` performs; persist it with the results.
