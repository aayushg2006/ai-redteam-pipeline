# Jenkins setup on Windows (manual steps)

Everything except Jenkins was tested locally. Do these steps once.

## 0. Before you start
- Docker Desktop is running (whale icon in the system tray).
- Ollama is running and the model is present: `ollama pull qwen2.5:3b`
- Python 3.13 (with the `py` launcher), Node.js and Google Chrome are installed.
  The pipeline runs `py -3.13` on purpose: on this PC plain `python` in cmd is an MSYS2 Python 3.14.
- Note where the tools live (you need these paths in step 3). In PowerShell:
  ```powershell
  (Get-Command py).Source
  (Get-Command node).Source
  (Get-Command docker).Source
  ```

## 1. Install Jenkins
1. Install Java if the Jenkins installer asks for it (Temurin JDK 17 or 21 from adoptium.net;
   JDK 17 is already installed on this PC). If the installer says 17 is too old, install 21.
2. Download the **Jenkins LTS Windows installer (.msi)** from jenkins.io/download and run it.
3. On the *Service Logon Credentials* page choose **"Run service as local or domain user"** and
   enter **your own Windows username and password**, then click *Test Credentials*.
   - With a Microsoft account, use the local username (the folder name under `C:\Users`) and your
     Microsoft account password.
   - Why: the default LocalSystem account can't see your Python, Node or Docker Desktop.
4. Keep port **8080**. Finish the install.

## 2. First login
1. Open http://localhost:8080.
2. Paste the password from `C:\ProgramData\Jenkins\.jenkins\secrets\initialAdminPassword`
   (the page shows the exact path).
3. Click **Install suggested plugins** (this includes Git, Pipeline, JUnit and Workspace Cleanup).
4. Create your admin user.
5. Manage Jenkins → Plugins → Available → install **HTML Publisher**. Restart Jenkins if asked.

## 3. Make the tools visible to Jenkins
Manage Jenkins → System → **Global properties** → tick *Environment variables* → Add:
- Name: `PATH+EXTRA`
- Value: the folders from step 0, separated by `;`, for example
  `C:\Users\<you>\AppData\Local\Programs\Python\Launcher;C:\Program Files\nodejs;C:\Program Files\Docker\Docker\resources\bin`

Save.

## 4. Create the pipeline job
1. New Item → name `ai-redteam-pipeline` → **Pipeline** → OK.
2. In **Pipeline**, set Definition to **Pipeline script from SCM**.
   - SCM: **Git**
   - Repository URL: `https://github.com/aayushg2006/ai-redteam-pipeline.git`
   - Credentials: none if the repo is public. If it's private, add a GitHub username plus a
     Personal Access Token.
   - Branch Specifier: `*/main`
   - Script Path: `Jenkinsfile`
3. Save.

## 5. First run
1. Click **Build Now**. The first run is slower (pip, npm and Docker downloads), about 10-15 min.
   This first build also activates the "poll GitHub every 2 minutes" trigger from the Jenkinsfile.
2. Watch it in **Stage View** or the console output.
3. When it's green, open:
   - http://localhost:8000 for the live AcmeBot (production)
   - http://localhost:8090 for the deployment dashboard
   - in the build page, **Red-Team Report** and **Test Result**

If the red-team HTML report looks unstyled inside Jenkins, go to Manage Jenkins → Script
Console, run this, then rebuild:
```groovy
System.setProperty("hudson.model.DirectoryBrowserSupport.CSP", "")
```

## 6. Demo for the faculty (Git branch + PR workflow)
```powershell
git checkout -b demo/break-security
# edit target-app/app/rules.yaml: set ml_guardrail, input_rules.enabled,
# block_secret_leaks and strip_html to false
git commit -am "demo: disable security layers"
git push -u origin demo/break-security
```
Open a Pull Request on GitHub and merge it into main. Within 2 minutes Jenkins builds it:
red-team FAIL (about 67%), Selenium failures, **BLOCKED** on the dashboard, and
http://localhost:8000 still shows the previous build (badge "Protection ON · build-N").

Fix: revert the change (`git revert`, or set the switches back to `true`), push or merge again.
The next build passes and is **deployed automatically**, and the dashboard shows the new LIVE build.

## Troubleshooting
| Symptom | Fix |
|---|---|
| `'py' is not recognized` | Step 3 PATH is wrong, or the service isn't running as your user (step 1.3). |
| `error during connect ... docker_engine` | Docker Desktop isn't running, or Jenkins runs as LocalSystem. |
| Red-team stage ERROR (exit 2), "502 Ollama unreachable" | Start Ollama and check `ollama list` shows `qwen2.5:3b`. |
| Selenium: `session not created` | Update Chrome. Selenium Manager downloads a matching driver (needs internet). |
| Port 8000/9000/8090 already in use | Stop the other program, or `docker compose -p acme-prod down` and similar. |
| Change Jenkins service account later | `services.msc` → Jenkins → Properties → Log On → *This account*. |
