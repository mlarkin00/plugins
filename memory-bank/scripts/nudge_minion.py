"""Nudge the deployed memory-minion Agent Runtime to curate the Memory Bank.

Curation no longer runs in this plugin — it is done by the memory-minion agent
deployed on the GCP Agent Runtime. After the client writes memories, it fires a
best-effort, FAIL-OPEN nudge here: if it fails (agent cold, auth, network), the
agent's own 6-hour schedule still grooms the change, so nudge failures never
affect the session.

Usage:
  nudge_minion.py            fire-and-forget (detached); returns immediately
  nudge_minion.py --wait     synchronous; prints the curate summary JSON
"""

import sys
import os
import json
import subprocess
import urllib.request

# The deployed memory-minion engine's :query endpoint. Override with MINION_QUERY_URL.
DEFAULT_URL = ("https://us-west1-aiplatform.googleapis.com/v1/projects/756846227114"
               "/locations/us-west1/reasoningEngines/4732975345110614016:query")


def _url():
    return os.environ.get("MINION_QUERY_URL", DEFAULT_URL)


def _token():
    try:
        p = subprocess.run(['gcloud', 'auth', 'application-default', 'print-access-token'],
                           capture_output=True, text=True, timeout=15)
        return p.stdout.strip()
    except Exception:
        return None


def _query(timeout):
    headers = {"Content-Type": "application/json"}
    token = _token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps({"class_method": "curate", "input": {}}).encode('utf-8')
    req = urllib.request.Request(_url(), data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read().decode('utf-8')


def wait_and_print():
    """Synchronous curate; print the summary. Used by /memories-curate."""
    try:
        data = json.loads(_query(timeout=300))
        print(json.dumps(data.get("output", data)))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


def fire_and_forget():
    """Detach (double-fork) and nudge in the background; never block the caller."""
    try:
        if os.fork() > 0:
            return
    except Exception:
        # No fork (e.g. non-POSIX): best-effort inline, swallow everything.
        try:
            _query(timeout=120)
        except Exception:
            pass
        return
    try:
        os.setsid()
        if os.fork() > 0:
            os._exit(0)
    except Exception:
        pass
    try:
        _query(timeout=300)
    except Exception:
        pass
    os._exit(0)


def main():
    if "--wait" in sys.argv:
        wait_and_print()
    else:
        fire_and_forget()


if __name__ == '__main__':
    main()
