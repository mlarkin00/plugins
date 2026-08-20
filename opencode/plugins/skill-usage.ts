// skill-usage — PostToolUse(Skill) + SessionEnd → tool.execute.after(skill) + event(session.idle)
// Counts how often each skill is invoked and flushes counts to a git repo.
//
// Ported from:
//   hooks/hooks.json (Claude): PostToolUse → track-usage.py, SessionEnd → sync-usage.py
//   hooks.json (Antigravity): PostToolUse → track-usage-agy.py, Stop → sync-usage.py
//
// opencode has a "skill" tool (invoked via skill(name="...")), so tracking
// works by hooking tool.execute.after with tool === "skill". The skill name
// is in input.args.name — equivalent to Claude Code's tool_input.skill.
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

// Resolve repo root from this file's location (following symlinks).
// This file lives at <repo>/opencode/plugins/skill-usage.ts → repo root is ../..
const __filename = fs.realpathSync(fileURLToPath(import.meta.url));
const __dirname = path.dirname(__filename);
const PLUGINS_REPO = path.resolve(__dirname, "..", "..");

const SYNC_INTERVAL = 30 * 60 * 1000; // 30 minutes — matches Antigravity's --min-interval 1800
let lastSync = 0;

export default async function ({ $ }) {
  const trackScript = path.join(PLUGINS_REPO, "skill-usage", "scripts", "track-usage.py");
  const syncScript = path.join(PLUGINS_REPO, "skill-usage", "scripts", "sync-usage.py");

  return {
    // Increment a skill's counter when the skill tool is used
    "tool.execute.after": async (input) => {
      if (input.tool !== "skill") return;
      const skillName: string | undefined = input.args?.name;
      if (!skillName) return;

      // track-usage.py expects Claude Code's hook payload format:
      // {"tool_name": "Skill", "tool_input": {"skill": "<name>"}}
      const payload = JSON.stringify({
        tool_name: "Skill",
        tool_input: { skill: skillName },
      });
      try {
        await $`echo ${payload} | python3 ${trackScript}`.quiet().nothrow();
      } catch {
        // Fail-open: a tracking error must never block a skill call
      }
    },

    // Flush accumulated counts to the git repo (throttled)
    "event": async (input) => {
      if (input.event?.type !== "session.idle") return;
      const now = Date.now();
      if (now - lastSync < SYNC_INTERVAL) return;
      lastSync = now;
      try {
        await $`python3 ${syncScript} --min-interval 1800`.quiet().nothrow();
      } catch {
        // Fail-open: a sync error must never break the session
      }
    },
  };
}
