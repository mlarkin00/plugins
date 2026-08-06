---
name: agent-eval-design
description: Design an evaluation strategy for a GCP AI agent before writing any eval code — choose metrics across outcome, trajectory, operational, and safety dimensions; pick scorer types (code-based rules, LLM-as-judge, human review); and plan a golden dataset with adversarial coverage. Use when the user asks how to evaluate an ADK, Vertex AI, Agent Engine, or Gemini Enterprise agent, what metrics to use, how to build a golden or test dataset for an agent, or wants an eval plan or eval strategy for an AI agent. Not for evaluating Claude Code skills (use skill-creator-enhanced), writing agent eval code (use agent-eval-implement), or executing agent evals (use agent-eval-run).
---

# Agent Eval Design

Produce a written eval plan for an AI agent **before any eval code exists**. This is
Evaluation-Driven Development (EDD): define what "good" looks like first, so the
evals become the specification the agent is built and improved against. Agents can
reach a correct answer through a broken process, so the plan must cover the *path*
(trajectory) as well as the *destination* (final response) — plus what it cost to
get there and whether it was safe.

The output of this skill is an **eval plan document** (template below) that
`agent-eval-implement` turns into runnable assets and `agent-eval-run` executes.

## Step 1 — Establish context

Ask (or extract from the conversation) before choosing anything:

- What is the agent's task, and what does user success look like in one sentence?
- What tools does it call? Is there a single correct tool sequence for typical
  tasks, or many valid paths?
- Is it RAG-backed? Multi-turn? Which failures are expensive (wrong answer, wrong
  action, unsafe output, slow/costly response)?
- Where does it run — ADK locally, deployed on Agent Engine, or another framework?
  This decides the implementation path later, not the design.

## Step 2 — Choose analysis levels and scope

| Level | What it tells you | When to include |
| :--- | :--- | :--- |
| End-to-end (final response) | Did the user get the right outcome? | Always |
| Trajectory / step-level | Did the agent take a sane, efficient path — right tools, right arguments, right order? | Whenever the agent calls tools (i.e., almost always) |
| Offline (curated dataset) | Regression safety before deploy | Always |
| Online (live traffic) | Real-user quality, unknown unknowns | Once the agent is deployed; plan it now, build it later |

End-to-end alone hides root causes; trajectory alone can pass a broken answer.
Plan both.

## Step 3 — Select metrics

Pick a small set from each applicable category — a single score always lies about
an agent. Full catalog with the concrete public metric names that implement each:
`references/metric-taxonomy.md`.

| Category | Core examples | Include when |
| :--- | :--- | :--- |
| Outcome | task success, factual correctness, semantic match to reference | Always |
| Trajectory & tool use | tool selection/argument accuracy, trajectory match (exact / in-order / any-order), efficiency | Agent calls tools |
| RAG | faithfulness/groundedness, context precision & recall | RAG-backed agents only |
| Operational | latency, cost/tokens, tool-call failure rate | Always (cheap — often captured automatically) |
| Quality & safety | hallucination, policy adherence, safe refusal under attack | Always; weight by risk profile |

## Step 4 — Choose a scorer per metric

| Scorer | Use for | Cost / fidelity |
| :--- | :--- | :--- |
| Code-based rules (exact match, trajectory match, ROUGE, JSON/format checks) | Objective, deterministic checks; CI gates | Cheap, fast, predictable |
| LLM-as-judge against a rubric | Semantic correctness, response quality, reasoning coherence | Moderate cost; needs rubric + calibration |
| Human review | Ambiguous cases, business-critical sign-off, calibrating the judges | Gold standard; use sparingly and deliberately |

Two rules that prevent silent bias: never judge an agent with the same model family
that powers it (self-preference bias), and calibrate any LLM judge against a small
human-labeled sample before trusting it in a gate.

## Step 5 — Plan the golden dataset

The eval is only as good as its dataset. Blend three sourcing methods — detail and
sampling strategies in `references/golden-dataset-methods.md`:

1. **Production traces** — real sessions, both happy-path and failures. Every
   confirmed production failure becomes a permanent regression case. Scrub PII
   before anything else.
2. **Manual authoring** — subject-matter experts write the critical user journeys,
   the ideal final response, and the ideal tool sequence (the "golden trajectory").
   Include questions the agent must *refuse* or admit it cannot answer.
3. **Synthetic generation** — an LLM expands a human-authored seed set for
   coverage and cold-start; anchor generation in the agent's actual tools and
   user personas, or it produces shallow repetition.

Coverage checklist: happy paths, edge cases, out-of-scope/unanswerable queries,
and adversarial inputs (prompt injection, jailbreak, tool misuse — see
`references/adversarial-testing.md`). Version the dataset like code; a result that
can't name its dataset version is not reproducible.

## Step 6 — Set thresholds and baselines

Decide pass/fail *now*, not after seeing results — post-hoc thresholds always
drift toward whatever the agent already scores. State each as a checkable rule:
an absolute floor ("task success ≥ 0.9") or a regression bound ("hallucination
rate must not rise more than 2 points vs baseline"). Agents are non-deterministic,
so thresholds gate *aggregates over multiple runs*, never a single run —
`agent-eval-run` covers the statistics.

## Step 7 — Write the eval plan

Produce this document and hand it to `agent-eval-implement`:

```markdown
# Eval Plan: <agent name>
## Agent context      — task, tools, RAG/multi-turn, runtime, risk profile
## Analysis levels    — end-to-end / trajectory; offline now, online at deploy
## Metrics & scorers  — table: metric | category | scorer | rationale
## Golden dataset     — sources, target size, coverage checklist, versioning home
## Adversarial plan   — attack types in scope, expected safe behavior
## Thresholds         — metric | floor or regression bound | gate (PR / deploy)
## Open questions
```

Exact API signatures and metric names change: verify against live docs
(google-developer-knowledge MCP first, context7 second) when implementing.

## Gotchas & Anti-Patterns

| Excuse | Reality |
| :--- | :--- |
| "The final answers look right, so the agent works." | Agents reach right answers via broken, costly, or unsafe paths. Trajectory metrics exist because outcome metrics can't see the path. |
| "One accuracy score is enough to start." | A single metric gets optimized at the expense of everything unmeasured. Pick at least outcome + trajectory + one safety signal. |
| "We'll define thresholds once we see the numbers." | Post-hoc thresholds ratify the status quo. EDD means the bar exists before the code. |
| "The judge model can be the same Gemini the agent uses." | Self-preference bias inflates scores. Use a different family, and calibrate against human labels. |
| "Synthetic data can cover everything; it's cheaper." | Ungrounded generation produces shallow paraphrases. Seed with real traces and SME-authored cases. |
| "Adversarial cases can wait until the security review." | Prompt injection is the #1 LLM application risk; untested refusal behavior is unknown behavior. Put attacks in the first dataset. |
| "The user asked about evaluating a 'skill', close enough." | Claude Code skills are measured by skill-creator-enhanced. This skill is for GCP AI agents. |
