"""Local Laya decision port, limited to bounded choice questions.

The local server is an optional judgment backend. Structural evidence and task
authorization remain with the MotifAgent runtime, not with Laya.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener


@dataclass(frozen=True)
class ChoiceDecision:
    question_id: str
    choice: str
    probability: float | None
    confidence: float | None
    model: str
    raw: dict[str, Any]


class LayaDecisionPort:
    def __init__(self, endpoint: str = "http://127.0.0.1:8766/v1/systemone", timeout_seconds: float = 30.0):
        parsed = urlparse(endpoint)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Laya endpoint must be a local HTTP address")
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def choose(self, *, state: str, question_id: str, instructions: str,
               criteria: dict[str, str], model: str = "multilingual") -> ChoiceDecision:
        if model not in {"english", "multilingual", "typed-decisions"}:
            raise ValueError("unrecognized Laya checkpoint")
        if not isinstance(state, str) or not state.strip() or len(state) > 12_000:
            raise ValueError("state must be nonempty and within the local budget")
        if not isinstance(question_id, str) or not question_id or not isinstance(instructions, str) or not instructions:
            raise ValueError("question id and instructions are required")
        if not isinstance(criteria, dict) or not 2 <= len(criteria) <= 12 or any(
            not isinstance(key, str) or not key or not isinstance(value, str) or not value
            for key, value in criteria.items()
        ):
            raise ValueError("choice needs 2–12 described candidates")
        payload = {
            "state": state, "model": model,
            "questions": {question_id: {"type": "choice", "instructions": instructions, "criteria": criteria}},
        }
        request = Request(self.endpoint, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                          headers={"Content-Type": "application/json"}, method="POST")
        # The endpoint is loopback-only; bypass host-level HTTP proxies explicitly.
        with build_opener(ProxyHandler({})).open(request, timeout=self.timeout_seconds) as response:
            result = json.load(response)
        if not isinstance(result, dict) or not isinstance(result.get("answers"), dict):
            raise ValueError("invalid Laya response shape")
        answer = result["answers"].get(question_id)
        if not isinstance(answer, dict) or answer.get("choice") not in criteria:
            raise ValueError("Laya chose a candidate outside the offered set")
        probabilities = answer.get("probabilities")
        if not isinstance(probabilities, dict) or set(probabilities) != set(criteria):
            raise ValueError("Laya returned incomplete choice probabilities")
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) or not 0 <= value <= 1 for value in probabilities.values()):
            raise ValueError("Laya returned invalid choice probabilities")
        if abs(sum(probabilities.values()) - 1) > 0.01:
            raise ValueError("Laya choice probabilities do not sum to one")
        for field in ("answer_confidence", "confidence"):
            value = answer.get(field)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or not math.isfinite(value) or not 0 <= value <= 1):
                raise ValueError(f"invalid {field} from Laya")
        return ChoiceDecision(
            question_id=question_id, choice=answer["choice"],
            probability=probabilities[answer["choice"]], confidence=answer.get("confidence"),
            model=str((result.get("routing") or {}).get("model") or result.get("model") or model), raw=result,
        )
