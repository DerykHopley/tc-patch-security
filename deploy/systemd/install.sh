#!/usr/bin/env bash
# Install the scheduled refresh as a systemd user timer (B03, #36). It copies the two units, with this checkout's
# backend/ folder and uv filled in, to ~/.config/systemd/user/ and reloads systemd. It does not start the timer:
# the last lines it prints say how.
#
#   deploy/systemd/install.sh              install, then reload systemd
#   deploy/systemd/install.sh --no-reload  only write the files (the test uses this)
#
# UV=/path/to/uv overrides the uv found on PATH. XDG_CONFIG_HOME is honoured.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
backend="$(cd "$here/../../backend" && pwd)"
uv="${UV:-$(command -v uv || true)}"
if [[ -z "$uv" ]]; then
  echo "uv isn't on PATH. Install it (https://docs.astral.sh/uv/) or set UV=/path/to/uv." >&2
  exit 1
fi
dest="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$dest"

for unit in patch-refresh.service patch-refresh.timer; do
  sed -e "s|@BACKEND@|$backend|g" -e "s|@UV@|$uv|g" "$here/$unit" > "$dest/$unit"
  echo "Wrote $dest/$unit"
done

if [[ ! -f "$backend/.env" ]]; then
  echo "Note: $backend/.env doesn't exist yet. The refresh reads DATA_MODE=live and FEEDS=real from it." >&2
elif ! grep -q '^DATA_MODE=live' "$backend/.env"; then
  echo "Note: $backend/.env doesn't set DATA_MODE=live, so each scheduled run will stop with exit code 2." >&2
fi

if [[ "${1:-}" != "--no-reload" ]]; then
  systemctl --user daemon-reload
fi

cat <<EOF

Installed, not started. To start the hourly timer:
  systemctl --user enable --now patch-refresh.timer
Check it:  systemctl --user list-timers patch-refresh.timer
A run now: systemctl --user start patch-refresh.service && journalctl --user -u patch-refresh.service -n 30
To run while you're logged out: loginctl enable-linger
To remove: systemctl --user disable --now patch-refresh.timer, then delete the two files in $dest
EOF
