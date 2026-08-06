# CI/CD Integration for Agent Evals

Quality gates that run agent evals automatically on every change, block
regressions before merge, and keep results attributable.

## Contents

1. Trigger strategy
2. Environment and reproducibility
3. Pipeline shape
4. Reporting
5. Data versioning

## 1. Trigger strategy

| Trigger | Suite | Purpose |
| :--- | :--- | :--- |
| Every commit (dev branches) | Lightweight — computation criteria (`tool_trajectory_avg_score`, `response_match_score`) on a core slice | Fast feedback, minutes not hours |
| Pull request → main | Comprehensive — full dataset, LLM-judged criteria, statistical baseline comparison | The merge gate |
| Scheduled (nightly/weekly) | Full suite against the newest dataset version, current production agent | Drift detection without a code change |

Any change triggers the pipeline — agent logic, prompt/instruction templates,
tool definitions, config, or model version. Prompt edits regress agents as
reliably as code edits.

On Google Cloud, these map to Cloud Build triggers (the `cloud-build-triggers`
skill covers 1st/2nd-gen connection mechanics); the pattern is identical on
GitHub Actions, GitLab CI, or Jenkins.

## 2. Environment and reproducibility

- **Isolated, containerized eval jobs** — no shared mutable state between runs.
- **Environment parity** — the eval environment reaches the same tools/APIs the
  production agent does (or faithful fakes); an agent evaluated against stubs is
  a different agent.
- **Pin everything a result depends on**: dataset version, eval config
  (criteria + thresholds), agent version, judge configuration. A result that
  can't name these is unattributable and unreproducible.

## 3. Pipeline shape

```yaml
# Cloud Build sketch (adapt per repo layout)
steps:
  - id: install
    name: python
    entrypoint: pip
    args: ["install", "-r", "requirements.txt"]   # includes google-cloud-aiplatform[adk,evaluation]
  - id: eval
    name: python
    entrypoint: bash
    args: ["-c", "python run_evals.py --dataset-version $_DATASET_VERSION --runs 3 --out results/candidate.json"]
  - id: gate
    name: python
    entrypoint: bash
    args: ["-c", "python compare_to_baseline.py results/candidate.json baselines/production.json --plan eval-plan.md"]
    # compare_to_baseline exits non-zero on floor breach or significant regression
```

- `run_evals.py` wraps whichever harness applies — `adk eval` (or pytest
  `AgentEvaluator`), and/or an `EvalTask` script — and runs the suite the number
  of times the statistics require.
- The gate step implements `statistical-gates.md`: paired tests over cases,
  block on floor breach or significant regression beyond bound.
- On acceptance (merge/deploy), promote the candidate's results to become the
  new stored baseline artifact.
- Cost control: LLM-judged criteria on every commit gets expensive fast — that
  is what the tiered trigger strategy is for.

## 4. Reporting

- **PR comment** with the metric table (candidate vs baseline, delta, CI), the
  gate verdict, and links to per-case results — reviewers should not need to
  open the CI logs to know what happened.
- **Failure notifications** to the team channel with a direct link to the
  failing cases and traces.
- **Trend dashboards** of the scheduled runs — slow drift is invisible in
  PR-sized comparisons.
- **Traceability**: every report links code change ↔ dataset version ↔ eval
  config ↔ detailed run logs.

## 5. Data versioning

Golden datasets are code: same repo (or DVC/Git LFS when large), reviewed
changes, immutable released versions. Baseline results are artifacts keyed by
(agent version, dataset version) — comparing across dataset versions is a
category error the pipeline should refuse.
