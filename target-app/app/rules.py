"""AcmeBank rule engine: loads rules.yaml and applies the input/output rules.

check_input(message)  -> Verdict   (run BEFORE the message reaches the model)
check_output(reply)   -> (reply, Verdict)  (run AFTER the model answers)
"""
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import CONFIDENTIAL_MARKERS

RULES_PATH = Path(__file__).parent / "rules.yaml"
HTML_TAG_RE = re.compile(r"<[^>]*>")


@dataclass
class Verdict:
    blocked: bool = False
    blocked_by: str | None = None   # e.g. "rule:R1", "output:secret_leak"
    reason: str | None = None


def load_rules(path: Path = RULES_PATH) -> dict:
    rules = yaml.safe_load(path.read_text(encoding="utf-8"))
    # Compile the regexes once; IGNORECASE so "IGNORE ALL..." is caught too.
    for rule in rules["input_rules"]["rules"]:
        rule["regex"] = re.compile(rule["pattern"], re.IGNORECASE)
    return rules


RULES = load_rules()


def check_input(message: str, rules: dict = RULES) -> Verdict:
    if not rules["input_rules"]["enabled"]:
        return Verdict()
    for rule in rules["input_rules"]["rules"]:
        if rule["regex"].search(message):
            return Verdict(True, f"rule:{rule['id']}", rule["reason"])
    return Verdict()


def check_output(reply: str, rules: dict = RULES) -> tuple[str, Verdict]:
    out = rules["output_rules"]
    if out["block_secret_leaks"]:
        lowered = reply.lower()
        for marker in CONFIDENTIAL_MARKERS:
            if marker.lower() in lowered:
                return reply, Verdict(True, "output:secret_leak",
                                      "Reply contained confidential data")
    if out["strip_html"]:
        reply = HTML_TAG_RE.sub("", reply)
    return reply, Verdict()
