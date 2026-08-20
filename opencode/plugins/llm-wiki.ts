// llm-wiki — PostToolUse → tool.execute.after
// Validates OKF §9 conformance on .md writes inside an OKF bundle.
// Ported from hooks/hooks.json (Claude) and hooks.json (Antigravity).
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

// Resolve repo root from this file's location (following symlinks).
// This file lives at <repo>/opencode/plugins/llm-wiki.ts → repo root is ../..
const __filename = fs.realpathSync(fileURLToPath(import.meta.url));
const __dirname = path.dirname(__filename);
const PLUGINS_REPO = path.resolve(__dirname, "..", "..");

export default async function ({ $ }) {
  const hookScript = path.join(PLUGINS_REPO, "llm-wiki", "hooks", "validate-on-write.sh");

  return {
    "tool.execute.after": async (input, output) => {
      if (input.tool !== "edit" && input.tool !== "write") return;
      const filePath: string | undefined = input.args?.filePath;
      if (!filePath || !filePath.endsWith(".md")) return;

      const payload = JSON.stringify({ tool_input: { file_path: filePath } });
      try {
        const result = await $`echo ${payload} | bash ${hookScript}`.quiet().nothrow();
        if (result.exitCode !== 0) {
          const err = result.stderr.toString().trim();
          if (err) {
            output.output = (output.output || "") + "\n\n---\n**OKF Validation Error:**\n" + err;
          }
        }
      } catch {
        // Fail-open: a validator error must never block a write
      }
    },
  };
}
