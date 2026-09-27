"""Typed, bounded semantic choices requested by deterministic tool adapters."""

from __future__ import annotations


class SemanticInputRequired(ValueError):
    """A read-only tool found explicit choices but cannot select one safely."""

    def __init__(self, parameter: str, candidates: list[str] | tuple[str, ...],
                 details: dict[str, dict] | None = None):
        choices = tuple(candidates)
        if (not isinstance(parameter, str) or not parameter
                or not 1 <= len(choices) <= 50
                or any(not isinstance(item, str) or not item for item in choices)
                or len(set(choices)) != len(choices)):
            raise ValueError("semantic choices must be bounded, nonempty strings")
        self.parameter = parameter
        self.candidates = choices
        details = details or {}
        if (not isinstance(details, dict) or set(details) - set(choices)
                or any(not isinstance(item, dict)
                       or set(item) != {"record_count", "fields"}
                       or type(item["record_count"]) is not int
                       or not 0 <= item["record_count"] <= 100_000
                       or not isinstance(item["fields"], list)
                       or len(item["fields"]) > 30
                       or any(not isinstance(field, str) or not field
                              or len(field) > 120 for field in item["fields"])
                       for item in details.values())):
            raise ValueError("semantic choice details must contain bounded schemas")
        self.details = details
        super().__init__(f"{parameter} requires an explicit choice: {', '.join(choices)}")
