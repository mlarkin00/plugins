# Statistical Quality Gates

Agents are non-deterministic: identical inputs produce varying trajectories and
responses. A quality gate that compares two single numbers therefore blocks good
changes and passes bad ones at random. The fix is standard statistics applied to
a candidate-vs-baseline comparison.

## Contents

1. The comparison setup
2. Choosing the test
3. Interpreting p-values and confidence intervals
4. Setting thresholds
5. Run-count guidance
6. Worked example

## 1. The comparison setup

- **Baseline**: the current production (or last accepted) agent version's
  results — same dataset version, same metrics, stored as a CI artifact.
- **Candidate**: the change under review, evaluated identically.
- **Paired by case**: both versions ran the same cases, so per-case differences
  are the unit of analysis. Pairing removes case-difficulty variance and is why
  the paired tests below apply.

## 2. Choosing the test

| Metric shape | Test | Notes |
| :--- | :--- | :--- |
| Binary per case (pass/fail, task success) | **McNemar** | Uses only the discordant pairs (case passed under one version, failed under the other) |
| Continuous (latency, cost, ROUGE/similarity) | **Paired t-test** | If per-case differences look roughly normal |
| Continuous, non-normal or outlier-heavy | **Wilcoxon signed-rank** | Rank-based, robust default when in doubt |
| Ordinal (1–5 rubric scores from judges) | **Wilcoxon signed-rank** | Ordinal data; means are already suspect |
| Ratios, composite scores, small samples | **Bootstrap resampling** | Resample cases to build an empirical CI for the difference |

Independent-sample variants (chi-squared, two-proportion z-test) apply only when
the two versions ran *different* case sets — avoid that situation; pairing is
strictly more sensitive.

## 3. Interpreting p-values and confidence intervals

- **p-value**: probability of a difference at least this large if the versions
  were truly identical. Conventional significance bar: p < 0.05.
- **Confidence interval on the difference** is more informative than p alone:
  a 95% CI of [+0.02, +0.08] on success rate says "somewhere between 2 and 8
  points better". **A CI containing zero = no detected difference**, whatever
  the point estimates say.
- Significant ≠ important: with enough cases, a 0.2-point latency regression is
  "significant". The threshold (below) decides importance; the test only decides
  whether the difference is real.
- Gating several metrics at once inflates false alarms (five independent 5%
  tests ≈ 23% chance one trips by luck). Keep the *blocking* metric list short;
  report the rest without blocking.

## 4. Setting thresholds

Two forms, both defined in the eval plan **before** results exist:

- **Absolute floor** — "task success ≥ 0.90", "safe-refusal rate on the
  adversarial slice = 1.0". Candidate must clear it regardless of baseline.
- **Regression bound** — "hallucination rate must not rise more than 2 points
  vs baseline, and the rise must be statistically significant to block."

Combine: block when the candidate breaches a floor, **or** shows a significant
regression beyond the bound. This lets harmless noise through while stopping
real damage.

## 5. Run-count guidance

- 3–5 full-suite runs per version is the practical floor for stable aggregates;
  high-variance metrics (LLM judges) may need more.
- More cases beat more reruns for detecting small differences — reruns shrink
  measurement noise, cases shrink sampling error. If the gate must detect a
  2-point change, dozens of cases are not optional.
- Compute the per-case score as the mean over runs, then run the paired test
  over cases. This keeps the pairing structure and uses all the data.
- The Gen AI evaluation service reports per-metric `mean` and `standard
  deviation` — persist both; the standard deviation is the noise floor that says
  whether an observed delta could be luck.

## 6. Worked example

Suite: 60 cases, 3 runs per version. Gating metric: task success (binary per
case, majority over runs).

1. Baseline passes 51/60; candidate passes 48/60.
2. Discordant pairs: 7 cases flipped pass→fail, 4 flipped fail→pass. McNemar on
   (7, 4): p ≈ 0.55 — not significant; the CI on the -3-case difference
   comfortably contains zero.
3. Verdict: no detected regression. The gate passes — but 3 net-new failures at
   p ≈ 0.55 with only 60 cases also means the suite can't yet detect changes
   this small. If 3 points matters, grow the case count; don't tighten the
   p-bar and start blocking on noise.
