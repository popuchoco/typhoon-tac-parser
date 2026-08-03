from __future__ import annotations

import re
from typing import Any

from ..models import Field, ParseResult
from ..normalization import normalize_tac, parse_heading
from .base import BaseParser


SIGNAL_ACTION_RE = re.compile(
    r"SIGNAL\s+NO\.(?P<number>\d+)\s+WAS\s+(?P<action>ISSUED|CANCELLED|REPLACED)\s+AT\s+(?P<time>\d{6})\s+UTC",
    re.I,
)
PRESENT_REPLACED_RE = re.compile(
    r"THE\s+PRESENT\s+SIGNAL\s+WILL\s+BE\s+REPLACED?E?\s+BY\s+SIGNAL\s+NO\.(?P<number>\d+)\s+AT\s+(?P<time>\d{6})\s+UTC",
    re.I,
)
ALL_CANCELLED_RE = re.compile(r"ALL\s+SIGNALS\s+WERE\s+CANCELLED\s+AT\s+(?P<time>\d{6})\s+UTC", re.I)


class VmmcSignalParser(BaseParser):
    """Macao VMMC tropical cyclone signal bulletin parser."""

    def supports(self, normalized: str) -> bool:
        heading = parse_heading(normalized)
        if not heading or heading.get("center") != "VMMC":
            return False
        return bool(SIGNAL_ACTION_RE.search(normalized) or PRESENT_REPLACED_RE.search(normalized) or ALL_CANCELLED_RE.search(normalized))

    def parse(self, raw: str) -> dict[str, Any]:
        normalized = normalize_tac(raw).rstrip("=")
        heading = parse_heading(normalized)
        result = ParseResult(family="vmmc_tropical_cyclone_signal", raw=raw, normalized=normalized, heading=heading)
        result.fields["source_profile"] = {
            "value": "VMMC tropical cyclone signal",
            "meaning": "Macao Meteorological and Geophysical Bureau tropical cyclone signal bulletin",
            "confidence": "high",
        }

        if match := SIGNAL_ACTION_RE.search(normalized):
            self._fill_signal_result(result, match.group(0), int(match.group("number")), match.group("action").upper(), match.group("time") + "UTC")
        elif match := PRESENT_REPLACED_RE.search(normalized):
            self._fill_signal_result(result, match.group(0), int(match.group("number")), "WILL_BE_REPLACED", match.group("time") + "UTC")
        elif match := ALL_CANCELLED_RE.search(normalized):
            self._fill_cancelled_result(result, match.group(0), match.group("time") + "UTC")
        return result.to_dict()

    def _fill_signal_result(self, result: ParseResult, raw: str, number: int, action: str, time: str) -> None:
        signal_name = self._signal_name(number)
        result.fields["signal_number"] = Field(str(number), number, meaning="tropical cyclone signal number").to_dict()
        result.fields["signal_action"] = Field(action, self._action_zh(action), meaning="signal action").to_dict()
        result.fields["signal_time"] = Field(time, time, meaning="signal action time").to_dict()
        result.fields["human_summary"] = f"澳門地球物理氣象局(VMMC)將於{time} {self._action_phrase(action)}{signal_name}。"
        if action == "ISSUED":
            result.fields["human_summary"] = f"澳門地球物理氣象局(VMMC)於{time} 發出{signal_name}。"
        result.systems.append({
            "identity": signal_name,
            "raw": raw,
            "fields": {
                "classification": Field(f"SIGNAL NO.{number}", signal_name, meaning="tropical cyclone signal").to_dict(),
                "analysis_time": Field(time, time, meaning="signal action time").to_dict(),
            },
            "discussion": [result.fields["human_summary"]],
        })

    def _fill_cancelled_result(self, result: ParseResult, raw: str, time: str) -> None:
        result.fields["signal_action"] = Field("CANCELLED", "取消", meaning="signal action").to_dict()
        result.fields["signal_time"] = Field(time, time, meaning="signal action time").to_dict()
        result.fields["human_summary"] = f"澳門地球物理氣象局(VMMC)於{time} 取消所有熱帶氣旋信號。"
        result.systems.append({
            "identity": "所有熱帶氣旋信號取消",
            "raw": raw,
            "fields": {
                "classification": Field("ALL SIGNALS CANCELLED", "所有熱帶氣旋信號取消", meaning="tropical cyclone signal status").to_dict(),
                "analysis_time": Field(time, time, meaning="signal action time").to_dict(),
            },
            "discussion": [result.fields["human_summary"]],
        })

    def _signal_name(self, number: int) -> str:
        return {
            1: "一號風球",
            3: "三號風球",
            8: "八號風球",
            9: "九號風球",
            10: "十號風球",
        }.get(number, f"{number}號風球")

    def _action_zh(self, action: str) -> str:
        return {
            "ISSUED": "發出",
            "CANCELLED": "取消",
            "REPLACED": "取代",
            "WILL_BE_REPLACED": "將改發",
        }.get(action, action)

    def _action_phrase(self, action: str) -> str:
        return {
            "ISSUED": "發出",
            "CANCELLED": "取消",
            "REPLACED": "改發",
            "WILL_BE_REPLACED": "改發",
        }.get(action, action)
