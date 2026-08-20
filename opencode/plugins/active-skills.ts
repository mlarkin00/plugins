// active-skills — Stop → event(session.idle)
// Checks for plugin updates at most once every 6 hours.
// Ported from hooks.json (Antigravity): Stop → agy_check_updates.py
//
// The script handles its own throttling (6h gate via a timestamp file) and
// spawns the actual checker detached, so this hook is a thin trigger.
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

// Resolve repo root from this file's location (following symlinks).
// This file lives at <repo>/opencode/plugins/active-skills.ts → repo root is ../..
const __filename = fs.realpathSync(fileURLToPath(import.meta.url));
const __dirname = path.dirname(__filename);
const PLUGINS_REPO = path.resolve(__dirname, "..", "..");

const IDLE_THRESHOLD = 1; // run on first idle event per plugin lifetime
let runCount = 0;

export default async function ({ $ }) {
  const script = path.join(PLUGINS_REPO, "active-skills", "scripts", "agy_check_updates.py");

  return {
    "event": async (input) => {
      if (input.event?.type !== "session.idle") return;
      if (runCount >= IDLE_THRESHOLD) return;
      runCount++;
      try {
        await $`python3 ${script}`.quiet().nothrow();
      } catch {
        // Fail-open: an update check must never break the session
      }
    },
  };
}
