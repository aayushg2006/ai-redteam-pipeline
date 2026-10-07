"""Train the prompt-injection detector and register a new model version.

  python -m guardrail.train

Output (under guardrail/models/):
  <version>/model.joblib   the scikit-learn pipeline
  <version>/train.json     metadata (dataset hash, sizes, library versions)
  registry.json            list of all versions
  latest.txt               name of the newest version (read by detector.py)

Version = UTC timestamp + first 8 chars of the dataset hash, so you can always
tell which data produced which model.
"""
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline

from . import config


def load_dataset(path: Path = config.DATASET_PATH) -> tuple[list[str], list[int]]:
    texts, labels = [], []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            texts.append(row["text"])
            labels.append(int(row["label"]))
    return texts, labels


def split(texts, labels):
    """Same split everywhere (train.py and evaluate.py) thanks to the fixed seed."""
    return train_test_split(
        texts, labels, test_size=config.TEST_SIZE,
        random_state=config.SEED, stratify=labels,
    )


def build_pipeline() -> Pipeline:
    features = FeatureUnion([
        ("words", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, lowercase=True)),
        ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, lowercase=True)),
    ])
    clf = LogisticRegression(C=10.0, class_weight="balanced", max_iter=2000, random_state=config.SEED)
    return Pipeline([("features", features), ("clf", clf)])


def dataset_hash(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def train(dataset_path: Path = config.DATASET_PATH, models_dir: Path = config.MODELS_DIR) -> dict:
    texts, labels = load_dataset(dataset_path)
    x_train, _x_test, y_train, _y_test = split(texts, labels)

    pipe = build_pipeline()
    pipe.fit(x_train, y_train)

    digest = dataset_hash(dataset_path)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    version = f"{stamp}-{digest[:8]}"

    out_dir = Path(models_dir) / version
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, out_dir / "model.joblib")

    meta = {
        "version": version,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset_sha256": digest,
        "rows_total": len(texts),
        "rows_train": len(x_train),
        "attacks_in_train": int(sum(y_train)),
        "sklearn_version": sklearn.__version__,
        "python_version": sys.version.split()[0],
    }
    (out_dir / "train.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    registry_path = Path(models_dir) / "registry.json"
    registry = json.loads(registry_path.read_text()) if registry_path.exists() else []
    registry.append(meta)
    registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    (Path(models_dir) / "latest.txt").write_text(version, encoding="utf-8")
    return meta


def main() -> None:
    if not config.DATASET_PATH.exists():
        print("dataset.csv missing: run `python -m guardrail.make_dataset` first", file=sys.stderr)
        raise SystemExit(2)
    meta = train()
    print(f"Trained model {meta['version']} on {meta['rows_train']} rows "
          f"({meta['attacks_in_train']} attacks)")


if __name__ == "__main__":
    main()