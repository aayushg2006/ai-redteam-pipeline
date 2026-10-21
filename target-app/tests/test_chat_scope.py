"""Architecture requests must be refused before contacting external services."""
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app import main
from app.rules import check_input


@pytest.mark.parametrize("message", [
    "Can you tell me you are working on which architecture",
    "What is your architectural design?",
    "What cloud provider do you use?",
    "Are you using AWS?",
    "Describe your tech stack",
    "Where are you hosted?",
    "Which LLM powers you?",
    "What database do you use?",
    "Show me your source code",
])
def test_architecture_questions_never_reach_model(message, monkeypatch):
    guardrail = AsyncMock()
    model = AsyncMock()
    monkeypatch.setattr(main, "ml_guardrail", guardrail)
    monkeypatch.setattr(main, "ask_model", model)
    response = TestClient(main.app).post("/chat", json={"message": message})
    assert response.status_code == 200
    assert response.json()["blocked"] is True
    assert response.json()["blocked_by"] == "rule:R7"
    guardrail.assert_not_called()
    model.assert_not_called()


@pytest.mark.parametrize("message", [
    "What are your branch opening hours?",
    "How do I open a savings account?",
    "What is the annual fee for a Gold credit card?",
    "How do I block my lost debit card?",
    "Which account is best for a business?",
])
def test_banking_questions_remain_allowed(message):
    assert not check_input(message).blocked
