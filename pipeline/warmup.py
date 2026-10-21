"""Load the LLM into memory before the tests start.

  python pipeline/warmup.py

The first request after Ollama starts has to load the model from disk, which
can take minutes on a busy CPU and time out. That made a normal question fail
in Selenium (build #2) even though the code was fine. Sending one small request
here, with retries, means the tests measure the chatbot and not a cold start.

Exit code 0 = model answered, 1 = Ollama/model not available (build stops).
"""
import os
import sys
import time
from pathlib import Path

import httpx

# Jenkins runs on the same PC as Ollama. (Not read from OLLAMA_HOST: Ollama itself
# uses that variable for its listen address, e.g. "0.0.0.0", which is not a URL.)
OLLAMA_URL = "http://127.0.0.1:11434"
MODEL_NAME = os.getenv("MODEL_NAME", "qwen2.5:3b")
ATTEMPTS = 3


def main() -> int:
    payload = {"model": MODEL_NAME, "stream": False,
               "messages": [{"role": "user", "content": "Say OK"}]}
    for attempt in range(1, ATTEMPTS + 1):
        try:
            r = httpx.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=300)
            r.raise_for_status()
            print(f"LLM {MODEL_NAME} is ready (attempt {attempt})")
            return 0
        except httpx.HTTPError as exc:
            print(f"attempt {attempt}/{ATTEMPTS} failed: {exc}")
            time.sleep(10)
    # notify.py shows this file's text as the reason on the dashboard
    Path("reports").mkdir(exist_ok=True)
    Path("reports/llm-warmup.txt").write_text(
        f"LLM: model {MODEL_NAME} could not be loaded by Ollama", encoding="utf-8")
    return 1


if __name__ == "__main__":
    sys.exit(main())
