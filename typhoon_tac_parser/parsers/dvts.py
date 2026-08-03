from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from ..centers import issuing_agency
from ..models import Field, ParseResult
from ..normalization import normalize_tac
from .base import BaseParser


DVTS_LINE_RE = re.compile(
    r"^(?P<basin>[A-Z]{2})\s+"
    r"(?P<number>\d{1,2})\s+"
    r"(?P<time>\d{12})\s+"
    r"(?P<type>DVTS)\s+"
    r"(?P<lat>\d{4}[NS])\s+"
    r"(?P<lon>\d{5}[EW])\s+"
    r"(?P<wind>\d+(?:\.\d+)?)\s+"
    r"(?P<tci>\d{4}|////)\s+"
    r"(?P<trend>[DSW]\d{4}|/{4,5})\s+"
    r"(?P<center>[A-Z]{4})$",
    re.I,
)


class DvtsAutoDvorakParser(BaseParser):
    """Agency automatic Dvorak analysis, one TAC line per issuing center."""

    def supports(self, normalized: str) -> bool:
        lines = [line.strip() for line in normalized.splitlines() if line.strip()]
        return bool(lines) and all(DVTS_LINE_RE.match(line.rstrip("=")) for line in lines)

    def parse(self, raw: str) -> dict[str, Any]:
        normalized = normalize_tac(raw)
        result = ParseResult(family="agency_auto_dvorak_analysis", raw=raw, normalized=normalized, heading=None)
        systems = []
        for line in normalized.splitlines():
            line = line.strip().rstrip("=")
            if not line:
                continue
            match = DVTS_LINE_RE.match(line)
            if not match:
                result.warnings.append(f"Unparsed DVTS line: {line}")
                continue
            systems.append(self._system(match, line))
        result.systems = systems
        result.fields["record_count"] = Field(str(len(systems)), len(systems), meaning="number of DVTS records").to_dict()
        result.fields["human_summary"] = self._summary(systems)
        return result.to_dict()

    def _system(self, match: re.Match[str], raw: str) -> dict[str, Any]:
        center = match.group("center").upper()
        tci = self._tci(match.group("tci"))
        trend = self._trend(match.group("trend"))
        fields = {
            "basin": Field(match.group("basin").upper(), match.group("basin").upper(), meaning="ocean basin code").to_dict(),
            "storm_number": Field(match.group("number"), int(match.group("number")), meaning="tropical cyclone number").to_dict(),
            "analysis_time": self._time(match.group("time")),
            "message_type": Field(match.group("type").upper(), "氣象機構德沃夏克自動分析", meaning="automatic Dvorak analysis report").to_dict(),
            "position": Field(
                f"{match.group('lat')} {match.group('lon')}",
                {"lat": self._lat(match.group("lat")), "lon": self._lon(match.group("lon"))},
                "degree",
                "analyzed position",
            ).to_dict(),
            "wind": Field(match.group("wind"), float(match.group("wind")), "kt", "estimated wind speed").to_dict(),
            "dvorak": Field(match.group("tci"), tci, meaning="T-number and CI number").to_dict(),
            "trend": Field(match.group("trend"), trend, meaning="Dvorak intensity trend").to_dict(),
            "issuing_center": Field(center, center, meaning="issuing center").to_dict(),
            "issuing_agency": Field(center, issuing_agency(center) or center, meaning="issuing agency").to_dict(),
        }
        return {
            "identity": f"{match.group('basin').upper()}{int(match.group('number')):02d} {center}",
            "raw": raw,
            "fields": fields,
        }

    def _summary(self, systems: list[dict[str, Any]]) -> str:
        if not systems:
            return "未解析到 DVTS 自動德沃夏克分析資料。"
        lines = [f"共解析 {len(systems)} 筆氣象機構德沃夏克自動分析。"]
        for system in systems:
            fields = system["fields"]
            pos = fields["position"]["value"]
            dvorak = fields["dvorak"]["value"]
            trend = fields["trend"]["value"]
            lines.append(
                f"{fields['issuing_agency']['value']}({fields['issuing_center']['value']})："
                f"{fields['basin']['value']}{int(fields['storm_number']['value']):02d}，"
                f"{fields['analysis_time']['value']['iso']} UTC，"
                f"位於 {self._coord_text(pos['lat'], 'lat')}、{self._coord_text(pos['lon'], 'lon')}，"
                f"風速 {self._format_number(fields['wind']['value'])} kt，"
                f"{self._dvorak_text(dvorak)}，{self._trend_text(trend)}。"
            )
        return "\n".join(lines)

    def _time(self, text: str) -> dict[str, Any]:
        dt = datetime.strptime(text, "%Y%m%d%H%M")
        return Field(text, {
            "year": dt.year,
            "month": dt.month,
            "day": dt.day,
            "hour": dt.hour,
            "minute": dt.minute,
            "timezone": "UTC",
            "iso": dt.strftime("%Y-%m-%d %H:%M"),
        }, meaning="analysis time").to_dict()

    def _lat(self, text: str) -> float:
        value = int(text[:-1]) / 100
        return -value if text[-1].upper() == "S" else value

    def _lon(self, text: str) -> float:
        value = int(text[:-1]) / 100
        return -value if text[-1].upper() == "W" else value

    def _tci(self, text: str) -> dict[str, Any]:
        if set(text) == {"/"}:
            return {"available": False}
        return {"available": True, "t_number": int(text[:2]) / 10, "ci_number": int(text[2:]) / 10}

    def _trend(self, text: str) -> dict[str, Any]:
        if set(text) == {"/"}:
            return {"available": False}
        direction = {"D": "developing", "S": "steady", "W": "weakening"}.get(text[0].upper(), text[0].upper())
        return {"available": True, "direction": direction, "change": int(text[1:3]) / 10, "hours": int(text[3:])}

    def _dvorak_text(self, value: dict[str, Any]) -> str:
        if not value.get("available"):
            return "T/CI 未提供"
        return f"T{value['t_number']:.1f}/CI{value['ci_number']:.1f}"

    def _trend_text(self, value: dict[str, Any]) -> str:
        if not value.get("available"):
            return "趨勢未提供"
        direction = {"developing": "增強", "steady": "維持", "weakening": "減弱"}.get(value["direction"], value["direction"])
        return f"過去 {value['hours']} 小時{direction} {value['change']:.1f}"

    def _format_number(self, value: float) -> str:
        return str(int(value)) if value.is_integer() else str(value)

    def _coord_text(self, value: float, axis: str) -> str:
        hemi = "N" if axis == "lat" and value >= 0 else "S" if axis == "lat" else "E" if value >= 0 else "W"
        return f"{abs(value):.2f}{hemi}"
