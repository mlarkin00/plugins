# Building a Golden Dataset

A golden dataset is a curated, versioned collection of inputs with expected
outcomes (final responses and/or tool trajectories) that serves as the ground
truth for measuring agent quality. Blend all three sourcing methods; each covers
a blind spot of the others.

## Contents

1. Curate from production traces
2. Manual authoring
3. Synthetic generation
4. Coverage checklist and sizing
5. Versioning and lifecycle

## 1. Curate from production traces

Real interactions are the only source that reflects actual user behavior.

- **Instrument first.** Capture user inputs, agent reasoning steps, tool calls
  with arguments, and final responses, linked by session ID. Without trace
  capture there is nothing to curate.
- **Sample deliberately**, don't read logs linearly:
  - *Outlier detection* — sort by response length, latency, or step count;
    extremes hide failures.
  - *User feedback* — negative-feedback sessions first; each is a candidate
    regression case.
  - *Stratified sampling* — group by user type, feature, or intent so the
    dataset mirrors the production mix.
  - *Embedding clustering* — cluster query embeddings to discover request types
    nobody thought to test.
- **Scrub PII before the trace leaves the production boundary** — names, emails,
  account numbers, free-text fields. A golden dataset gets copied everywhere
  (repos, CI logs, eval dashboards); sanitize at the source.
- **Convert failures to permanent cases.** Every confirmed production failure or
  negative-feedback session becomes a regression case with the *corrected*
  expected behavior. This is the flywheel that makes eval coverage grow where it
  matters.

## 2. Manual authoring

Subject-matter experts writing cases by hand is the gold standard for nuance the
logs don't contain.

- Enumerate the **critical user journeys** — the tasks the agent absolutely must
  handle — and write cases for each.
- For each case, author the ideal **final response** and the ideal **tool
  sequence with arguments** (the golden trajectory). Trajectory metrics are only
  as good as these references.
- Include **unanswerable and out-of-scope questions** where the expected behavior
  is a graceful refusal or an honest "I can't". An agent never tested on refusal
  will improvise.
- Write **variations** — rephrasings, typos, casual register — of the same
  underlying intent to test robustness rather than memorization.

## 3. Synthetic generation

LLM-generated cases solve cold start (no production data yet) and scale coverage.

- **Anchor generation** in the agent's real tool list, its instructions, and
  named user personas. Unanchored generation converges on shallow paraphrases of
  the same three questions.
- **Seed and expand** — hand a small set of high-quality human-authored cases to
  the generator as style/coverage exemplars, then expand along explicit
  dimensions (intent × difficulty × persona × phrasing).
- **Role-play generation** — a second LLM plays the user to produce multi-turn
  conversations, useful for `multi_turn_*` metrics.
- **Back-translation** for structured tasks (e.g., NL2SQL): generate the
  structured answer first, then have an LLM write the natural-language question
  for it — labels come free.
- **Human-review the output.** Synthetic cases enter the golden set only after a
  person confirms the expected outputs; otherwise the dataset encodes the
  generator's hallucinations as ground truth.

The Gen AI evaluation service ships public demo datasets
(`gs://cloud-ai-demo-datasets/agent-eval-datasets/` — `on-device`,
`customer-support`, `content-creation`) that show the expected shape before you
have data of your own.

## 4. Coverage checklist and sizing

Every golden set needs, in rough priority order:

- [ ] Happy paths for each critical user journey
- [ ] Edge cases and known failure modes
- [ ] Out-of-scope / unanswerable queries (expected: refusal)
- [ ] Adversarial inputs (expected: safe refusal — see `adversarial-testing.md`)
- [ ] Phrasing variations of the same intents

Size: start small (10–30 cases) and honest — a small set of verified cases beats
a large set of guessed ones. Grow toward 100+ via the production-failure flywheel
and synthetic expansion. The dataset should be *demonstrative of production
usage, diverse, and evolving* — a static dataset measures the agent against last
quarter's users.

## 5. Versioning and lifecycle

- Version the dataset **like code** — in git next to the agent, or DVC/Git LFS if
  large. Every eval result must be attributable to an exact dataset version, or
  score changes can't be separated from data changes.
- Never edit a case in place after results reference it; add a new version.
- Record provenance per case (trace-derived / authored / synthetic) — when a
  metric shifts, knowing which slice moved is the first debugging question.
