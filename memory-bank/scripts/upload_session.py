"""Upload an opencode session transcript to the Agent Engine Session Service.

Creates (or gets) a Session on the same reasoningEngines resource the Memory
Bank uses, then appends each conversation turn as a SessionEvent. This stores
the raw, ordered transcript — complementing save_context.py, which extracts
atomic facts via memories:generate from the same conversation.

Called from opencode/plugins/memory-bank.ts on session.idle (growth-gated).
stdin: JSON {"sessionId": "ses_...", "transcriptPath": "/tmp/...jsonl",
             "workspace": "/path/to/cwd"}
transcript file: JSONL, one line per turn:
  {"role": "user"|"assistant", "content": "text",
   "timestamp": "...", "messageId": "..."}

Fail-open: every error is swallowed and the script exits 0. Prints a JSON
summary on stdout when it runs to completion, so the TS caller can advance
its growth gate. No output means the script failed early — the caller
retries the same delta on the next idle (append-only, so no duplicates
from a partial run; the curator handles any that do arise).

Session-end consolidation is always global scope, matching save_context.py.
The scope model maps to the Session Service as: userId = resolve_user_id()
(the gcloud-account SHA-256 hash), labels.project = "global".
"""

import sys
import os
import json
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from resolve_scope import resolve_user_id
from config import get_plugin_config


def get_access_token():
    """Fetch an ADC bearer token via gcloud."""
    try:
        import subprocess
        p = subprocess.run(
            ['gcloud', 'auth', 'application-default', 'print-access-token'],
            capture_output=True, text=True, check=True
        )
        return p.stdout.strip()
    except Exception:
        return None


def api_request(url, payload, project, token):
    """Make an authenticated POST to the GCP API. Returns parsed JSON or None."""
    headers = {
        "Content-Type": "application/json",
        "X-Goog-User-Project": project,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode('utf-8'))
    except Exception as e:
        print(f"Error in API request to {url}: {e}", file=sys.stderr)
        return None


def create_session(base_url, project, token, session_id, user_id, project_label):
    """Create or get a Session. Idempotent via ?sessionId=.

    The Session Service accepts a custom session ID in the query string, so
    re-uploading for the same opencode sessionID is a create-or-get, not a
    duplicate. A failure here is not fatal — the session may already exist
    from a prior upload, and appendEvent will reach it regardless.
    """
    url = f"{base_url}/sessions?sessionId={session_id}"
    payload = {
        "userId": user_id,
        "labels": {"project": project_label},
        "ttl": "2592000s",  # 30 days, matching the memories convention
    }
    return api_request(url, payload, project, token)


def build_event(role, content, timestamp=None, invocation_id=None):
    """Build a SessionEvent from a flattened transcript turn.

    opencode uses 'assistant' for the AI role; the Session Service expects
    author='agent' and content.role='model' for the model's turns, matching
    the Content-shape contract memories:generate already enforces
    (test_save_context.py locks the lowercase user/model convention).
    """
    if role == 'assistant':
        author = 'agent'
        content_role = 'model'
    else:
        author = 'user'
        content_role = 'user'

    event = {
        "author": author,
        "content": {
            "role": content_role,
            "parts": [{"text": content}],
        },
    }
    if timestamp:
        event["timestamp"] = timestamp
    if invocation_id:
        event["invocationId"] = invocation_id
    return event


def append_event(base_url, project, token, session_id, event):
    """Append a single conversation event to a session."""
    url = f"{base_url}/sessions/{session_id}:appendEvent"
    return api_request(url, {"event": event}, project, token)


def run():
    try:
        input_data = json.loads(sys.stdin.read())
    except Exception:
        return

    session_id = input_data.get('sessionId')
    transcript_path = input_data.get('transcriptPath')

    if not session_id or not transcript_path or not os.path.exists(transcript_path):
        return

    # Read the transcript turns (only the delta since last upload)
    turns = []
    try:
        with open(transcript_path, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    turns.append(json.loads(line.strip()))
                except (json.JSONDecodeError, TypeError):
                    continue
    except Exception:
        return

    if not turns:
        return

    cfg = get_plugin_config()
    if not cfg["project"] or not cfg["location"] or not cfg["reasoning_engine_id"]:
        return

    token = get_access_token()
    if not token:
        return

    base_url = (
        f"https://{cfg['location']}-aiplatform.googleapis.com/v1beta1"
        f"/projects/{cfg['project']}/locations/{cfg['location']}"
        f"/reasoningEngines/{cfg['reasoning_engine_id']}"
    )

    user_id = resolve_user_id()
    # Session-end consolidation is always global scope, matching save_context.py.
    project_label = "global"

    # Create or get the session (idempotent via ?sessionId=)
    create_session(base_url, cfg["project"], token, session_id, user_id, project_label)

    # Append each turn as an event
    appended = 0
    for turn in turns:
        role = turn.get('role', '')
        content = turn.get('content', '')
        if not content:
            continue
        event = build_event(
            role=role,
            content=content,
            timestamp=turn.get('timestamp'),
            invocation_id=turn.get('messageId'),
        )
        res = append_event(base_url, cfg["project"], token, session_id, event)
        if res is not None:
            appended += 1

    # Signal completion so the TS caller can advance its growth gate.
    # No output means "failed early" — the caller retries the same delta.
    print(json.dumps({"appended": appended, "sessionId": session_id}))


if __name__ == '__main__':
    try:
        run()
    except Exception:
        pass  # fail-open: never break the session
