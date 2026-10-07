# AI Red-Team Pipeline: Security Testing for AI Systems

AI DevOps mini-project (topic 8: *Security Testing for AI Systems*).

**AcmeBot** is a bank support chatbot that runs on a local LLM (Ollama, `qwen2.5:3b`) and is
protected by three security layers. A **Jenkins CI/CD pipeline** attacks every new build
automatically. If the build is safe it is deployed. If a breach is found, the deployment is
**stopped**, the old version keeps running, and the reason appears on a **dashboard**.

```
 git push ──► Jenkins (polls GitHub every 2 min)
               │
               ├─ 1 Setup              venv, pip, npm, start dashboard
               ├─ 2 Unit tests         pytest: rules, guardrail, red-team code
               ├─ 3 Train model        ML prompt-injection classifier (versioned)
               ├─ 4 Evaluate model     quality gate: recall / false-positive rate
               ├─ 5 Build images       docker compose build  (tag build-N)
               ├─ 6 Deploy CANDIDATE   port 9000
               ├─ 7 Red-team tests     21 attacks against the candidate
               ├─ 8 Selenium UI tests  6 browser tests against the candidate
               └─ 9 Deploy PRODUCTION  port 8000, only if 2-8 all passed
                        │
         pass ──► DEPLOYED ──┐
         fail ──► BLOCKED ───┴──► dashboard :8090 (reasons, what is live)
```

## How a message is protected (defence in depth)

```
user ─► [1] input rules ─► [2] ML guardrail ─► LLM ─► [3] output rules ─► user
          rules.yaml         guardrail service           block leaks, strip HTML
```

All three layers are switched on and off in one file, `target-app/app/rules.yaml`.

## Project layout

| Path | What it is | Syllabus practical |
|---|---|---|
| `target-app/` | AcmeBot: FastAPI app, rule engine (`rules.py` + `rules.yaml`), chat UI | 5 |
| `guardrail/` | ML classifier: dataset, train, evaluate (gate), HTTP service | 8 |
| `redteam/` | Attack suite: 21 YAML payloads, scoring, gate, HTML report | 10 |
| `selenium-tests/` | JavaScript Selenium UI tests (mocha) | 6, 7 |
| `dashboard/` | Deployment status page | 9 |
| `pipeline/notify.py` | Turns test reports into reasons and sends them to the dashboard | 3 |
| `Jenkinsfile` | The CI/CD pipeline | 2, 3, 9 |
| `docker-compose.yml` | Guardrail, chatbot and dashboard containers | 4, 5 |
| `docs/` | `EXPLANATION.md` (viva guide), `JENKINS_SETUP.md` | |

## Run it locally (without Jenkins)

Prerequisites: Python 3.13, Docker Desktop, Node.js, Chrome, Ollama with `ollama pull qwen2.5:3b`.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r target-app/requirements.txt -r guardrail/requirements.txt -r redteam/requirements.txt

python -m pytest                                   # 31 unit tests
python -m guardrail.train                          # train + version the ML model
python -m guardrail.evaluate                       # quality gate -> GATE: PASS
docker compose up -d --build --wait                # chatbot on http://localhost:8000
python -m redteam.runner --target http://127.0.0.1:8000   # security gate
cd selenium-tests; npm ci; npm test                # UI tests
```

## Demo: breach is blocked, fix is deployed

1. Push any change: the pipeline runs, everything is green, and the dashboard shows **LIVE build-N**.
2. Break security: in `target-app/app/rules.yaml` set `ml_guardrail`, `input_rules.enabled`,
   `block_secret_leaks` and `strip_html` to `false`, then commit and push.
   The red-team gets 14/21 attacks through (67%) and leaks the secret, and Selenium sees the
   leaked key. The build is **BLOCKED**, the dashboard lists the reasons, and
   http://localhost:8000 still runs the old safe build.
3. Fix it: set them back to `true` and push. The build passes and is **deployed automatically**.

## Results (measured)

| Configuration | Attack success | Gate |
|---|---|---|
| No protection (all switches off) | 14/21 = 67% (secret leaked) | FAIL, deployment blocked |
| All three layers on | 0/21 = 0% | PASS, deployed |

| Layer | Known attacks (21) | Unseen paraphrased attacks (20) | Normal messages wrongly blocked |
|---|---|---|---|
| Input rules | 21/21 | 7/20 | 1/411 (0.2%) |
| ML guardrail | 21/21 | 18/20 | 0/20 (novel set), 2.4% (held-out) |

The rules are precise but only catch phrasings someone wrote a rule for. The ML model generalises
to new phrasings. Each layer covers the other's gaps. See `docs/EXPLANATION.md` for the known
limitations.
