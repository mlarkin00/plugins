# Online Evals and Production Monitoring

Offline suites measure the cases someone imagined. Live traffic contains the
rest. Online evaluation samples and scores real interactions to detect quality
degradation near real-time and to harvest the failures that make the offline
suite grow — closing the loop between what is tested and what actually happens.

## Contents

1. Safe rollout: shadow mode
2. Asynchronous scoring pipeline
3. Observability foundation
4. Monitoring and anomaly detection
5. The improvement flywheel

## 1. Safe rollout: shadow mode

Deploy the candidate alongside production; it processes a sample of live
traffic in parallel, its responses are **logged but never shown to users**.
Compare its scored output against production's on identical real inputs —
production-grade evidence at zero user risk. Graduate through canary
(small user fraction, instant rollback) once shadow results hold.

## 2. Asynchronous scoring pipeline

Never score synchronously in the request path — evaluation adds latency and its
failures must not become user-facing failures. The pattern:

1. **Sample** sessions (all of them if volume allows; otherwise stratified by
   intent/feature, plus everything with negative user feedback).
2. **Trigger on session completion** — score conversations after an inactivity
   window closes them, via a delayed task queue (e.g., Cloud Tasks or a
   scheduler-driven sweep), so multi-turn quality is judged on whole sessions.
3. **Score asynchronously** — a worker fetches the full session trace and runs
   the scorers: cheap computation checks broadly, LLM-as-judge rubrics
   (quality, safety, task completion) on the sampled slice. Reuse the offline
   judges — calibration carries over and offline↔online scores stay comparable.
4. **Scrub PII** from scored results, then write to an analytical store
   (BigQuery) for dashboards and queries.

## 3. Observability foundation

Online evals consume traces, so instrument first: Cloud Observability tracing,
logging, and metrics for deployed agents (Agent Engine deployments emit these),
with every step — user input, reasoning, tool calls and arguments, tool
results, final response — linked by session ID. An unscorable trace is a
session that never happened, and debugging without the trace is guesswork.

## 4. Monitoring and anomaly detection

- Dashboards over the scored results: task success, safe-refusal rate, tool
  failure rate, latency and cost percentiles, user feedback — trended over
  time and sliced by intent.
- Alert on deviations from baseline (rolling-window rules or an anomaly
  detector); a quality drop showing only in a weekly report costs a week of
  degraded users.
- Watch operational and quality metrics together — a spike in tool retries or
  latency often precedes the visible quality drop, because degraded tools make
  agents improvise.

## 5. The improvement flywheel

1. **Identify** — monitoring alerts, anomaly flags, negative feedback.
2. **Analyze** — route flagged traces to review (human or triage-judge); find
   the first bad step, cluster recurring patterns.
3. **Convert** — every confirmed failure becomes a permanent golden-dataset
   case with corrected expected behavior (PII-scrubbed).
4. **Verify** — next offline run fails on the new case until fixed; the fix
   deploys; online metrics confirm.

This is what makes the offline suite converge toward reality: coverage grows
exactly where production found the holes.
