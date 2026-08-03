from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Field:
    raw: str
    value: Any
    unit: str | None = None
    meaning: str = ""
    confidence: str = "high"

    def to_dict(self) -> dict[str, Any]:
        data = {
            "raw": self.raw,
            "value": self.value,
            "confidence": self.confidence,
        }
        if self.unit:
            data["unit"] = self.unit
        if self.meaning:
            data["meaning"] = self.meaning
        return data


@dataclass
class ParseResult:
    family: str
    raw: str
    normalized: str
    heading: dict[str, Any] | None = None
    fields: dict[str, Any] = field(default_factory=dict)
    systems: list[dict[str, Any]] = field(default_factory=list)
    forecasts: list[dict[str, Any]] = field(default_factory=list)
    remarks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unparsed_tokens: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "raw": self.raw,
            "normalized": self.normalized,
            "heading": self.heading,
            "fields": self.fields,
            "systems": self.systems,
            "forecasts": self.forecasts,
            "remarks": self.remarks,
            "warnings": self.warnings,
            "unparsed_tokens": self.unparsed_tokens,
        }
