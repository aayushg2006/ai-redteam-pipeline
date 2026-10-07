"""Send the result of a Jenkins run to the deployment dashboard.

  python pipeline/notify.py DEPLOYED
  python pipeline/notify.py BLOCKED

It reads the reports written by the pipeline stages and turns every failure
into one human-readable reason, e.g.
  "Red-team: attack success rate 67% exceeds the limit of 20%".
A missing report means that stage never ran (an earlier stage failed).

Build number, commit and Jenkins URL come from Jenkins' environment variables.
"""
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import httpx

REPORTS = Path("reports")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://127.0.0.1:8090")


def junit_failures(path: Path, label: str) -> list[str]:
    """One reason per failed test in a JUnit XML file (pytest and mocha both write these)."""
    if not path.exists():
        return [f"{label}: did not run (see Jenkins console log)"]
    failed = []
    for case in ET.parse(path).getroot().iter("testcase"):
        if case.find("failure") is not None or case.find("error") is not None:
            failed.append(f"{label}: test failed - {case.get('name')}")
    return failed


def model_reasons() -> list[str]:
    path = REPORTS / "model-eval.json"
    if not path.exists():
        return ["Model gate: guardrail model was not evaluated"]
    result = json.loads(path.read_text(encoding="utf-8"))
    return [f"Model gate: {f}" for f in result["failures"]]


def redteam_reasons() -> tuple[list[str], float | None]:
    path = REPORTS / "redteam" / "report.json"
    if not path.exists():
        return ["Red-team: security tests did not run"], None
    summary = json.loads(path.read_text(encoding="utf-8"))["summary"]
    return [f"Red-team: {r}" for r in summary["reasons"]], summary["attack_success_rate"]


def model_version() -> str:
    path = REPORTS / "model-eval.json"
    return json.loads(path.read_text(encoding="utf-8"))["version"] if path.exists() else ""


def commit_message() -> str:
    try:
        return subprocess.run(["git", "log", "-1", "--pretty=%s"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return ""


def collect(decision: str) -> dict:
    redteam, asr = redteam_reasons()
    reasons = []
    if decision == "BLOCKED":
        reasons = (junit_failures(REPORTS / "unit-tests.xml", "Unit tests")
                   + model_reasons()
                   + redteam
                   + junit_failures(REPORTS / "selenium.xml", "Selenium UI"))
        if not reasons:
            reasons = ["Pipeline error (see Jenkins console log)"]
    return {
        "build": os.getenv("IMAGE_TAG", "local"),
        "decision": decision,
        "reasons": reasons,
        "commit": os.getenv("GIT_COMMIT", ""),
        "commit_message": commit_message(),
        "attack_success_rate": asr,
        "model_version": model_version(),
        "build_url": os.getenv("BUILD_URL", ""),
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ("DEPLOYED", "BLOCKED"):
        print(__doc__)
        return 2
    run = collect(sys.argv[1])
    print(json.dumps(run, indent=2))
    # Jenkins shows the first reason as the build description.
    Path(REPORTS).mkdir(exist_ok=True)
    (REPORTS / "decision.txt").write_text(
        run["decision"] + (": " + run["reasons"][0] if run["reasons"] else ""), encoding="utf-8")
    try:
        httpx.post(f"{DASHBOARD_URL}/api/runs", json=run, timeout=10).raise_for_status()
    except httpx.HTTPError as exc:
        # The dashboard is only a display; never fail the build because of it.
        print(f"WARNING: could not reach dashboard: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
