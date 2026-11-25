# OpenCode Command Center — UI-managed edition

A self-hosted Flask dashboard that manages an OpenCode installation **inside its own Docker container**. After the dashboard is bootstrapped, use the browser UI to install OpenCode, start/stop its server, connect API-key providers, create sessions, send prompts, inspect project files, connect GitHub, and commit/push local changes.

## What is and is not terminal-free

- You do **not** need to run `export PATH`, `opencode serve`, `/connect`, or other OpenCode commands manually. The UI installs and starts OpenCode inside the application container.
- There is one unavoidable initial bootstrap step: Docker Compose must start the Flask web application. You can run `docker compose up -d --build` once. After that, OpenCode installation and lifecycle are controlled from the UI.
- This OpenCode installation is isolated inside the container and persists in the `opencode-home` Docker volume. It does not manage or replace a separate OpenCode installation on the Ubuntu host.
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
3. Click **Start server**.
4. Open **Connect Provider**, select Groq (or another listed provider), and enter the provider API key. The key is sent to OpenCode's local `/auth/{provider}` API and stored by OpenCode.
5. Open **Models** to inspect configured providers. Select a model in the AI Studio through the provider/model configuration supported by the installed OpenCode version.
6. Use AI Studio, Sessions, Projects & Files, and GitHub Deploy.

Ollama generally uses a local endpoint and can require provider configuration; it is not automatically installed by this project.

## GitHub

Enter your GitHub username and a fine-grained Personal Access Token in the UI. Grant the minimum permissions needed. Repository creation requires permission to create repositories; pushing requires Contents read/write on the target repository. Create or select a repository, and ensure the mounted project folder has an `origin` remote and working Git credentials. Review changes before clicking commit/push.

The GitHub token is stored in `data/settings.json` with filesystem mode 0600; it is **not encrypted**. Protect the VM, disk and backups. Do not commit `.env` or `data/settings.json`.

## Security and limitations

- OpenCode server listens only on container loopback port 4096; it is not published on the host.
- Dashboard is bound to `127.0.0.1:5000` by default. Use an SSH tunnel for remote access.
- The app can run prompts that lead OpenCode to modify project files. Review changes and maintain Git checkpoints.
- This is a starter implementation, not a security-audited production product. Review code before use. Protect credentials and backups.
