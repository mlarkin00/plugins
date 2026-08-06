# Third-Party Eval Frameworks (Optional)

Open-source frameworks that complement the GCP-native path. Reach for one when
it covers a need the native tools don't; skip this file otherwise.

## RAGAS — RAG pipeline evaluation

Component-level metrics that separate retriever failures from generator
failures: `faithfulness` (answer consistent with retrieved context — the
hallucination signal), `answer_relevancy`, `context_precision` (relevant chunks
ranked high), `context_recall` (retrieval found everything needed;
requires ground-truth answers).

RAGAS defaults to OpenAI models but accepts any LangChain-compatible LLM and
embeddings — point it at Vertex AI models (`langchain_google_vertexai`'s
`ChatVertexAI` / `VertexAIEmbeddings`, current model tier looked up at
implementation time) so the eval stack stays inside the same cloud and billing
boundary as the agent. It can also synthesize test datasets from a document
corpus — useful for cold-starting a RAG golden set.

Diagnostic pattern: low faithfulness + high context recall → generator problem;
high faithfulness + low context recall → retriever problem.

## DeepEval — pytest-style assertions

`assert_test(LLMTestCase(input=…, actual_output=…, expected_output=…),
[AnswerRelevancyMetric(threshold=0.7)])` — evals as unit tests, thresholds as
assertions. Overlaps with ADK's pytest `AgentEvaluator` wiring; prefer the ADK
path for ADK agents, DeepEval for non-ADK Python stacks already using pytest.

## TruLens — RAG triad and agent GPA

Popularized the **RAG triad** (context relevance, groundedness, answer
relevance) and offers agent-level Goal-Plan-Action ("Agent GPA") scoring for
plan correctness and adherence. Strong for instrumented, feedback-function-style
continuous scoring during development.

## LangSmith — tracing plus datasets

Tracing, dataset management, and eval runs for LangChain-family stacks. If the
agent is built on LangChain/LangGraph and deployed via Agent Engine, note the
native path also works: Agent Engine agents evaluate directly with the Gen AI
evaluation service (see `vertex-eval-service.md`), which keeps results next to
the deployment.

## Selection rule

Native first: ADK criteria and the Gen AI evaluation service cover trajectory,
response quality, safety, and hallucination for GCP agents. Add a third-party
framework for (a) RAG component diagnosis (RAGAS/TruLens), (b) a non-ADK,
non-GCP-deployed stack, or (c) an existing team investment in one of these
ecosystems.
