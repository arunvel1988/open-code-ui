#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"


for cmd in python3 curl; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "Missing $cmd. Run: sudo apt-get install -y python3 python3-venv python3-pip curl"; exit 1; }
done

mkdir -p "$HOME/projects" "$HOME/.config/opencode" "$HOME/.local/share/opencode"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

if [[ ! -f .env ]]; then cp .env.example .env; fi
if grep -q 'CHANGE_THIS' .env; then
  echo "Edit .env and replace all CHANGE_THIS values first."
  echo "Generate each secret using: openssl rand -hex 32"
  exit 1
fi

export HOME
curl -fsSL https://opencode.ai/install | bash
if [[ ! -x "$HOME/.opencode/bin/opencode" ]]; then
  echo "OpenCode installer did not create $HOME/.opencode/bin/opencode"
  exit 1
fi
"$HOME/.opencode/bin/opencode" --version

mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/opencode-command-center.service" <<EOF
[Unit]
Description=OpenCode Command Center (native Ubuntu process)
After=network.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
Environment=HOME=$HOME
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/run-dashboard.sh
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now opencode-command-center.service

echo
echo "Installed natively on Ubuntu. No Docker used."
echo "Dashboard: http://<UBUNTU-VM-IP>:5000"
echo "Dashboard bind: 0.0.0.0:5000"
echo "OpenCode API bind: 0.0.0.0:4096 (password protected)"
echo "Allow inbound TCP 5000 from your IP. Do not expose 4096 publicly."
echo "Logs: journalctl --user -u opencode-command-center -f"
