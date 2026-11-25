# OpenCode Command Center — UI-managed edition

A self-hosted Flask dashboard that manages an OpenCode installation **inside its own Docker container**. After the dashboard is bootstrapped, use the browser UI to install OpenCode, start/stop its server, connect API-key providers, create sessions, send prompts, inspect project files, connect GitHub, and commit/push local changes.

## What is and is not terminal-free

- You do **not** need to run `export PATH`, `opencode serve`, `/connect`, or other OpenCode commands manually. The UI installs and starts OpenCode inside the application container.
- There is one unavoidable initial bootstrap step: Docker Compose must start the Flask web application. You can run `docker compose up -d --build` once. After that, OpenCode installation and lifecycle are controlled from the UI.
- This OpenCode installation is isolated inside the container and persists in Docker volumes (`opencode-home` for OpenCode home/config/auth and `opencode-data` for dashboard settings/logs). It does not manage or replace a separate OpenCode installation on the Ubuntu host.
- GitHub push expects the selected project directory to be a local Git repository with an `origin` remote and working Git authentication. GitHub username/token are used for GitHub API actions (account test, list/create repos); the PAT is not silently injected into Git remotes.
- Prompt responses currently return after the OpenCode API request completes; this first version is not token-by-token streaming. File browser is a top-level listing, not a full editor.

## 1. Bootstrap the web UI

On Ubuntu, ensure Docker Engine and the Compose plugin are installed. Extract the ZIP, then:

```bash
cd opencode-command-center
cp .env.example .env
```

Edit `.env` and set a strong `DASHBOARD_PASSWORD` and `FLASK_SECRET_KEY` (generate a secret with `openssl rand -hex 32` if desired). Set `HOST_PROJECT_DIR` to the absolute host directory you want OpenCode to work in. The host directory is mounted in the container as `/workspace`.

Start the dashboard once:

```bash
docker compose up -d --build
```

Open `http://127.0.0.1:5000` on the Ubuntu machine. To access it from your laptop, use an SSH tunnel:

```bash
ssh -L 5000:127.0.0.1:5000 ubuntu@YOUR_VM_IP
```

Then open `http://127.0.0.1:5000` on your laptop. The dashboard binds to localhost by default. Do not expose it publicly without HTTPS, authentication hardening and firewall controls.

## 2. Use the UI

1. Sign in with `DASHBOARD_PASSWORD`.
2. Open **OpenCode Engine** and click **Install OpenCode**.
3. Click **Start**. The default model is set automatically to `opencode/big-pickle` (Big Pickle).
4. Start a new session and send a prompt. No API key is needed for Big Pickle while it remains in OpenCode's free model catalog.
5. To use another model, connect its provider key, enter a valid `provider/model` ID in **Default model ID**, save, then start OpenCode again.
6. Use the workspace, recent sessions, project file list, and optional GitHub tools.

Ollama generally uses a local endpoint and can require provider configuration; it is not automatically installed by this project.

## GitHub

Enter your GitHub username and a fine-grained Personal Access Token in the UI. Grant the minimum permissions needed. Repository creation requires permission to create repositories; pushing requires Contents read/write on the target repository. Create or select a repository, and ensure the mounted project folder has an `origin` remote and working Git credentials. Review changes before clicking commit/push.

The GitHub token is stored in `data/settings.json` with filesystem mode 0600; it is **not encrypted**. Protect the VM, disk and backups. Do not commit `.env` or `data/settings.json`.

## Security and limitations

- OpenCode server listens only on container loopback port 4096; it is not published on the host.
- Dashboard is bound to `127.0.0.1:5000` by default. Use an SSH tunnel for remote access.
- The app can run prompts that lead OpenCode to modify project files. Review changes and maintain Git checkpoints.
- This is a starter implementation, not a security-audited production product. Review code before use. Protect credentials and backups.


## Big Pickle default

The app writes the OpenCode global config at `~/.config/opencode/opencode.json` inside the persistent OpenCode home volume, setting `"model": "opencode/big-pickle"`. OpenCode documents this `provider/model` format. Big Pickle is listed as free for a limited time, so availability can change. OpenCode's Console documentation says data sent to Big Pickle during its free period may be used to improve the model. If unavailable, connect another provider and set its `provider/model` ID in the UI.

## Data volume and permissions

Dashboard settings and logs now use the named Docker volume `opencode-data`, not a host bind mount. This addresses the previous `/app/data/opencode-server.log` permission error caused by the non-root container user writing into a host-owned `./data` directory. OpenCode binaries, config and credentials remain in `opencode-home`.


## Workspace permission fix

This build runs the manager container as root (`user: "0:0"`) so it can create and edit files in `/workspace` even when the host directory belongs to a different numeric UID/GID. This addresses Docker bind-mount errors such as `Permission denied: '/workspace'`. OpenCode home and dashboard data remain in separate named Docker volumes. The project folder is still mounted at `/workspace`, so changes are visible on the host.

This is intended for a trusted, single-user machine. Keep the dashboard bound to `127.0.0.1` unless protected by authenticated HTTPS. Do not expose it directly to the public internet.

## Upgrade without losing OpenCode setup

From the project directory:

```bash
docker compose down
docker compose up -d --build
```

Do **not** run `docker compose down -v`; that deletes persistent OpenCode home and data volumes. This version stores dashboard data in the named `opencode-data` volume instead of a host `./data` bind mount.


## Automatic engine startup

When the dashboard opens, it now loads saved settings, checks whether OpenCode is installed, starts the OpenCode server automatically if needed, and only then loads sessions and models. This avoids the first-page-load race where the Recent Sessions panel requested `/session` before the engine was started. If the engine is not installed, use Install first. If startup fails, the manager displays the server log details.


## Startup/install reliability fix

The installer now runs under non-login `bash -c` with `HOME=/home/appuser`. The previous `bash -lc` login shell could reset HOME to `/root` while the manager expected the binary under `/home/appuser/.opencode/bin/opencode`. The dashboard now automatically installs OpenCode into the persistent `opencode-home` volume if the binary is missing, then starts the server before requesting sessions or models. It also makes the binary executable and can migrate a legacy `/root/.opencode/bin/opencode` binary if one exists in the running container.


## Chat response rendering

The dashboard now displays only OpenCode message parts whose API type is `text`. Reasoning, tool-call, and other internal event parts are excluded from both new responses and session history. The browser uses DOM `textContent` for assistant output, so model text is escaped safely, and newline characters render as actual line breaks rather than the literal characters `\\n`. If OpenCode returns no text part, the UI reports a useful message instead of dumping the raw API JSON.
