// memory-bank — SessionStart (load) + Stop (save) → experimental.chat.system.transform + event(session.idle)
// Loads GCP-backed long-term memories into the system prompt and saves
// conversation context for fact extraction at session idle.
//
// Ported from:
//   hooks/hooks.json (Claude): SessionStart → load_context.py, Stop → save_context.py
//   hooks.json (Antigravity): PreInvocation → agy_load_context.py, Stop → save_context.py
//
// Limitation: sidecar_consolidate.py is not run because it walks
// ~/.claude/projects/**/*.jsonl (Claude Code transcript format). opencode
// stores sessions in SQLite, not JSONL. The per-session save_context.py
// call captures new facts; bulk consolidation needs an opencode adapter.
import path from "node:path";
import fs from "node:fs";
import os from "node:os";
import { fileURLToPath } from "node:url";

// Resolve repo root from this file's location (following symlinks).
// This file lives at <repo>/opencode/plugins/memory-bank.ts → repo root is ../..
const __filename = fs.realpathSync(fileURLToPath(import.meta.url));
const __dirname = path.dirname(__filename);
const PLUGINS_REPO = path.resolve(__dirname, "..", "..");

const CACHE_TTL = 30 * 60 * 1000; // 30 minutes
const SAVE_INTERVAL = 5 * 60 * 1000; // 5 minutes per session

let cachedMemories: string | null = null;
let cacheTime = 0;
const lastSave: Map<string, number> = new Map();
const lastUploadedCount: Map<string, number> = new Map();

async function loadMemories($): Promise<string | null> {
  const now = Date.now();
  if (cachedMemories !== null && (now - cacheTime) < CACHE_TTL) {
    return cachedMemories;
  }

  const script = path.join(PLUGINS_REPO, "memory-bank", "scripts", "load_context.py");
  try {
    const result = await $`echo '{}' | python3 ${script}`.quiet().nothrow();
    const stdout = result.stdout.toString().trim();
    if (stdout) {
      const data = JSON.parse(stdout);
      cachedMemories = data?.hookSpecificOutput?.additionalContext ?? null;
    }
  } catch {
    // Fail-open: no memories is better than a broken session
  }

  cacheTime = now;
  return cachedMemories;
}

async function saveContext(client, sessionID: string, $): Promise<void> {
  const now = Date.now();
  const last = lastSave.get(sessionID) ?? 0;
  if (now - last < SAVE_INTERVAL) return;
  lastSave.set(sessionID, now);

  try {
    const result = await client.session.messages({ path: { id: sessionID } });
    const messages = result.data;
    if (!messages || !Array.isArray(messages) || messages.length === 0) return;

    // Convert opencode messages to the JSONL format save_context.py expects
    const lines: string[] = [];
    for (const msg of messages) {
      const role = msg.info?.role;
      if (role !== "user" && role !== "assistant") continue;
      const textParts = (msg.parts ?? []).filter((p) => p.type === "text");
      const text = textParts.map((p) => p.text).join("\n");
      if (text) {
        lines.push(JSON.stringify({ role, content: text }));
      }
    }

    if (lines.length === 0) return;

    // Write to a temp JSONL file that save_context.py can read
    const tmpFile = path.join(os.tmpdir(), `opencode-transcript-${sessionID}.jsonl`);
    await fs.promises.writeFile(tmpFile, lines.join("\n"));

    const script = path.join(PLUGINS_REPO, "memory-bank", "scripts", "save_context.py");
    const payload = JSON.stringify({
      transcriptPath: tmpFile,
      workspacePaths: [process.cwd()],
    });

    try {
      await $`echo ${payload} | python3 ${script}`.quiet().nothrow();
    } finally {
      await fs.promises.unlink(tmpFile).catch(() => {});
    }
  } catch {
    // Fail-open: a save error must never break the session
  }
}

async function uploadSession(client, sessionID: string, $): Promise<void> {
  try {
    const result = await client.session.messages({ path: { id: sessionID } });
    const messages = result.data;
    if (!messages || !Array.isArray(messages) || messages.length === 0) return;

    const lastCount = lastUploadedCount.get(sessionID) ?? 0;
    if (messages.length <= lastCount) return; // no growth since last upload

    // Only upload the new turns (delta since last upload). appendEvent is
    // append-only, so re-uploading a delta never duplicates earlier turns.
    const newMessages = messages.slice(lastCount);

    // Flatten new messages to JSONL with role, content, timestamp, messageId.
    // Reuses the same text-extraction logic as saveContext.
    const lines: string[] = [];
    for (const msg of newMessages) {
      const role = msg.info?.role;
      if (role !== "user" && role !== "assistant") continue;
      const textParts = (msg.parts ?? []).filter((p) => p.type === "text");
      const text = textParts.map((p) => p.text).join("\n");
      if (text) {
        lines.push(JSON.stringify({
          role,
          content: text,
          timestamp: msg.info?.time_created,
          messageId: msg.info?.id,
        }));
      }
    }

    if (lines.length === 0) {
      // All new messages were non-text — advance the count so we don't
      // re-process them on every idle.
      lastUploadedCount.set(sessionID, messages.length);
      return;
    }

    // Write the delta to a temp JSONL file that upload_session.py can read
    const tmpFile = path.join(os.tmpdir(), `opencode-session-${sessionID}.jsonl`);
    await fs.promises.writeFile(tmpFile, lines.join("\n"));

    const script = path.join(PLUGINS_REPO, "memory-bank", "scripts", "upload_session.py");
    const payload = JSON.stringify({
      sessionId: sessionID,
      transcriptPath: tmpFile,
      workspace: process.cwd(),
    });

    try {
      const shellResult = await $`echo ${payload} | python3 ${script}`.quiet().nothrow();
      const stdout = shellResult.stdout.toString().trim();
      // Only advance the growth gate if the script ran to completion (it
      // prints a JSON summary on stdout). No output means it failed early
      // (no auth, no config, can't read file) — don't advance, so the next
      // idle re-attempts the same delta. appendEvent is append-only, so a
      // partial run that did append some events will produce duplicates on
      // retry — the memory-minion curator handles those.
      if (stdout) {
        lastUploadedCount.set(sessionID, messages.length);
      }
    } finally {
      await fs.promises.unlink(tmpFile).catch(() => {});
    }
  } catch {
    // Fail-open: an upload error must never break the session
  }
}

export default async function ({ client, $ }) {
  return {
    // Inject long-term memories into the system prompt before each LLM call
    "experimental.chat.system.transform": async (_input, output) => {
      const memories = await loadMemories($);
      if (memories) {
        output.system.push(memories);
      }
    },

    // Save conversation context when the session goes idle
    "event": async (input) => {
      if (input.event?.type !== "session.idle") return;
      const sessionID = input.event?.properties?.sessionID;
      if (!sessionID) return;
      await saveContext(client, sessionID, $);
      await uploadSession(client, sessionID, $);
    },
  };
}
