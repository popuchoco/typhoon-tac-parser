from __future__ import annotations

import re
from typing import Any

from ..models import Field, ParseResult
from ..normalization import normalize_tac, parse_heading
from .base import BaseParser


COORD_RE = re.compile(r"\(\s*(?P<lat>\d{1,2}(?:\.\d+)?)\s*(?P<lat_h>[NS])\s*\)\s+.*?\(\s*(?P<lon>\d{1,3}(?:\.\d+)?)\s*(?P<lon_h>[EW])\s*\)", re.I)
IDENTITY_RE = re.compile(r"\b(?P<classification>TYPHOON|TROPICAL STORM|TROPICAL DEPRESSION|SEVERE TROPICAL STORM)\s+(?P<name>[A-Z0-9-]+)\s+\((?P<number>\d{4})\)", re.I)
CURRENT_RE = re.compile(
    r"AT\s+(?P<time>\d{6})\s+UTC,\s+(?P<classification>TYPHOON|TROPICAL STORM|TROPICAL DEPRESSION|SEVERE TROPICAL STORM)\s+(?P<name>[A-Z0-9-]+)\s+\((?P<number>\d{4})\)\s+WITH\s+CENTRAL\s+PRESSURE\s+(?P<pressure>\d{3,4})\s+HECTOPASCALS.*?CENTRED\s+WITHIN\s+(?P<accuracy>\d+)\s+NAUTICAL\s+MILES\s+OF\s+(?P<coord_text>.*?)\s+AND\s+IS\s+FORECAST\s+TO\s+MOVE\s+(?P<direction>[A-Z-]+)\s+AT\s+ABOUT\s+(?P<speed>\d+)\s+KNOTS\s+FOR\s+THE\s+NEXT\s+(?P<period>\d+)\s+HOURS",
    re.I | re.S,
)
MAX_WIND_RE = re.compile(r"MAXIMUM\s+WINDS\s+NEAR\s+THE\s+CENTRE\s+ARE\s+ESTIMATED\s+TO\s+BE\s+(?P<wind>\d+)\s+KNOTS", re.I)
WIND_RADIUS_RE = re.compile(
    r"RADIUS\s+OF\s+OVER\s+(?P<threshold>\d+)\s+KNOT\s+WINDS\s+(?P<first>\d+)\s+NAUTICAL\s+MILES(?:\s+OVER\s+(?P<area>[A-Z\s]+?)(?:,|\.)\s*(?P<second>\d+)?\s*NAUTICAL\s+MILES\s+(?P<second_area>ELSEWHERE))?",
    re.I,
)
WAVE_RADIUS_RE = re.compile(
    r"RADIUS\s+OF\s+OVER\s+(?P<height>\d+)\s+METRE\s+WAVES\s+(?P<first>\d+)\s+NAUTICAL\s+MILES\s+OVER\s+(?P<area>[A-Z\s]+?)(?:,|\.)\s*(?P<second>\d+)?\s*NAUTICAL\s+MILES\s+(?P<second_area>ELSEWHERE)",
    re.I,
)
FORECAST_BLOCK_RE = re.compile(
    r"FORECAST\s+POSITION\s+AND\s+INTENSITY\s+AT\s+(?P<time>\d{6})\s+UTC\s+(?P<body>.*?)(?=FORECAST\s+POSITION\s+AND\s+INTENSITY\s+AT|$)",
    re.I | re.S,
)
FORECAST_WIND_RE = re.compile(r"MAXIMUM\s+WINDS\s+(?P<wind>\d+)\s+KNOTS", re.I)


class VhhhTropicalCycloneWarningParser(BaseParser):
    """Hong Kong Observatory VHHH tropical cyclone warning parser."""

    def supports(self, normalized: str) -> bool:
        heading = parse_heading(normalized)
        if not heading or heading.get("center") != "VHHH":
            return False
        text = normalize_tac(normalized).upper()
        return "TROPICAL CYCLONE WARNING" in text or bool(IDENTITY_RE.search(text))

    def parse(self, raw: str) -> dict[str, Any]:
        normalized = normalize_tac(raw).rstrip("=")
        heading = parse_heading(normalized)
        compact = re.sub(r"\s+", " ", normalized)
        result = ParseResult(family="vhhh_tropical_cyclone_warning", raw=raw, normalized=normalized, heading=heading)
        result.fields["source_profile"] = {
            "value": "VHHH WIS-JMA Warning/Tropical_cyclone",
            "meaning": "Hong Kong Observatory tropical cyclone warning bulletin from WIS-JMA",
            "confidence": "high",
        }
        system = self._system(compact)
        if system:
            result.systems.append(system)
        result.forecasts = self._forecasts(compact, system)
        result.fields["human_summary"] = self._summary(heading, system, result.forecasts)
        return result.to_dict()

    def _system(self, text: str) -> dict[str, Any] | None:
        current = CURRENT_RE.search(text)
        identity = IDENTITY_RE.search(text)
        if not current and not identity:
            return None
        source = current or identity
        name = source.group("name").upper()
        number = source.group("number")
        classification = re.sub(r"\s+", " ", source.group("classification").upper())
        fields: dict[str, Any] = {
            "name": Field(name, name, meaning="storm name").to_dict(),
            "storm_number": Field(number, number, meaning="tropical cyclone number").to_dict(),
            "classification": Field(classification, self._classification_zh(classification), meaning="current classification").to_dict(),
        }
        if current:
            fields["analysis_time"] = Field(current.group("time") + "UTC", current.group("time") + "UTC", meaning="analysis time").to_dict()
            fields["pressure"] = Field(current.group("pressure") + " hPa", int(current.group("pressure")), "hpa", "central pressure").to_dict()
            fields["position_accuracy"] = Field(current.group("accuracy") + " NM", int(current.group("accuracy")), "nm", "position accuracy radius").to_dict()
            coord = self._coord_from_text(current.group("coord_text"))
            if coord:
                fields["position"] = Field(current.group("coord_text"), coord, "degree", "storm center position").to_dict()
            fields["movement"] = Field(
                current.group(0),
                {"direction": current.group("direction").upper(), "speed": int(current.group("speed")), "period_hours": int(current.group("period"))},
                "kt",
                "forecast movement for next period",
            ).to_dict()
        if wind := MAX_WIND_RE.search(text):
            fields["max_wind"] = Field(wind.group(0), int(wind.group("wind")), "kt", "maximum winds near centre").to_dict()
        wind_radii = self._wind_radii(text)
        if wind_radii:
            fields["wind_radii"] = wind_radii
        wave_radii = self._wave_radii(text)
        if wave_radii:
            fields["wave_radii"] = Field("wave radii", wave_radii, meaning="radius of waves by sector").to_dict()
        return {"identity": f"{name} / {number}", "raw": text, "fields": fields, "discussion": []}

    def _forecasts(self, text: str, system: dict[str, Any] | None) -> list[dict[str, Any]]:
        base_day = None
        fields = system.get("fields", {}) if system else {}
        analysis_time = fields.get("analysis_time", {}).get("value", "")
        if re.match(r"\d{6}UTC", str(analysis_time)):
            base_day = int(str(analysis_time)[:2])
        forecasts = []
        for block in FORECAST_BLOCK_RE.finditer(text):
            valid = block.group("time") + "UTC"
            body = block.group("body").strip()
            forecast: dict[str, Any] = {
                "valid_time": Field(valid, valid, meaning="forecast valid time").to_dict(),
                "raw": block.group(0),
            }
            lead = self._lead_hours(base_day, block.group("time"))
            if lead is not None:
                forecast["lead_time"] = Field(f"{lead}H", lead, "hour", "forecast lead time").to_dict()
            if "DISSIPATED" in body.upper():
                forecast["status"] = Field("DISSIPATED OVER LAND", "陸上消散", meaning="forecast status").to_dict()
                forecasts.append(forecast)
                continue
            coord = self._coord_from_text(body)
            if coord:
                forecast["position"] = Field(body, coord, "degree", "forecast position").to_dict()
            if wind := FORECAST_WIND_RE.search(body):
                forecast["max_wind"] = Field(wind.group(0), int(wind.group("wind")), "kt", "forecast maximum wind").to_dict()
            forecasts.append(forecast)
        return forecasts

    def _wind_radii(self, text: str) -> list[dict[str, Any]]:
        rows = []
        for match in WIND_RADIUS_RE.finditer(text):
            threshold = int(match.group("threshold"))
            first = int(match.group("first"))
            area = self._clean_area(match.group("area")) if match.group("area") else "ALL"
            rows.append(Field(match.group(0), {
                "threshold_kt": threshold,
                "radius_nm": first,
                "radius_km": round(first * 1.852),
                "quadrant": area,
            }, "nm", "wind radius").to_dict())
            if match.group("second"):
                second = int(match.group("second"))
                rows.append(Field(match.group(0), {
                    "threshold_kt": threshold,
                    "radius_nm": second,
                    "radius_km": round(second * 1.852),
                    "quadrant": "ELSEWHERE",
                }, "nm", "wind radius").to_dict())
        return rows

    def _wave_radii(self, text: str) -> list[dict[str, Any]]:
        rows = []
        for match in WAVE_RADIUS_RE.finditer(text):
            first = int(match.group("first"))
            rows.append({
                "height_m": int(match.group("height")),
                "radius_nm": first,
                "radius_km": round(first * 1.852),
                "area": self._clean_area(match.group("area")),
            })
            if match.group("second"):
                second = int(match.group("second"))
                rows.append({
                    "height_m": int(match.group("height")),
                    "radius_nm": second,
                    "radius_km": round(second * 1.852),
                    "area": "ELSEWHERE",
                })
        return rows

    def _coord_from_text(self, text: str) -> dict[str, float] | None:
        match = COORD_RE.search(text)
        if not match:
            return None
        lat = float(match.group("lat"))
        lon = float(match.group("lon"))
        if match.group("lat_h").upper() == "S":
            lat *= -1
        if match.group("lon_h").upper() == "W":
            lon *= -1
        return {"lat": lat, "lon": lon}

    def _lead_hours(self, base_day: int | None, valid: str) -> int | None:
        if base_day is None:
            return None
        day = int(valid[:2])
        hour = int(valid[2:4])
        return (day - base_day) * 24 + hour

    def _clean_area(self, text: str | None) -> str:
        return re.sub(r"\s+", " ", (text or "").strip().upper())

    def _classification_zh(self, text: str) -> str:
        return {
            "TYPHOON": "颱風",
            "TROPICAL STORM": "熱帶風暴",
            "SEVERE TROPICAL STORM": "強烈熱帶風暴",
            "TROPICAL DEPRESSION": "熱帶低壓",
        }.get(text.upper(), text)

    def _summary(self, heading: dict[str, Any] | None, system: dict[str, Any] | None, forecasts: list[dict[str, Any]]) -> str:
        issue = heading.get("issue_time", {}).get("raw", "") if heading else ""
        if not system:
            return f"香港天文台(VHHH)於 {issue}Z 發布熱帶氣旋警報。"
        fields = system.get("fields", {})
        parts = [f"香港天文台(VHHH)於 {issue}Z 發布熱帶氣旋警報。"]
        name = fields.get("name", {}).get("value")
        number = fields.get("storm_number", {}).get("value")
        classification = fields.get("classification", {}).get("value")
        if name:
            parts.append(f"系統：{classification} {name} ({number})。")
        if fields.get("position", {}).get("value"):
            pos = fields["position"]["value"]
            parts.append(f"目前中心位於 {pos['lat']}N、{pos['lon']}E。")
        if fields.get("pressure") or fields.get("max_wind"):
            parts.append(f"中心氣壓 {fields.get('pressure', {}).get('value')} hPa，近中心最大風 {fields.get('max_wind', {}).get('value')} kt。")
        if fields.get("movement"):
            movement = fields["movement"]["value"]
            parts.append(f"未來 {movement['period_hours']} 小時大致向 {movement['direction']} 移動，速度約 {movement['speed']} kt。")
        if forecasts:
            parts.append(f"預報位置共 {len(forecasts)} 筆，最後一筆為 {forecasts[-1].get('status', {}).get('value') or forecasts[-1].get('valid_time', {}).get('value')}。")
        return "\n".join(parts)
