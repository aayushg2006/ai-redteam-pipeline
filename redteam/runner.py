"""Red-team runner.

Sends every attack payload to the target chatbot, scores each reply, applies
the security gate and writes JSON + HTML reports.

Exit codes (Jenkins uses these to pass/fail the build):
  0  gate passed
  1  gate failed (too many successful attacks, or a critical leak)
  2  run was inconclusive (target unreachable / request errors)

Usage (from the project root):
  python -m redteam.runner --target http://127.0.0.1:8000
"""
import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

from . import config
from .report import write_reports
from .scoring import DETECTORS, score_reply

PAYLOAD_DIR = Path(__file__).parent / "payloads"


def load_payloads(categories: list[str] | None = None) -> list[dict]:
    items = []
    for path in sorted(PAYLOAD_DIR.glob("*.yaml")):
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        if categories and spec["category"] not in categories:
            continue
        for p in spec["payloads"]:
            items.append(
                {
                    "id": p["id"],
                    "category": spec["category"],
                    "title": spec.get("title", spec["category"]),
                    "severity": spec.get("severity", "medium"),
                    "detector": p.get("detector", spec["detector"]),
                    "marker": p.get("marker"),
                    "prompt": p["prompt"],
                }
            )
    return items


def send(client: httpx.Client, url: str, prompt: str) -> dict:
    r = client.post(f"{url}/chat", json={"message": prompt})
    r.raise_for_status()
    return r.json()


def run_attacks(payloads, url, repeats=1, timeout=120.0, sender=send) -> list[dict]:
    results = []
    with httpx.Client(timeout=timeout) as client:
        for p in payloads:
            for attempt in range(1, repeats + 1):
                rec = {**p, "attempt": attempt}
                start = time.time()
                try:
                    data = sender(client, url, p["prompt"])
                    rec["reply"] = data.get("reply", "")
                    rec["blocked"] = bool(data.get("blocked", False))
                    if rec["blocked"]:
                        rec["success"], rec["evidence"] = False, "blocked by guardrail"
                    else:
                        rec["success"], rec["evidence"] = score_reply(
                            p["detector"], rec["reply"], p.get("marker")
                        )
                    rec["error"] = None
                except Exception as exc:  # network error, bad JSON, HTTP 5xx...
                    rec.update(reply="", blocked=False, success=False,
                               evidence="", error=str(exc))
                rec["latency_s"] = round(time.time() - start, 2)
                results.append(rec)
                status = "ERROR" if rec["error"] else ("BREACH" if rec["success"] else "ok")
                print(f"  [{status:6}] {p['id']:7} {p['category']}", flush=True)
    return results


def summarize(results, max_asr, critical_categories) -> dict:
    valid = [r for r in results if not r["error"]]
    errors = len(results) - len(valid)

    by_cat: dict[str, dict] = {}
    for r in valid:
        c = by_cat.setdefault(r["category"], {"attempts": 0, "successful": 0, "blocked": 0})
        c["attempts"] += 1
        c["successful"] += int(r["success"])
        c["blocked"] += int(r["blocked"])
    for c in by_cat.values():
        c["asr"] = round(c["successful"] / c["attempts"], 3)

    total = len(valid)
    successful = sum(int(r["success"]) for r in valid)
    asr = round(successful / total, 3) if total else 0.0

    reasons = []
    if errors:
        status = "ERROR"
        reasons.append(f"{errors} request(s) failed; results are inconclusive")
    else:
        status = "PASS"
        if asr > max_asr:
            status = "FAIL"
            reasons.append(f"attack success rate {asr:.0%} exceeds limit {max_asr:.0%}")
        for cat in critical_categories:
            if by_cat.get(cat, {}).get("successful", 0) > 0:
                status = "FAIL"
                reasons.append(f"critical category '{cat}' had a successful attack")

    return {
        "status": status,
        "reasons": reasons,
        "total_attempts": total,
        "successful_attacks": successful,
        "attack_success_rate": asr,
        "max_asr": max_asr,
        "errors": errors,
        "by_category": by_cat,
    }


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Run the red-team attack suite.")
    ap.add_argument("--target", default=config.TARGET_URL)
    ap.add_argument("--max-asr", type=float, default=config.MAX_ASR)
    ap.add_argument("--repeats", type=int, default=config.REPEATS)
    ap.add_argument("--category", action="append", help="limit to a category (repeatable)")
    ap.add_argument("--report-dir", default=config.REPORT_DIR)
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    payloads = load_payloads(args.category)
    if not payloads:
        print("No payloads selected.", file=sys.stderr)
        return 2

    print(f"Target: {args.target}  |  payloads: {len(payloads)}  |  repeats: {args.repeats}")
    results = run_attacks(payloads, args.target, args.repeats, config.REQUEST_TIMEOUT)
    summary = summarize(results, args.max_asr, config.CRITICAL_CATEGORIES)

    meta = {
        "target": args.target,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repeats": args.repeats,
    }
    json_path, html_path = write_reports(args.report_dir, meta, summary, results)

    print(f"\nGate: {summary['status']}  |  ASR {summary['attack_success_rate']:.0%} "
          f"({summary['successful_attacks']}/{summary['total_attempts']})")
    for reason in summary["reasons"]:
        print(f"  - {reason}")
    print(f"Reports: {json_path}  {html_path}")

    return {"PASS": 0, "FAIL": 1, "ERROR": 2}[summary["status"]]


if __name__ == "__main__":
    sys.exit(main())
