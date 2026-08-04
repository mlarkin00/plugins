#!/usr/bin/env bash
# Disable and uninstall the hourly git polling systemd timer for mlarkin00/plugins.
# NOTE: This refresh systemd service should ONLY be used with Jetski and Antigravity.
# It should NOT be used with clients that have proper marketplace/plugin install/update (e.g. Claude Code).
set -euo pipefail

SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

systemctl --user disable --now mlarkin00-plugins-poll.timer 2>/dev/null || true
systemctl --user disable --now mlarkin00-plugins-poll.service 2>/dev/null || true
rm -f "${SYSTEMD_USER_DIR}/mlarkin00-plugins-poll.service"
rm -f "${SYSTEMD_USER_DIR}/mlarkin00-plugins-poll.timer"
systemctl --user daemon-reload

echo "Successfully uninstalled mlarkin00-plugins-poll.timer"
