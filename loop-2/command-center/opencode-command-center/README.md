# OpenCode Command Center — Native Ubuntu Edition

A native Ubuntu application. **No Docker, Docker Compose, containers, or Kubernetes.**

- Flask dashboard: `0.0.0.0:5000`
- OpenCode API server: `0.0.0.0:4096`
- OpenCode binary: `$HOME/.opencode/bin/opencode`
- Python dependencies: isolated `.venv`
- Process manager: user-level systemd service

## Install

Run as your normal Ubuntu user, not root:

```bash
unzip opencode-command-center-native-fixed.zip
cd opencode-command-center
sudo apt-get update
sudo apt-get install -y curl python3 python3-venv python3-pip
cp .env.example .env
nano .env
```

Set three strong, different secrets:

```bash
DASHBOARD_PASSWORD=<dashboard-login-password>
FLASK_SECRET_KEY=<random-secret>
OPENCODE_PASSWORD=<different-random-opencode-api-password>
```

Generate each secret with `openssl rand -hex 32`. Keep `BIND_IP=0.0.0.0`, `PORT=5000`, and `OPENCODE_URL=http://localhost:4096`.

Then:

```bash
bash install.sh
```

The installer installs OpenCode directly into your Ubuntu user's home, creates a Python virtual environment, and registers a native user systemd service. It does not install or use Docker.

## Open the dashboard

Browse to:

```text
http://<YOUR-UBUNTU-VM-PUBLIC-IP>:5000
```

Sign in with `DASHBOARD_PASSWORD`.

The Flask server listens on all network interfaces. Allow inbound TCP 5000 in the Ubuntu firewall and cloud firewall/security group. Restrict the source to your own public IP. Do not expose port 4096 publicly; the OpenCode API is password-protected and intended for the dashboard's internal connection.

## Provider integration

The dashboard supports Groq, OpenAI, Anthropic, Google AI Studio, and OpenRouter.

1. Choose the provider and paste its API key.
2. The dashboard checks the key against that provider's actual models endpoint before saving.
3. If the key is invalid or the provider is unreachable, it reports the provider error and does not save the key.
4. After validation, the key is stored in `data/settings.json` with owner-only permissions.
5. Restart OpenCode so the provider environment variable is loaded into the native OpenCode process.
6. Set the default model using the exact `provider/model-id` from OpenCode's `/api/models` response. Do not guess model IDs.

Provider keys are passed to OpenCode using supported environment variables: `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_GENERATIVE_AI_API_KEY`, or `OPENROUTER_API_KEY`. A provider key is not itself a model selection: choose a model belonging to that provider.

## Service management

```bash
systemctl --user status opencode-command-center
systemctl --user restart opencode-command-center
systemctl --user stop opencode-command-center
journalctl --user -u opencode-command-center -f
```

Enable lingering so the user service can run after logout/reboot:

```bash
sudo loginctl enable-linger "$USER"
```

## Useful checks

```bash
ss -lntp | grep -E ':5000|:4096'
curl -I http://localhost:5000
curl -u "opencode:$OPENCODE_PASSWORD" http://localhost:4096/global/health
$HOME/.opencode/bin/opencode --version
```

Keep `.env` and `data/settings.json` private. The dashboard can run code-changing agent actions inside the selected project; use Git and review changes.
