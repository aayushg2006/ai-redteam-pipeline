"""Evaluate the latest model and decide whether it may be deployed.

  python -m guardrail.evaluate

Three views of quality:
  heldout  - unseen rows from the SAME generator. Easy; sanity check only.
  novel    - hand-written messages phrased differently (novel_eval.py).
             This is the honest generalisation number and the main gate.
  redteam  - the attack prompts of the red-team suite, as an external check.
             Recall only (they are all attacks). Reported, not gated, because
             the real test is running the full suite against the chatbot.

recall = share of attacks caught.  FPR = share of normal messages wrongly blocked.

Exit code: 0 = gate passed, 1 = gate failed. CI uses this to stop a bad model.
"""
import json
import sys

from . import config
from .detector import Detector
from .novel_eval import NOVEL_ATTACKS, NOVEL_BENIGN
from .train import load_dataset, split


def rates(detector: Detector, texts: list[str], labels: list[int]) -> dict:
    scores = detector.scores(texts)
    preds = [int(s >= detector.threshold) for s in scores]
    tp = sum(1 for p, y in zip(preds, labels) if p == 1 and y == 1)
    fn = sum(1 for p, y in zip(preds, labels) if p == 0 and y == 1)
    fp = sum(1 for p, y in zip(preds, labels) if p == 1 and y == 0)
    tn = sum(1 for p, y in zip(preds, labels) if p == 0 and y == 0)
    recall = tp / (tp + fn) if (tp + fn) else None
    fpr = fp / (fp + tn) if (fp + tn) else None
    precision = tp / (tp + fp) if (tp + fp) else None
    missed = [t for t, p, y in zip(texts, preds, labels) if y == 1 and p == 0]
    false_alarms = [t for t, p, y in zip(texts, preds, labels) if y == 0 and p == 1]
    return {
        "n": len(texts), "tp": tp, "fn": fn, "fp": fp, "tn": tn,
        "recall": None if recall is None else round(recall, 3),
        "fpr": None if fpr is None else round(fpr, 3),
        "precision": None if precision is None else round(precision, 3),
        "missed_attacks": missed,
        "false_alarms": false_alarms,
    }


def redteam_recall(detector: Detector) -> dict:
    from redteam.runner import load_payloads  # optional dependency (same repo)
    prompts = [p["prompt"] for p in load_payloads()]
    flagged = [detector.is_attack(p) for p in prompts]
    return {
        "n": len(prompts),
        "recall": round(sum(flagged) / len(prompts), 3),
        "missed": [p for p, f in zip(prompts, flagged) if not f],
    }


def evaluate() -> dict:
    detector = Detector()
    texts, labels = load_dataset()
    _x_train, x_test, _y_train, y_test = split(texts, labels)

    heldout = rates(detector, x_test, y_test)
    novel = rates(detector, NOVEL_ATTACKS + NOVEL_BENIGN,
                  [1] * len(NOVEL_ATTACKS) + [0] * len(NOVEL_BENIGN))
    try:
        red = redteam_recall(detector)
    except Exception as exc:  # running inside the guardrail-only Docker image
        red = {"skipped": str(exc)}

    checks = {
        "heldout_recall": (heldout["recall"], ">=", config.MIN_RECALL_HELDOUT),
        "heldout_fpr": (heldout["fpr"], "<=", config.MAX_FPR_HELDOUT),
        "novel_recall": (novel["recall"], ">=", config.MIN_RECALL_NOVEL),
        "novel_fpr": (novel["fpr"], "<=", config.MAX_FPR_NOVEL),
    }
    failures = []
    for name, (value, op, limit) in checks.items():
        ok = value >= limit if op == ">=" else value <= limit
        if not ok:
            failures.append(f"{name} {value} is not {op} {limit}")

    result = {
        "version": detector.version,
        "threshold": detector.threshold,
        "passed": not failures,
        "failures": failures,
        "heldout": heldout,
        "novel": novel,
        "redteam_prompts": red,
    }
    (detector.models_dir / detector.version / "eval.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    r = evaluate()
    print(f"Model {r['version']}  (threshold {r['threshold']})")
    for name in ("heldout", "novel"):
        s = r[name]
        print(f"  {name:8} n={s['n']:4}  recall={s['recall']}  fpr={s['fpr']}  precision={s['precision']}")
    if "recall" in r["redteam_prompts"]:
        print(f"  redteam  n={r['redteam_prompts']['n']:4}  recall={r['redteam_prompts']['recall']}")
        for p in r["redteam_prompts"]["missed"]:
            print(f"     missed: {p[:90]!r}")
    for t in r["novel"]["missed_attacks"]:
        print(f"  novel attack missed: {t[:90]!r}")
    for t in r["novel"]["false_alarms"]:
        print(f"  novel false alarm:   {t[:90]!r}")
    print("GATE:", "PASS" if r["passed"] else "FAIL")
    for f in r["failures"]:
        print("  -", f)
    return 0 if r["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())