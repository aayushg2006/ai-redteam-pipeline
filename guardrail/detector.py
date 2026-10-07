"""Runtime detector: loads the latest trained model and scores messages."""
from pathlib import Path

import joblib

from . import config


def latest_version(models_dir: Path = config.MODELS_DIR) -> str:
    pointer = Path(models_dir) / "latest.txt"
    if not pointer.exists():
        raise FileNotFoundError(f"no trained model found in {models_dir}; run `python -m guardrail.train`")
    return pointer.read_text(encoding="utf-8").strip()


class Detector:
    def __init__(self, models_dir: Path = config.MODELS_DIR, version: str | None = None,
                 threshold: float = config.THRESHOLD):
        self.models_dir = Path(models_dir)
        self.version = version or latest_version(self.models_dir)
        self.threshold = threshold
        self.pipeline = joblib.load(self.models_dir / self.version / "model.joblib")

    def score(self, text: str) -> float:
        """Probability that the text is an attack (0..1)."""
        return float(self.pipeline.predict_proba([text])[0][1])

    def scores(self, texts: list[str]) -> list[float]:
        return [float(p[1]) for p in self.pipeline.predict_proba(texts)]

    def is_attack(self, text: str) -> bool:
        return self.score(text) >= self.threshold