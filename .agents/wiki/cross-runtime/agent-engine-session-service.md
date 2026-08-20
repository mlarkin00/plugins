---
type: Runtime Behaviour
title: The Agent Engine has a native Session Service for conversation transcripts
description: POST .../reasoningEngines/{id}/sessions + :appendEvent stores ordered
  SessionEvent records — distinct from the Memory Bank memories endpoint, which
  stores short extracted facts.
tags:
- gcp
- session-service
- memory-bank
timestamp: '2026-08-20T14:30:00+00:00'
---

The Vertex AI Agent Engine (Reasoning Engine) provides a **Session Service** — a
first-class API for storing conversation history as ordered `SessionEvent` records.
It is a child resource of the same `reasoningEngines/{id}` instance the Memory Bank
uses; no separate engine deployment is required.

## Endpoints (v1beta1)

| Operation | Method & URL |
|---|---|
| Create / get session | `POST .../reasoningEngines/{id}/sessions?sessionId={custom_id}` |
| Append event | `POST .../sessions/{session_id}:appendEvent` |
| Get session | `GET .../sessions/{session_id}` |
| List events | `GET .../sessions/{session_id}/events?pageSize=100` |
| List sessions | `GET .../sessions?filter=user_id="{id}"` |

The `?sessionId=` query parameter makes create idempotent — a custom
user-defined session ID (e.g. an opencode `ses_...` ID) re-used on a second call
is a create-or-get, not a duplicate.

## SessionEvent shape

```json
{
  "event": {
    "author": "user" | "agent",
    "invocationId": "inv-001",
    "timestamp": "2026-08-20T12:00:00Z",
    "content": {
      "role": "user" | "model",
      "parts": [{"text": "..."}]
    }
  }
}
```

The `content` field uses the same Content-shape contract as `memories:generate`
(`{"role": "user"|"model", "parts": [{"text": ...}]}`) — lowercase roles,
`assistant` maps to `author: "agent"` / `content.role: "model"`.

## How it differs from the Memory Bank `memories` endpoint

| | Session Service (`/sessions`) | Memory Bank (`/memories`) |
|---|---|---|
| Purpose | Raw conversation history (ordered events) | Extracted atomic facts (semantic) |
| Structure | `Session` → ordered `SessionEvent` records | `Memory` with a `fact` string + embeddings |
| Retrieval | Chronological `list` / `get` by sessionId | Semantic vector search via `:retrieve` |
| TTL | Configurable (min 24h) | Defaults to 30 days |

## Bonus integration

Once events are stored, `memories:generate` can take `vertexSessionSource:
{"session": session.name}` to extract facts *from the persisted session* —
no need to send raw content in the generate payload.

## Why this matters for this repo

The memory-bank plugin's `save_context.py` sends transcript turns inline to
`memories:generate` for fact extraction. The Session Service is the complement:
it stores the raw, ordered transcript itself. `upload_session.py` (new in this
session) uses it to preserve full opencode session transcripts without chunking
or truncation — each turn is one `appendEvent` call.

# Citations

[1] Vertex AI Agent Engine REST API reference, v1beta1 — researched via
    Google Cloud documentation and the `@opencode-ai/sdk` type definitions
    (verified 2026-08-20 against engine `3095916880561438720`).
