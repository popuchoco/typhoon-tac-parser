from __future__ import annotations

import re
from typing import Any

from ..models import Field, ParseResult
from ..normalization import normalize_tac, parse_heading
from .base import BaseParser


NAME_RE = re.compile(
    r"^NAME\s+(?P<classification>TY|TS|TD|STY|TYPHOON|TROPICAL\s+STORM|TROPICAL\s+DEPRESSION)\s+"
    r"(?P<number>\d{4})\s+(?P<name>[A-Z0-9-]+)(?:\s+\((?P<international>\d{4})\))?\s*$",
    re.I,
)
ANALYSIS_POSITION_RE = re.compile(
    r"^PSTN\s+(?P<time>\d{6})UTC\s+(?P<lat>\d{1,2}(?:\.\d+)?)(?P<lat_h>[NS])\s+"
    r"(?P<lon>\d{1,3}(?:\.\d+)?)(?P<lon_h>[EW])\s+(?P<quality>[A-Z]+)\s*$",
    re.I,
)
FORECAST_POSITION_RE = re.compile(
    r"^(?P<lead>\d{1,3})HF\s+(?P<time>\d{6})UTC\s+"
    r"(?P<lat>\d{1,2}(?:\.\d+)?)(?P<lat_h>[NS])\s+"
    r"(?P<lon>\d{1,3}(?:\.\d+)?)(?P<lon_h>[EW])\s+"
    r"(?P<accuracy>\d+)NM\s+(?P<probability>\d+)%\s*(?P<tail>.*)$",
    re.I,
)
MOVE_RE = re.compile(
    r"^MOVE\s+(?P<direction>[A-Z-]+)(?:\s+(?P<speed>\d+)\s*(?P<unit>KT|KTS|KNOTS|KM/H)|\s+(?P<qualifier>SLOWLY|RAPIDLY|STEADILY))?\s*$",
    re.I,
)
PRESSURE_RE = re.compile(r"^PRES\s+(?P<pressure>\d{3,4})HPA\s*$", re.I)
WIND_RE = re.compile(r"^(?P<kind>MXWD|GUST)\s+(?P<wind>\d{1,3})KT\s*$", re.I)
RADIUS_RE = re.compile(
    r"^(?P<threshold>\d{1,3})KT\s+(?P<first>\d+)NM\s+(?P<first_dir>NORTH|SOUTH|EAST|WEST)\s+"
    r"(?P<second>\d+)NM\s+(?P<second_dir>NORTH|SOUTH|EAST|WEST)\s*$",
    re.I,
)


def _signed_coordinate(value: str, hemisphere: str) -> float:
    number = float(value)
    return -number if hemisphere.upper() in {"S", "W"} else number


class RjtdTropicalCycloneParser(BaseParser):
    """Japan RSMC tropical cyclone advisory (RJTD WTPQ) parser."""

    def supports(self, normalized: str) -> bool:
        heading = parse_heading(normalized)
        if not heading or heading.get("center") != "RJTD" or heading.get("ttaa") != "WTPQ":
            return False
        return "RSMC TROPICAL CYCLONE ADVISORY" in normalize_tac(normalized).upper()

    def parse(self, raw: str) -> dict[str, Any]:
        normalized = normalize_tac(raw)
        heading = parse_heading(normalized)
        result = ParseResult(
            family="rjtd_tropical_cyclone_advisory",
            raw=raw,
            normalized=normalized,
            heading=heading,
        )
        result.fields["source_profile"] = {
            "value": "RJTD/RSMC Tokyo",
            "meaning": "Japan Meteorological Agency RSMC tropical cyclone advisory",
            "confidence": "high",
        }

        system: dict[str, Any] = {"identity": "UNKNOWN", "raw": normalized, "fields": {}}
        current_forecast: dict[str, Any] | None = None
        section = ""
        remarks: list[str] = []
        for line in normalized.splitlines():
            stripped = line.strip()
            if not stripped or (heading and stripped == heading["raw"]):
                continue
            upper = stripped.upper()
            if upper == "ANALYSIS":
                section = "analysis"
                current_forecast = None
                continue
            if upper == "FORECAST":
                section = "forecast"
                current_forecast = None
                continue
            name = NAME_RE.match(stripped)
            if name:
                classification = name.group("classification").upper()
                system["identity"] = f"{name.group('name').upper()} / {name.group('number')}"
                system["fields"].update({
                    "name": Field(name.group("name").upper(), name.group("name").upper(), meaning="storm name").to_dict(),
                    "storm_number": Field(name.group("number"), name.group("number"), meaning="tropical cyclone number").to_dict(),
                    "classification": Field(classification, self._classification_text(classification), meaning="current classification").to_dict(),
                })
                if name.group("international"):
                    system["fields"]["international_number"] = Field(name.group("international"), name.group("international"), meaning="international cyclone number").to_dict()
                continue
            analysis_position = ANALYSIS_POSITION_RE.match(stripped)
            if analysis_position:
                system["fields"].update(self._position_fields(analysis_position, analysis=True))
                continue
            forecast_position = FORECAST_POSITION_RE.match(stripped)
            if forecast_position:
                current_forecast = {
                    "lead_time": Field(forecast_position.group("lead") + "H", int(forecast_position.group("lead")), "hour", "forecast lead time").to_dict(),
                    "valid_time": Field(forecast_position.group("time") + "UTC", forecast_position.group("time") + "UTC", meaning="forecast valid time").to_dict(),
                    "position": self._position_value(forecast_position),
                    "position_accuracy": Field(forecast_position.group("accuracy") + " NM", int(forecast_position.group("accuracy")), "nm", "forecast position uncertainty radius").to_dict(),
                    "probability": Field(forecast_position.group("probability") + "%", int(forecast_position.group("probability")), "%", "forecast position probability").to_dict(),
                    "raw": stripped,
                }
                tail = forecast_position.group("tail").strip()
                if tail:
                    current_forecast["status"] = Field(tail, tail, meaning="forecast status or classification").to_dict()
                result.forecasts.append(current_forecast)
                continue

            target = current_forecast if current_forecast is not None else system["fields"]
            if move := MOVE_RE.match(stripped):
                movement: dict[str, Any] = {"direction": move.group("direction").upper()}
                if move.group("speed"):
                    movement["speed"] = int(move.group("speed"))
                    movement["unit"] = move.group("unit").lower()
                if move.group("qualifier"):
                    movement["qualifier"] = move.group("qualifier").upper()
                target["movement"] = Field(stripped, movement, meaning="storm movement").to_dict()
                continue
            if pressure := PRESSURE_RE.match(stripped):
                target["pressure"] = Field(stripped, int(pressure.group("pressure")), "hpa", "central pressure").to_dict()
                continue
            if wind := WIND_RE.match(stripped):
                key = "max_wind" if wind.group("kind").upper() == "MXWD" else "gust"
                target[key] = Field(stripped, int(wind.group("wind")), "kt", "maximum sustained wind" if key == "max_wind" else "gust wind").to_dict()
                continue
            if radius := RADIUS_RE.match(stripped):
                radii = target.setdefault("wind_radii", [])
                radii.extend(self._radius_fields(radius, stripped))
                continue
            if upper in {"RSMC TROPICAL CYCLONE ADVISORY", "NAME", "ANALYSIS", "FORECAST"} or upper.startswith("RSMC "):
                continue
            remarks.append(stripped)

        if system["identity"] != "UNKNOWN" or system["fields"]:
            result.systems.append(system)
        result.remarks = remarks
        result.fields["human_summary"] = self._summary(result)
        return result.to_dict()

    def _position_fields(self, match: re.Match[str], analysis: bool = False) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "position": self._position_value(match),
        }
        if analysis:
            fields["analysis_time"] = Field(match.group("time") + "UTC", match.group("time") + "UTC", meaning="analysis time").to_dict()
            fields["position_quality"] = Field(match.group("quality"), match.group("quality").upper(), meaning="analysis position quality").to_dict()
        return fields

    def _position_value(self, match: re.Match[str]) -> dict[str, Any]:
        return Field(
            f"{match.group('lat')}{match.group('lat_h')} {match.group('lon')}{match.group('lon_h')}",
            {
                "lat": _signed_coordinate(match.group("lat"), match.group("lat_h")),
                "lon": _signed_coordinate(match.group("lon"), match.group("lon_h")),
            },
            "degree",
            "storm center position",
        ).to_dict()

    def _radius_fields(self, match: re.Match[str], raw: str) -> list[dict[str, Any]]:
        threshold = int(match.group("threshold"))
        rows = []
        for radius, quadrant in ((match.group("first"), match.group("first_dir")), (match.group("second"), match.group("second_dir"))):
            radius_nm = int(radius)
            rows.append(Field(raw, {
                "threshold_kt": threshold,
                "radius_nm": radius_nm,
                "radius_km": round(radius_nm * 1.852, 1),
                "quadrant": quadrant.upper(),
            }, "nm", "wind radius by direction").to_dict())
        return rows

    def _classification_text(self, value: str) -> str:
        return {
            "TY": "TYPHOON",
            "TS": "TROPICAL STORM",
            "TD": "TROPICAL DEPRESSION",
            "STY": "SUPER TYPHOON",
        }.get(value.upper(), value.upper())

    def _summary(self, result: ParseResult) -> str:
        heading = result.heading or {}
        issue = heading.get("issue_time", {}).get("raw", "")
        if not result.systems:
            return f"RJTD 於 {issue}Z 發布熱帶氣旋預報。"
        system = result.systems[0]
        fields = system.get("fields", {})
        position = fields.get("position", {}).get("value")
        lines = [f"日本氣象廳(RJTD)於 {issue}Z 發布熱帶氣旋預報：{system['identity']}。"]
        if position:
            lines.append(f"目前位置 {position['lat']}N、{position['lon']}E。")
        lines.append(f"預報位置 {len(result.forecasts)} 筆。")
        return "\n".join(lines)
