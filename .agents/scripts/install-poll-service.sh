#!/usr/bin/env bash
# Install and enable the hourly git polling systemd timer for mlarkin00/plugins.
# NOTE: This refresh systemd service should ONLY be used with Jetski and Antigravity.
# It should NOT be used with clients that have proper marketplace/plugin install/update (e.g. Claude Code).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

if [[ "${REPO_ROOT}" != "${HOME}/plugins" ]]; then
  echo "Error: mlarkin00/plugins must be located at ${HOME}/plugins to use mlarkin00-plugins-poll.service (found: ${REPO_ROOT})" >&2
  exit 1
fi

mkdir -p "${SYSTEMD_USER_DIR}"

# Create symlinks to the unit files in .agents/systemd/
ln -sf "${REPO_ROOT}/.agents/systemd/mlarkin00-plugins-poll.service" "${SYSTEMD_USER_DIR}/mlarkin00-plugins-poll.service"
ln -sf "${REPO_ROOT}/.agents/systemd/mlarkin00-plugins-poll.timer" "${SYSTEMD_USER_DIR}/mlarkin00-plugins-poll.timer"

# Reload systemd and enable/start timer
systemctl --user daemon-reload
systemctl --user enable --now mlarkin00-plugins-poll.timer

echo "Successfully installed and enabled mlarkin00-plugins-poll.timer"
echo "NOTE: This refresh systemd service is for Jetski and Antigravity only."
echo "Do not use with clients that have proper marketplace/plugin install/update (e.g. Claude Code)."
systemctl --user status mlarkin00-plugins-poll.timer --no-pager || true
