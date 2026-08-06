# Custom LLM-as-Judge Scorers

An LLM-as-judge scores agent output against a written rubric. It is the scorer
for qualities code can't check — semantic correctness, reasoning coherence,
refusal quality — and it is only as trustworthy as its rubric and calibration.

## Contents

1. When to build a custom judge
2. Rubric design rules
3. Trajectory-judge template
4. Pointwise vs pairwise
5. Judge model selection
6. Calibration
7. Implementation notes

## 1. When to build a custom judge

Reach for the built-ins first: ADK's rubric-based criteria
(`rubric_based_final_response_quality_v1`, `rubric_based_tool_use_quality_v1`)
accept custom rubrics without custom plumbing, and the evaluation service's
`PointwiseMetricPromptTemplate` covers most single-quality judgments (see
`vertex-eval-service.md` §5). Build fully custom only when the judgment needs
inputs the built-ins don't accept (full traces, external context) or output
structure they don't produce.

## 2. Rubric design rules

- **One quality per rubric.** A rubric scoring correctness *and* tone *and*
  efficiency produces middle scores that mean nothing. Three qualities = three
  rubrics = three interpretable scores.
- **Anchor every score level with an observable description.** "5: all tool
  calls relevant and necessary; 3: some calls inefficient but not incorrect;
  1: wrong tools or a necessary tool missing." Unanchored 1–10 scales measure
  the judge's mood.
- **Demand an explanation with the score.** It exposes judge misreadings during
  calibration and is the first thing a human reads when triaging a failure.
- **Prefer coarse scales** (1–5, or binary + explanation). Judges cannot
  reliably distinguish a 7 from an 8; forcing precision adds noise, not signal.
- **State the inputs explicitly** in the prompt — question, trajectory, response,
  context — and instruct the judge to use only them.

## 3. Trajectory-judge template

Adapt per quality being judged (this one bundles three for illustration — split
into separate judges for gating use):

```text
You are a meticulous and fair AI agent evaluator. Given a user's question and
the agent's execution trajectory, score the following, each 1-5, each with a
brief justification:

1. Tool Selection (5: every call relevant and necessary; 3: inefficient but not
   incorrect; 1: wrong tool called or a necessary tool never called)
2. Tool Inputs (5: all arguments correct and well-formed; 3: minor formatting
   issues; 1: incorrect or hallucinated arguments)
3. Efficiency (5: minimal steps; 3: roundabout but converging; 1: circular or
   stalled)

Finally classify the trajectory Correct/Incorrect for answering the question,
with an explanation.

User Question: {question}
Agent Trajectory: {trajectory}
```

A judge with trajectory access catches what outcome scoring can't: an
unnecessary tool call lowers Efficiency even when the final answer is right.

## 4. Pointwise vs pairwise

- **Pointwise** (score one output against the rubric) — for absolute quality
  bars and CI thresholds. This is what gates need.
- **Pairwise** (A vs B, which is better) — for comparing agent versions or
  prompts; more sensitive to small differences, but yields a preference, not a
  threshold. Randomize A/B position — judges have position bias.

## 5. Judge model selection

- Use a high-capability model tier for judging; weak judges dominate the error
  budget. Look up the current recommended model tier at implementation time —
  never hardcode a model ID into eval infrastructure.
- **Different family than the agent under test.** Same-family judges score their
  relatives higher (self-preference bias). If the agent is Gemini-powered, the
  bias-free option is a judge from another family; where policy requires staying
  in-family, calibrate extra carefully and revisit gates that sit near the
  threshold.
- Temperature 0 (or the lowest available) for score stability.

## 6. Calibration

Before a judge gates anything:

1. Have a human label 20–50 representative cases (include known-bad ones).
2. Run the judge on the same cases; compare (agreement rate, or correlation for
   scalar scores).
3. Disagreements → fix the rubric (usually: anchors too vague, or two qualities
   bundled), not the judge's individual scores.
4. Re-check periodically and whenever the rubric, judge model, or agent domain
   changes. An uncalibrated judge is an unvalidated metric wearing a numeric
   costume.

## 7. Implementation notes

- Parse defensively: instruct the judge to emit structured output (JSON with
  `score` and `explanation`), validate it, and retry on malformed output rather
  than defaulting the score to 0 or 1 silently.
- Log judge inputs and raw outputs with the results — un-reproducible judgments
  can't be debugged.
- Judges add real cost and latency per case; in CI, run computation metrics on
  every case and reserve judges for the slices that need them.
