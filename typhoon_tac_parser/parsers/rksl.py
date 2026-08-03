from __future__ import annotations

import re
from typing import Any

from ..models import Field, ParseResult
from ..normalization import normalize_tac, parse_heading
from .base import BaseParser
from .tropical import signed_coord


COORD_RE = re.compile(r"(?P<lat>\d{1,2}(?:\.\d+)?)(?P<lat_h>[NS])\s+(?P<lon>\d{1,3}(?:\.\d+)?)(?P<lon_h>[EW])")
ADVISORY_RE = re.compile(r"KMA\s+TROPICAL\s+CYCLONE\s+ADVISORY\s+NO\.\s*(?P<number>\d+)", re.I)
NAME_RE = re.compile(r"NAME\s+(?P<number>\d{4})\s+(?P<name>[A-Z0-9-]+)", re.I)
POSITION_RE = re.compile(r"POSITION\s+(?P<time>\d{6})UTC\s+(?P<coord>\d{1,2}(?:\.\d+)?[NS]\s+\d{1,3}(?:\.\d+)?[EW])(?:\s+WITHIN\s+(?P<accuracy>\d+)NM)?", re.I)
MOVEMENT_RE = re.compile(r"MOVEMENT\s+(?P<direction>[A-Z]+)\s+(?P<speed>\d+)KT", re.I)
PRES_VMAX_RE = re.compile(r"PRES/VMAX\s+(?P<pressure>\d{3,4})HPA\s+(?P<wind>\d+)KT", re.I)
LEAD_RE = re.compile(r"^(?P<hour>\d+)HR$", re.I)


class RkslKmaAdvisoryParser(BaseParser):
    """Korea Meteorological Administration RKSL tropical cyclone advisory parser."""

    def supports(self, normalized: str) -> bool:
        heading = parse_heading(normalized)
        return bool(heading and heading.get("center") == "RKSL" and "KMA TROPICAL CYCLONE ADVISORY" in normalized.upper())

    def parse(self, raw: str) -> dict[str, Any]:
        normalized = normalize_tac(raw).rstrip("=")
        heading = parse_heading(normalized)
        lines = [line.strip() for line in normalized.splitlines() if line.strip()]
        result = ParseResult(family="tropical_cyclone", raw=raw, normalized=normalized, heading=heading)
        result.fields["source_profile"] = {
            "value": "RKSL KMA tropical cyclone advisory",
            "meaning": "Korea Meteorological Administration tropical cyclone advisory",
            "confidence": "high",
        }
        advisory_number = self._advisory_number(lines)
        if advisory_number is not None:
            result.fields["advisory_number"] = Field(str(advisory_number), advisory_number, meaning="KMA advisory number").to_dict()

        identity = self._identity(lines)
        system = {"identity": " / ".join(part for part in (identity.get("name"), identity.get("number")) if part) or "TROPICAL CYCLONE", "raw": normalized, "fields": {}, "discussion": []}
        if identity.get("name"):
            system["fields"]["name"] = Field(identity["name"], identity["name"], meaning="storm name").to_dict()
        if identity.get("number"):
            system["fields"]["storm_number"] = Field(identity["number"], identity["number"], meaning="tropical cyclone number").to_dict()

        analysis_fields = self._analysis_fields(lines)
        system["fields"].update(analysis_fields)
        system["discussion"] = self._discussion(advisory_number, system["fields"])
        result.systems.append(system)
        result.forecasts = self._forecasts(lines)
        return result.to_dict()

    def _advisory_number(self, lines: list[str]) -> int | None:
        for line in lines:
            if match := ADVISORY_RE.search(line):
                return int(match.group("number"))
        return None

    def _identity(self, lines: list[str]) -> dict[str, str]:
        for line in lines:
            if match := NAME_RE.search(line):
                return {"number": match.group("number"), "name": match.group("name").upper()}
        return {}

    def _analysis_fields(self, lines: list[str]) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        in_analysis = False
        for line in lines:
            upper = line.upper()
            if upper == "ANALYSIS":
                in_analysis = True
                continue
            if upper == "FORECAST":
                break
            if not in_analysis:
                continue
            if match := POSITION_RE.search(line):
                fields["analysis_time"] = Field(match.group("time") + "UTC", match.group("time") + "UTC", meaning="analysis time").to_dict()
                fields["position"] = self._position_field(match.group("coord"))
            if match := MOVEMENT_RE.search(line):
                fields["movement"] = Field(
                    match.group(0),
                    {"direction": match.group("direction").upper(), "speed": int(match.group("speed"))},
                    "kt",
                    "current movement",
                ).to_dict()
            if match := PRES_VMAX_RE.search(line):
                fields["pressure"] = Field(match.group("pressure") + "HPA", int(match.group("pressure")), "hpa", "central pressure").to_dict()
                fields["max_wind"] = Field(match.group("wind") + "KT", int(match.group("wind")), "kt", "maximum sustained wind").to_dict()
        return fields

    def _forecasts(self, lines: list[str]) -> list[dict[str, Any]]:
        forecasts = []
        in_forecast = False
        pending: dict[str, Any] | None = None
        for line in lines:
            upper = line.upper()
            if upper == "FORECAST":
                in_forecast = True
                continue
            if not in_forecast:
                continue
            if lead := LEAD_RE.match(upper):
                if pending:
                    forecasts.append(pending)
                hour = int(lead.group("hour"))
                pending = {"lead_time": Field(line, hour, "hour", "forecast lead time").to_dict(), "raw": line}
                continue
            if pending is None:
                continue
            if match := POSITION_RE.search(line):
                pending["valid_time"] = Field(match.group("time") + "UTC", match.group("time") + "UTC", meaning="forecast valid time").to_dict()
                pending["position"] = self._position_field(match.group("coord"))
                if match.group("accuracy"):
                    pending["position_accuracy"] = Field(match.group("accuracy") + "NM", int(match.group("accuracy")), "nm", "forecast position uncertainty radius").to_dict()
                pending["raw"] += " " + line
            if match := PRES_VMAX_RE.search(line):
                pending["pressure"] = Field(match.group("pressure") + "HPA", int(match.group("pressure")), "hpa", "forecast central pressure").to_dict()
                pending["max_wind"] = Field(match.group("wind") + "KT", int(match.group("wind")), "kt", "forecast maximum sustained wind").to_dict()
                pending["raw"] += " " + line
        if pending:
            forecasts.append(pending)
        return forecasts

    def _position_field(self, raw_coord: str) -> dict[str, Any]:
        return Field(raw_coord, self._position(raw_coord), "degree", "storm center position").to_dict()

    def _position(self, raw_coord: str) -> dict[str, float] | None:
        match = COORD_RE.search(raw_coord)
        if not match:
            return None
        return {
            "lat": signed_coord(match.group("lat"), match.group("lat_h")),
            "lon": signed_coord(match.group("lon"), match.group("lon_h")),
        }

    def _discussion(self, advisory_number: int | None, fields: dict[str, Any]) -> list[str]:
        parts = []
        if advisory_number is not None:
            parts.append(f"KMA 發布第 {advisory_number} 號熱帶氣旋警報。")
        if fields.get("position"):
            pos = fields["position"]["value"]
            parts.append(f"分析位置 {pos['lat']}N、{pos['lon']}E。")
        if fields.get("movement"):
            mov = fields["movement"]["value"]
            parts.append(f"移動方向 {mov['direction']}，速度 {mov['speed']} kt。")
        if fields.get("pressure") or fields.get("max_wind"):
            parts.append(f"中心氣壓 {fields.get('pressure', {}).get('value')} hPa，最大風 {fields.get('max_wind', {}).get('value')} kt。")
        return parts
