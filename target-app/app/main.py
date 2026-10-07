"""Target chatbot for the AI Red-Team Pipeline.

DELIBERATELY VULNERABLE (v1) so the red-team suite has something to find:
  - fake secrets live inside the system prompt (leakage target)
  - user input goes to the model with no filtering (injection target)
  - the UI renders replies with innerHTML (XSS / output-handling target)

Set GUARDRAIL_ENABLED=true (and GUARDRAIL_URL) to put the ML guardrail service
(guardrail/service.py) in front of the model.
"""
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import SYSTEM_PROMPT

# 127.0.0.1, not "localhost": on Windows "localhost" can resolve to IPv6 (::1)
# first while Ollama only listens on IPv4, which caused 502 errors.
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
MODEL_NAME = os.getenv("MODEL_NAME", "qwen2.5:3b")
GUARDRAIL_ENABLED = os.getenv("GUARDRAIL_ENABLED", "false").lower() == "true"
GUARDRAIL_URL = os.getenv("GUARDRAIL_URL", "http://127.0.0.1:8001")

app = FastAPI(title="AcmeBank Support Bot (vulnerable target)", version="0.1.0")
STATIC_DIR = Path(__file__).parent / "static"


class ChatRequest(BaseModel):
    message: str = Field(..., max_length=4000)


class ChatResponse(BaseModel):
    reply: str
    blocked: bool = False
    guardrail_enabled: bool = GUARDRAIL_ENABLED


async def guardrail_check(message: str) -> bool:
    """Return True if the guardrail service says the message is an attack.

    Fails CLOSED but loudly: if the guardrail is unreachable we answer 503
    (not "blocked"), so a broken guardrail can never make the red-team suite
    look like it passed. The runner reports 503s as ERROR (inconclusive).
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{GUARDRAIL_URL}/check", json={"text": message})
            r.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Guardrail unavailable: {exc}")
    return bool(r.json()["attack"])


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_NAME, "guardrail": GUARDRAIL_ENABLED}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if GUARDRAIL_ENABLED and await guardrail_check(req.message):
        return ChatResponse(
            reply="Sorry, I can't help with that request.", blocked=True
        )

    payload = {
        "model": MODEL_NAME,
        "stream": False,
        "options": {"temperature": 0},  # keep tests as reproducible as possible
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": req.message},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(f"{OLLAMA_HOST}/api/chat", json=payload)
            r.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Ollama unreachable: {exc}")

    return ChatResponse(reply=r.json()["message"]["content"])


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")