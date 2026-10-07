"""Guardrail HTTP service.

  uvicorn guardrail.service:app --port 8001

POST /check  {"text": "..."}  ->  {"attack": bool, "score": float, "model_version": str}
GET  /health                  ->  model version + threshold

Runs as its own container so the model can be built, versioned and deployed
independently of the chatbot.
"""
from functools import lru_cache

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .detector import Detector

app = FastAPI(title="Prompt-injection guardrail", version="0.1.0")


@lru_cache(maxsize=1)
def get_detector() -> Detector:
    return Detector()


class CheckRequest(BaseModel):
    text: str = Field(..., max_length=20000)


class CheckResponse(BaseModel):
    attack: bool
    score: float
    model_version: str


@app.get("/health")
def health():
    d = get_detector()
    return {"status": "ok", "model_version": d.version, "threshold": d.threshold}


@app.post("/check", response_model=CheckResponse)
def check(req: CheckRequest):
    d = get_detector()
    score = d.score(req.text)
    return CheckResponse(attack=score >= d.threshold, score=round(score, 4), model_version=d.version)