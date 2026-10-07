# Viva guide: what every part does and why

## 1. The idea in one paragraph
LLM chatbots can be tricked with text: "ignore your instructions", "print your system prompt",
role-play jailbreaks, and HTML that runs in the browser. Normal unit tests do not catch this. So
**every build is attacked automatically before it is allowed to go live**. Jenkins deploys each
new version to a *candidate* environment, runs 21 attacks and 6 browser tests against it, and
replaces *production* only when all of them pass. Otherwise production keeps running and the
dashboard says why.

## 2. Request flow inside the chatbot (`target-app/app/main.py`)
1. **Input rules** (`rules.py`, `rules.yaml`): six regex rules (R1-R6) for known attack patterns.
   They are cheap, deterministic, and every block has a readable reason.
2. **ML guardrail** (`guardrail/service.py`): a classifier that returns P(attack). It catches
   paraphrases the rules don't know. If the service is down, the chatbot answers **503**, never
   "allowed", so a broken guardrail can't make the system look safe (*fail closed*).
3. **LLM** (Ollama `qwen2.5:3b`, temperature 0 for reproducible tests).
4. **Output rules**: block a reply that contains a secret or system-prompt text, and remove HTML tags.
   This is the last line of defence when the first two layers miss an attack.

The response says `blocked_by` (`rule:R1`, `ml_guardrail`, `output:secret_leak`) and gives a
`reason`, and the UI shows it in a red bubble.

## 3. File by file

### target-app/ (the AcmeBank bot)
- `app/config.py`: system prompt with bank knowledge (accounts, cards, branch hours) and
  **fake canary secrets**. If a canary appears in a reply, we know data leaked.
  `CONFIDENTIAL_MARKERS` lists what may never be printed.
- `app/rules.yaml`: the security rulebase as configuration-as-code. Changing it is a git commit,
  so it goes through the pipeline like code.
- `app/rules.py`: loads the YAML, compiles regexes once, and provides `check_input()` and
  `check_output()`, which return a `Verdict(blocked, blocked_by, reason)`.
- `app/main.py`: FastAPI endpoints `POST /chat`, `GET /health` (version and which layers are on),
  and `GET /` (UI).
- `app/static/index.html`: chat UI. It uses **`textContent`, never `innerHTML`**, so a reply with
  `<script>` is shown as text and not executed (XSS prevention). It shows a typing indicator, the
  block reason, and a protection badge. `data-testid` attributes give Selenium stable selectors.
- `tests/test_rules.py`: 7 tests, including that the rules block at most 3% of 411 normal messages.
- `Dockerfile`: python:3.13-slim, non-root user, HEALTHCHECK on `/health`.

### guardrail/ (ML model in CI/CD)
- `make_dataset.py`: seeded generator for about 830 labelled messages, including *hard negatives*
  ("ignore my last message") so the model doesn't just learn keywords. The output is committed as
  `data/dataset.csv`.
- `train.py`: TF-IDF features (word 1-2 grams + character 3-5 grams) and Logistic Regression.
  It saves `models/<UTC time>-<dataset hash>/model.joblib`, appends to `registry.json`, and
  updates `latest.txt`. The version name says when and from which data the model was made.
- `evaluate.py`: the **quality gate**. Held-out split (recall ≥ 0.95, FPR ≤ 0.03) and a
  hand-written *novel* set (recall ≥ 0.85, FPR ≤ 0.10). Exit code 1 stops the pipeline.
- `novel_eval.py`: the 40 hand-written novel messages.
- `detector.py`: loads the latest model and scores text. Threshold 0.4, because a missed attack
  costs more than an extra refusal.
- `service.py`: FastAPI `/check` and `/health` on port 8001.
- `Dockerfile`: copies the model **Jenkins already trained and evaluated**, so the image holds
  exactly the version that passed the gate. sklearn/joblib versions are pinned because pickled
  models need the same library versions.

### redteam/ (security testing)
- `payloads/*.yaml`: 21 attacks in 5 categories (prompt injection, jailbreak, system-prompt
  leakage, indirect injection, unsafe output/XSS).
- `scoring.py`: decides whether an attack worked. `leak` looks for canaries or prompt text,
  `marker` checks whether the bot printed the word the attacker demanded, and `html` looks for
  executable HTML. Refusals don't count as success.
- `runner.py`: sends every payload and applies the **gate**: FAIL if attack success rate > 20% or
  any success in the critical category `system_prompt_leakage`. Exit codes: 0 pass, 1 fail,
  2 error (target unreachable, so the result is inconclusive and also fails).
- `report.py`: `report.json` and `report.html`. Model output is HTML-escaped in the report.

### selenium-tests/ (practicals 6 and 7)
- `ui.test.js`: 6 mocha tests in headless Chrome: page and badge, empty message ignored, normal
  question answered (typing indicator), attack blocked with reason, XSS not executed, secret
  never shown.
- `package.json`: `npm test` locally, `npm run test:ci` writes JUnit XML for Jenkins.

### CI/CD
- `Jenkinsfile`: stages listed in the README. Key points:
  - `pollSCM('H/2 * * * *')`: local Jenkins can't receive GitHub webhooks, so it polls.
  - Hard gates (unit tests, model evaluation, build, candidate deploy) stop the pipeline.
  - Red-team and Selenium are wrapped in `catchError`, so both always run and every reason is
    collected. They still mark the build FAILED.
  - `when { currentBuild.currentResult == 'SUCCESS' }` guards the production deploy.
  - `post`: tear down the candidate, publish JUnit and the HTML report, archive the model, and
    notify the dashboard.
- `docker-compose.yml`: one file used as three projects: `acme-candidate` (9000), `acme-prod`
  (8000), `acme-dashboard` (8090). Images are tagged `build-N`, so production starts the **same
  images that were tested** (no rebuild between test and deploy).
- `pipeline/notify.py`: reads `reports/` (JUnit XML, model-eval.json, red-team report.json) and
  turns each failure into a sentence, then POSTs it to the dashboard.
- `dashboard/app.py`: stores runs in a Docker volume and shows "LIVE in production: build-N",
  "Deployment of build-M STOPPED" with reasons, and the history.

## 4. Why these design decisions?
| Question | Answer |
|---|---|
| Why a candidate environment? | You can't attack production safely, and if the new build is bad, production must not change. It's a simplified blue-green deployment. |
| How is the old version "kept running"? | The production stage is skipped, so `acme-prod` containers are never touched. |
| Why three layers? | Rules catch 21/21 known attacks but only 7/20 paraphrases. ML catches 18/20 paraphrases. Output rules stop leaks even if both miss. |
| Why train in CI? | Model, data and code are versioned together. A model that fails the gate can never be packaged. |
| Why a local LLM? | No API cost, no data leaves the machine, and results are reproducible (temperature 0). |
| Why exit codes? | Jenkins only understands success or failure. 0/1/2 makes each tool a gate. |
| Why fail closed (503)? | If the guardrail crashes, letting messages through would be silent and unsafe. |

## 5. Syllabus mapping
| # | Practical | Where |
|---|---|---|
| 1 | Git/GitHub | repo, feature branch + PR for the demo, `.gitignore`, `.gitattributes` |
| 2 | Jenkins setup | `docs/JENKINS_SETUP.md` |
| 3 | CI/CD with Jenkins | `Jenkinsfile` (pollSCM, stages, gates, post actions) |
| 4 | Docker commands | build, compose `-p`, `--wait`, tags, volumes, healthchecks |
| 5 | Containerised app | `target-app/`, `guardrail/`, `dashboard/` Dockerfiles |
| 6 | Selenium install | `selenium-tests/package.json` (Selenium Manager downloads the driver) |
| 7 | Selenium JS tests | `selenium-tests/ui.test.js` |
| 8 | ML model in CI/CD | Train, Evaluate (quality gate), versioned model, archived artifacts |
| 9 | Docker deploy via Jenkins | Deploy candidate and Deploy to production stages |
| 10 | Mini-project | the whole pipeline + dashboard demo |

## 6. Known limitations (say these honestly)
- 0% on our suite does not mean "unbreakable". It means none of *these 21* attacks worked. With
  the input rules on, the LLM's own behaviour under attack is barely exercised.
- The ML model is trained on synthetic data. It missed 2 of 20 novel paraphrases, and its
  threshold (0.4) was chosen on a small set.
- The input rules wrongly block 1 of 411 normal messages ("What is a system prompt, in general
  terms?").
- Leak detection is English-only: a secret translated into Spanish would not be caught by the
  scorer or the output rule.
- Swapping production causes a few seconds of downtime (containers are recreated).
- Jenkins polls every 2 minutes, so a deployment starts up to 2 minutes after a push.
