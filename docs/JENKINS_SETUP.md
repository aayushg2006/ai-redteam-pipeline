# Jenkins setup on Ubuntu 24.04

The Jenkinsfile runs on a Linux node with the `linux` label. It uses Python 3.12+
from the host and Python 3.13 in the application containers; the pinned
scikit-learn and joblib versions match in both environments.

## 1. Prepare the host

This machine already has Jenkins with Java 21, Docker Engine with Compose,
Google Chrome, and Ollama with `qwen2.5:3b`. Keep those services installed on the
same machine as the Jenkins build node. Jenkins needs Git, Pipeline, JUnit, and
HTML Publisher plugins (already present on this host).

From the repository root, run:

```bash
sudo bash pipeline/setup-linux.sh
```

The script installs Python venv support and a system-wide Node.js 24 runtime
when needed (the user's private nvm install is not accessible to Jenkins). Node
is downloaded from nodejs.org and checked against its SHA-256 manifest. It also
adds Jenkins to the Docker group, sets its service PATH, and restarts Jenkins
so those changes apply. Run this when no Jenkins build is in progress.
Docker group membership grants control over the host through Docker; this is
intended for this local demo machine and its trusted pipeline.

On Linux, `host.docker.internal` resolves to Docker's bridge address, while
Ollama normally listens only on `127.0.0.1`. If necessary, the script installs an
`acme-ollama-bridge` systemd service that forwards the bridge's port 11434 to
localhost. Ollama itself keeps its localhost binding; the proxy does not bind
LAN interfaces. Rerun setup if you change Docker's default bridge address.

The script finishes by checking tools, Docker access, and model availability
**as the Jenkins user**. It does not start the app or trigger a Jenkins build.

You can repeat that check separately from the repository root:

```bash
sudo -u jenkins bash -s < pipeline/check-linux.sh
```

If a check fails, fix the reported prerequisite and rerun setup. The model can
be downloaded with `ollama pull qwen2.5:3b`.

## 2. Configure the build node

1. Open http://localhost:8080 and sign in to the existing Jenkins installation.
2. Go to **Manage Jenkins → Nodes → Built-In Node → Configure** (or configure
   the Linux agent on this host).
3. Add `linux` to **Labels**, preserving any existing labels.
4. Ensure **Number of executors** is at least 1. Save.

Using the built-in node is sufficient for this local demo. A separate Linux
agent is appropriate for a shared Jenkins installation; run the host setup on
that agent instead.

## 3. Make the Linux changes available to Jenkins

The SCM job reads the Jenkinsfile from GitHub, not from this local directory.
Commit and push these changes to the branch that the job will build before
starting a build. For a Pipeline job using another branch, select that branch
in the configuration below.

## 4. Create or configure the pipeline job

**New Item → ai-redteam-pipeline → Pipeline → OK**. Under **Pipeline**:

| Setting | Value |
|---|---|
| Definition | Pipeline script from SCM |
| SCM | Git |
| Repository URL | `https://github.com/aayushg2006/ai-redteam-pipeline.git` |
| Credentials | None for a public repository; GitHub credentials for a private one |
| Branch Specifier | `*/main` (or the branch containing the Linux changes) |
| Script Path | `Jenkinsfile` |

Save. Avoid running another job that deploys this same project concurrently;
the Compose project names and deployment ports are shared on this host.

## 5. Run the pipeline when ready

Click **Build Now** and watch **Console Output**. The first stage verifies the
Linux prerequisites. Subsequent stages install dependencies, run unit tests,
train and evaluate the guardrail, build images, start the candidate on port
9000, run security and browser tests, and deploy to port 8000 only if every
gate passes. The candidate is removed after the build. The Jenkinsfile also
activates polling for new commits every two minutes after the first run.

After a successful build:

- Chatbot: http://localhost:8000
- Deployment dashboard: http://localhost:8090
- Jenkins build page: Test Result, Red-Team Report, and archived artifacts

Ports 8000, 9000, and 8090 must be free before the first deployment. You do not
need to run the application manually before Jenkins; the pipeline starts it.
If the HTML report is restricted by Jenkins' content security policy, download
the archived report and open it locally.

## Troubleshooting

| Symptom | Action |
|---|---|
| Build waits for a node with label `linux` | Add the label to an online Linux node with a free executor. |
| `node` / `npm` not found | Rerun host setup; nvm in your shell does not configure the Jenkins service. |
| Docker permission denied | Rerun setup and restart the Jenkins agent/service to refresh groups. |
| Ollama connection refused from containers | Check `systemctl status acme-ollama-bridge ollama` and rerun setup. |
| Model missing | Run `ollama pull qwen2.5:3b`. |
| Chrome fails to start | Confirm Chrome is installed and Jenkins can write to its home/cache; Selenium Manager needs internet for the matching driver. |
| Host setup cannot use sudo | Run the provided command in a local terminal and enter your own sudo password. |
| Need service logs | `sudo journalctl -u jenkins -u acme-ollama-bridge -n 80 --no-pager` |
