"""AcmeBank support chatbot (FastAPI + local Ollama model).

Every message goes through three layers of defence, all switched in rules.yaml:

  1. input rules   (rules.py)            - regex rules for known attacks
  2. ML guardrail  (guardrail service)   - classifier for paraphrased attacks
  3. Ollama model  answers
  4. output rules  (rules.py)            - block secret leaks, strip HTML

If a layer blocks the message the user gets a polite refusal plus the reason,
and the response says which layer blocked it (blocked_by).
"""
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .config import SYSTEM_PROMPT
from .rules import RULES, Verdict, check_input, check_output

# 127.0.0.1, not "localhost": on Windows "localhost" can resolve to IPv6 (::1)
# first while Ollama only listens on IPv4.
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
MODEL_NAME = os.getenv("MODEL_NAME", "qwen2.5:3b")
GUARDRAIL_URL = os.getenv("GUARDRAIL_URL", "http://127.0.0.1:8001")
APP_VERSION = os.getenv("APP_VERSION", "dev")   # Jenkins sets this to build-<N>

REFUSAL = "Sorry, I can't help with that request."

app = FastAPI(title="AcmeBank Support Bot", version="1.0.0")
INDEX_HTML = Path(__file__).parent / "static" / "index.html"


class ChatRequest(BaseModel):
    message: str = Field(..., max_length=4000)


class ChatResponse(BaseModel):
    reply: str
    blocked: bool = False
    blocked_by: str | None = None
    reason: str | None = None


def blocked_response(v: Verdict) -> ChatResponse:
    return ChatResponse(reply=REFUSAL, blocked=True, blocked_by=v.blocked_by, reason=v.reason)


async def ml_guardrail(message: str) -> Verdict:
    """Ask the guardrail service. If it is down we answer 503 instead of
    letting the message through, so a broken guardrail can never look safe."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{GUARDRAIL_URL}/check", json={"text": message})
            r.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Guardrail unavailable: {exc}")
    result = r.json()
    if result["attack"]:
        return Verdict(True, "ml_guardrail",
                       f"ML guardrail flagged a prompt attack (score {result['score']:.2f})")
    return Verdict()


async def ask_model(message: str) -> str:
    payload = {
        "model": MODEL_NAME,
        "stream": False,
        "options": {"temperature": 0},  # keep tests as reproducible as possible
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(f"{OLLAMA_HOST}/api/chat", json=payload)
            r.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Ollama unreachable: {exc}")
    return r.json()["message"]["content"]


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    # Layer 1: input rules
    verdict = check_input(req.message)
    if verdict.blocked:
        return blocked_response(verdict)

    # Layer 2: ML guardrail
    if RULES["ml_guardrail"]:
        verdict = await ml_guardrail(req.message)
        if verdict.blocked:
            return blocked_response(verdict)

    # The model answers, then layer 3: output rules
    reply, verdict = check_output(await ask_model(req.message))
    if verdict.blocked:
        return blocked_response(verdict)
    return ChatResponse(reply=reply)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": APP_VERSION,
        "model": MODEL_NAME,
        "protection": {
            "input_rules": RULES["input_rules"]["enabled"],
            "ml_guardrail": RULES["ml_guardrail"],
            "output_rules": RULES["output_rules"]["block_secret_leaks"]
                            or RULES["output_rules"]["strip_html"],
        },
    }


@app.get("/")
def index():
    return FileResponse(INDEX_HTML)
