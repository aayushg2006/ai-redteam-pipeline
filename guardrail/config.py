"""Settings for the guardrail (all overridable via environment variables)."""
import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).parent
DATA_DIR = PACKAGE_DIR / "data"
DATASET_PATH = DATA_DIR / "dataset.csv"
MODELS_DIR = Path(os.getenv("MODELS_DIR", PACKAGE_DIR / "models"))

SEED = 42
TEST_SIZE = 0.2

# Runtime: a message is blocked when P(attack) >= THRESHOLD.
# 0.4 rather than 0.5: for a security filter a missed attack costs more than an
# extra blocked message. Chosen by looking at a small (40 message) set, so
# revisit it when the novel set grows.
THRESHOLD = float(os.getenv("GUARDRAIL_THRESHOLD", "0.4"))

# Quality gate used by evaluate.py (and therefore by CI).
# "novel" = hand-written messages the model never saw, phrased differently
# from the generated training data. This is the number that matters.
MIN_RECALL_NOVEL = float(os.getenv("MIN_RECALL_NOVEL", "0.85"))
MAX_FPR_NOVEL = float(os.getenv("MAX_FPR_NOVEL", "0.10"))
# "heldout" = unseen rows from the same generator (easy; sanity check only).
MIN_RECALL_HELDOUT = float(os.getenv("MIN_RECALL_HELDOUT", "0.95"))
MAX_FPR_HELDOUT = float(os.getenv("MAX_FPR_HELDOUT", "0.03"))