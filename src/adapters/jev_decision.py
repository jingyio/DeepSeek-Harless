"""Opt-in TypeSafe Jev Choice port for a bounded SSS semantic handoff.

No request is made during construction. A real request needs both an API key
and explicit paid-call enablement from the caller.
"""

from __future__ import annotations

import json
import math
import os
from urllib.request import Request, urlopen

from src.adapters.laya_decision import ChoiceDecision


class JevDecisionPort:
    backend_name = "jev_api"
    endpoint = "https://api.typesafe.ai/v1/systemone"

    def __init__(self, *, api_key: str | None = None,
                 allow_paid_requests: bool = False,
                 timeout_seconds: float = 30.0):
        self.api_key = api_key or os.environ.get("TYPESAFE_API_KEY")
        self.allow_paid_requests = allow_paid_requests
        self.timeout_seconds = timeout_seconds

    def choose(self, *, state: str, question_id: str, instructions: str,
               criteria: dict[str, str], model: str = "jev-latest") -> ChoiceDecision:
        if not self.allow_paid_requests:
            raise PermissionError("Jev API requests require explicit paid-call enablement")
        if not self.api_key:
            raise ValueError("TYPESAFE_API_KEY is not configured")
        if (not isinstance(state, str) or not state.strip() or len(state) > 12000
                or not isinstance(question_id, str) or not question_id
                or not isinstance(instructions, str) or not instructions
                or not isinstance(criteria, dict) or not 2 <= len(criteria) <= 12
                or any(not isinstance(key, str) or not key
                       or not isinstance(value, str) or not value
                       for key, value in criteria.items())
                or not isinstance(model, str) or not model.startswith("jev-")):
            raise ValueError("Jev choice exceeds the bounded request scope")
        payload = {
            "model": model, "state": state,
            "questions": {question_id: {
                "type": "choice", "instructions": instructions,
                "criteria": criteria}},
        }
        request = Request(
            self.endpoint, data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=self.timeout_seconds) as response:
            result = json.load(response)
        answers = result.get("answers") if isinstance(result, dict) else None
        answer = answers.get(question_id) if isinstance(answers, dict) else None
        probabilities = answer.get("probabilities") if isinstance(answer, dict) else None
        choice = answer.get("choice") if isinstance(answer, dict) else None
        if (not isinstance(answer, dict) or answer.get("type") != "choice"
                or choice not in criteria or not isinstance(probabilities, dict)
                or set(probabilities) != set(criteria)
                or any(isinstance(value, bool) or not isinstance(value, (int, float))
                       or not math.isfinite(value) or not 0 <= value <= 1
                       for value in probabilities.values())
                or abs(sum(probabilities.values()) - 1) > .01
                or probabilities[choice] < max(probabilities.values())):
            raise ValueError("Jev response does not match bounded Choice question")
        confidence = answer.get("confidence")
        if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                or not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError("Jev returned invalid confidence")
        return ChoiceDecision(
            question_id, choice, float(probabilities[choice]), float(confidence),
            str(result.get("model") or model), result)
