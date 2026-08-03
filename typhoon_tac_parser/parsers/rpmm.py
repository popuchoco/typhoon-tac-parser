from __future__ import annotations

import re
from typing import Any

from ..models import Field, ParseResult
from ..normalization import normalize_tac, parse_heading
from .base import BaseParser
from .tropical import signed_coord


COORD_RE = re.compile(r"(?P<lat>\d{1,2}(?:\.\d+)?)(?P<lat_h>[NS])\s+(?P<lon>\d{1,3}(?:\.\d+)?)(?P<lon_h>[EW])")
ISSUED_RE = re.compile(r"ISSUED\s+AT\s+(?P<time>\d{4})UTC,\s*(?P<date>\d{1,2}\s+[A-Z]+\s+\d{4})", re.I)
WARNING_NR_RE = re.compile(r"WARNING\s+FOR\s+SHIPPING\s+NR\.\s*(?P<number>\d+)", re.I)
CLASS_PRESSURE_RE = re.compile(r"^(?P<classification>TROPICAL\s+DEPRESSION|TROPICAL\s+STORM|SEVERE\s+TROPICAL\s+STORM|TYPHOON|LOW)\s*(?P<pressure>\d{3,4})?H?PA?", re.I)
CURRENT_RE = re.compile(
    r"AT\s+(?P<time>\d{4})UTC,\s+PSTN\s+(?P<coord>\d{1,2}(?:\.\d+)?[NS]\s+\d{1,3}(?:\.\d+)?[EW])\s+MOV\s+(?P<direction>[A-Z]+)\s+(?P<speed>\d+)\s*KT",
    re.I,
)
MAX_WIND_RE = re.compile(r"MXWD\s+(?P<wind>\d+)\s*KT\s+NEAR\s+CTR", re.I)
FORECAST_HEADER_RE = re.compile(r"(?P<hour>\d+)-HOUR\s+FCST\s+VLD\s+AT\s+(?P<valid>\d{6})UTC", re.I)
FORECAST_DETAIL_RE = re.compile(
    r"PSTN\s+(?P<coord>\d{1,2}(?:\.\d+)?[NS]\s+\d{1,3}(?:\.\d+)?[EW]),?\s+PRES\s+(?P<pressure>\d{3,4})HPA,\s+(?:(?:MWXD|MXWD|MWD)\s+(?P<wind>\d+)KT|(?P<status>LOW|TROPICAL\s+DEPRESSION|TROPICAL\s+STORM|TYPHOON))",
    re.I,
)
NEXT_WARNING_RE = re.compile(r"NEXT\s+WARNING\s+(?P<time>\d{6})UTC", re.I)
VESSEL_RE = re.compile(r"ALL\s+VESSELS\s+WITHIN\s+(?P<radius>\d+)\s+NM\s+OF\s+(?P<coord>\d{1,2}(?:\.\d+)?[NS]\s+\d{1,3}(?:\.\d+)?[EW])", re.I)


class RpmmShippingWarningParser(BaseParser):
    """PAGASA/RPMM tropical cyclone warning for shipping parser."""

    def supports(self, normalized: str) -> bool:
        heading = parse_heading(normalized)
        if not heading or heading.get("center") != "RPMM":
            return False
        return "TROPICAL CYCLONE WARNING FOR SHIPPING" in normalized.upper()

    def parse(self, raw: str) -> dict[str, Any]:
        normalized = normalize_tac(raw).rstrip("=")
        heading = parse_heading(normalized)
        result = ParseResult(family="tropical_cyclone", raw=raw, normalized=normalized, heading=heading)
        lines = [line.strip() for line in normalized.splitlines() if line.strip()]

        fields: dict[str, Any] = {}
        system_fields: dict[str, Any] = {}
        classification = ""
        warning_number = ""
        issued = ""

        for line in lines:
            if match := WARNING_NR_RE.search(line):
                warning_number = match.group("number")
                fields["warning_number"] = Field(match.group(0), int(warning_number), meaning="shipping warning number").to_dict()
            if match := ISSUED_RE.search(line):
                issued = f"{match.group('date')} {match.group('time')}UTC"
                fields["issued_at"] = Field(match.group(0), issued, meaning="bulletin issue time").to_dict()
            if match := CLASS_PRESSURE_RE.search(line):
                classification = match.group("classification").upper()
                system_fields["classification"] = Field(match.group("classification"), self._classification_zh(classification), meaning="current cyclone classification").to_dict()
                if match.group("pressure"):
                    system_fields["pressure"] = Field(match.group("pressure") + "HPA", int(match.group("pressure")), "hpa", "current central pressure").to_dict()
            if match := CURRENT_RE.search(line):
                system_fields["analysis_time"] = Field(match.group("time") + "UTC", match.group("time") + "UTC", meaning="current analysis time").to_dict()
                system_fields["position"] = self._position_field(match.group("coord"))
                system_fields["movement"] = Field(
                    match.group(0),
                    {"direction": match.group("direction").upper(), "speed": int(match.group("speed"))},
                    "kt",
                    "current movement",
                ).to_dict()
            if match := MAX_WIND_RE.search(line):
                system_fields["max_wind"] = Field(match.group(0), int(match.group("wind")), "kt", "current maximum sustained wind near center").to_dict()
            if match := NEXT_WARNING_RE.search(line):
                fields["next_warning"] = Field(match.group(0), match.group("time") + "UTC", meaning="next warning time").to_dict()
            if match := VESSEL_RE.search(line):
                fields["vessel_report_request"] = Field(
                    match.group(0),
                    {"radius_nm": int(match.group("radius")), "position": self._position(match.group("coord"))},
                    meaning="vessel weather report request area",
                ).to_dict()

        result.fields.update(fields)
        result.forecasts = self._forecasts(lines)
        identity = classification or "TROPICAL CYCLONE"
        result.systems.append({
            "identity": self._classification_zh(identity),
            "raw": normalized,
            "fields": system_fields,
            "discussion": self._discussion(fields, system_fields, result.forecasts, warning_number, issued),
        })
        return result.to_dict()

    def _forecasts(self, lines: list[str]) -> list[dict[str, Any]]:
        forecasts = []
        pending: re.Match[str] | None = None
        for line in lines:
            if match := FORECAST_HEADER_RE.search(line):
                pending = match
                continue
            if pending and (detail := FORECAST_DETAIL_RE.search(line)):
                forecast = {
                    "lead_time": Field(pending.group(0), int(pending.group("hour")), "hour", "forecast lead time").to_dict(),
                    "valid_time": Field(pending.group("valid") + "UTC", pending.group("valid") + "UTC", meaning="forecast valid time").to_dict(),
                    "position": self._position_field(detail.group("coord")),
                    "pressure": Field(detail.group("pressure") + "HPA", int(detail.group("pressure")), "hpa", "forecast central pressure").to_dict(),
                    "raw": f"{pending.group(0)} {line}",
                }
                if detail.group("wind"):
                    forecast["max_wind"] = Field(detail.group("wind") + "KT", int(detail.group("wind")), "kt", "forecast maximum sustained wind").to_dict()
                if detail.group("status"):
                    forecast["status"] = Field(detail.group("status"), self._classification_zh(detail.group("status").upper()), meaning="forecast status").to_dict()
                forecasts.append(forecast)
                pending = None
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

    def _classification_zh(self, value: str) -> str:
        mapping = {
            "TROPICAL DEPRESSION": "熱帶低壓",
            "TROPICAL STORM": "熱帶風暴",
            "SEVERE TROPICAL STORM": "強烈熱帶風暴",
            "TYPHOON": "颱風",
            "LOW": "低壓",
        }
        return mapping.get(value.upper(), value)

    def _discussion(self, fields: dict[str, Any], system_fields: dict[str, Any], forecasts: list[dict[str, Any]], warning_number: str, issued: str) -> list[str]:
        parts = []
        if warning_number:
            parts.append(f"PAGASA 發布第 {warning_number} 號船舶熱帶氣旋警報。")
        if issued:
            parts.append(f"發報時間：{issued}。")
        if system_fields.get("classification"):
            parts.append(f"目前分類：{system_fields['classification']['value']}。")
        if system_fields.get("position"):
            pos = system_fields["position"]["value"]
            parts.append(f"目前中心位於 {pos['lat']:.1f}N、{pos['lon']:.1f}E。")
        if system_fields.get("movement"):
            mov = system_fields["movement"]["value"]
            parts.append(f"移動方向 {mov['direction']}，速度 {mov['speed']} kt。")
        if system_fields.get("pressure") or system_fields.get("max_wind"):
            pressure = system_fields.get("pressure", {}).get("value")
            wind = system_fields.get("max_wind", {}).get("value")
            parts.append(f"中心氣壓 {pressure} hPa，近中心最大風 {wind} kt。")
        if forecasts:
            last = forecasts[-1]
            if last.get("status"):
                parts.append(f"{last['lead_time']['value']} 小時預報時系統狀態為 {last['status']['value']}。")
        if fields.get("next_warning"):
            parts.append(f"下一報預計 {fields['next_warning']['value']} 發布。")
        return parts
