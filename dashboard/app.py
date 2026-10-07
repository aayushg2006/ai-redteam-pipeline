"""Deployment dashboard: shows what is live in production and why a build was stopped.

Jenkins sends one record per pipeline run (pipeline/notify.py):
  POST /api/runs  {"build": "build-7", "decision": "DEPLOYED" | "BLOCKED", "reasons": [...], ...}

GET /           HTML page (auto-refreshes every 15 s)
GET /api/runs   the raw history as JSON
"""
import json
import os
from datetime import datetime
from html import escape
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

HISTORY = Path(os.getenv("DATA_DIR", "data")) / "history.json"

app = FastAPI(title="AcmeBank deployment dashboard")


class Run(BaseModel):
    build: str
    decision: str                 # DEPLOYED or BLOCKED
    reasons: list[str] = []
    commit: str = ""
    commit_message: str = ""
    attack_success_rate: float | None = None
    model_version: str = ""
    build_url: str = ""
    time: str = ""


def load() -> list[dict]:
    return json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else []


@app.post("/api/runs")
def add_run(run: Run):
    run.time = run.time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    history = load()
    history.append(run.model_dump())
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    HISTORY.write_text(json.dumps(history, indent=2), encoding="utf-8")
    return {"stored": len(history)}


@app.get("/api/runs")
def list_runs():
    return load()


def link(run: dict) -> str:
    if not run["build_url"]:
        return escape(run["build"])
    return f'<a href="{escape(run["build_url"])}">{escape(run["build"])}</a>'


def percent(value: float | None) -> str:
    return "" if value is None else f"{value:.0%}"


@app.get("/", response_class=HTMLResponse)
def page():
    history = load()
    live = next((r for r in reversed(history) if r["decision"] == "DEPLOYED"), None)
    latest = history[-1] if history else None

    if live:
        live_html = (f'<div class="card ok"><h2>LIVE in production: {link(live)}</h2>'
                     f'<p>commit {escape(live["commit"][:7])} &middot; {escape(live["commit_message"])}'
                     f' &middot; deployed {escape(live["time"])}</p></div>')
    else:
        live_html = '<div class="card">Nothing deployed yet.</div>'

    blocked_html = ""
    if latest and latest["decision"] == "BLOCKED":
        reasons = "".join(f"<li>{escape(r)}</li>" for r in latest["reasons"])
        still = f"Production is still running {escape(live['build'])}." if live else ""
        blocked_html = (f'<div class="card bad"><h2>Deployment of {link(latest)} STOPPED</h2>'
                        f'<p>commit {escape(latest["commit"][:7])} &middot; '
                        f'{escape(latest["commit_message"])}</p><ul>{reasons}</ul><p>{still}</p></div>')

    rows = "".join(
        f'<tr><td>{escape(r["time"])}</td><td>{link(r)}</td>'
        f'<td class="{escape(r["decision"])}">{escape(r["decision"])}</td>'
        f'<td>{escape(r["commit"][:7])} {escape(r["commit_message"])}</td>'
        f'<td>{percent(r["attack_success_rate"])}</td>'
        f'<td>{"<br>".join(escape(x) for x in r["reasons"])}</td></tr>'
        for r in reversed(history)
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="15"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>AcmeBank Deployments</title><style>
body{{font-family:system-ui,sans-serif;margin:2rem auto;max-width:1000px;padding:0 1rem;background:#f4f5f7;color:#111}}
.card{{background:#fff;border-radius:10px;padding:1rem 1.25rem;margin:1rem 0;border-left:6px solid #9ca3af}}
.card h2{{margin:.2rem 0 .4rem;font-size:1.2rem}} .ok{{border-color:#16a34a}} .bad{{border-color:#dc2626}}
table{{border-collapse:collapse;width:100%;background:#fff;font-size:.9rem}}
th,td{{border:1px solid #e5e7eb;padding:.45rem .6rem;text-align:left;vertical-align:top}}
.DEPLOYED{{color:#15803d;font-weight:700}} .BLOCKED{{color:#b91c1c;font-weight:700}}
</style></head><body>
<h1>AcmeBank &middot; Deployment Dashboard</h1>
{live_html}{blocked_html}
<h2>Pipeline history</h2>
<table><tr><th>Time</th><th>Build</th><th>Decision</th><th>Commit</th><th>Attack success</th><th>Reasons</th></tr>
{rows}</table></body></html>"""
