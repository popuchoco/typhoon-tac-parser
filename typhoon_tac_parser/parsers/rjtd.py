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
GUIDANCE_NAME_RE = re.compile(
    r"^NAME\s+(?P<classification>TY|TS|TD|STY|TYPHOON|TROPICAL\s+STORM|TROPICAL\s+DEPRESSION)\s+"
    r"(?P<number>\d{4})\s+(?P<name>[A-Z0-9-]+)(?:\s+\((?P<international>\d{4})\))?\s*$",
    re.I,
)
GUIDANCE_POSITION_RE = re.compile(
    r"^PSTN\s+(?P<time>\d{6})UTC\s+(?P<lat>\d{1,2}(?:\.\d+)?)(?P<lat_h>[NS])\s+"
    r"(?P<lon>\d{1,3}(?:\.\d+)?)(?P<lon_h>[EW])\s*$",
    re.I,
)
GUIDANCE_PRESSURE_RE = re.compile(r"^PRES\s+(?P<pressure>\d{3,4})HPA\s*$", re.I)
GUIDANCE_WIND_RE = re.compile(r"^MXWD\s+(?P<wind>\d{1,3})KT\s*$", re.I)
GUIDANCE_MODEL_RE = re.compile(r"^FORECAST BY\s+(?P<model>.+?)\s*$", re.I)
GUIDANCE_FORECAST_RE = re.compile(
    r"^T\s*=\s*(?P<lead>\d{3})\s+"
    r"(?P<lat>\d{1,2}(?:\.\d+)?)(?P<lat_h>[NS])\s+"
    r"(?P<lon>\d{1,3}(?:\.\d+)?)(?P<lon_h>[EW])\s+"
    r"(?P<pressure_change>[+-]?\d{3})HPA\s+(?P<wind_change>[+-]\d{3})KT\s*$",
    re.I,
)


def _signed_coordinate(value: str, hemisphere: str) -> float:
    number = float(value)
    return -number if hemisphere.upper() in {"S", "W"} else number


class RjtdGuidanceParser(BaseParser):
    """RJTD FXPQ deterministic/ensemble tropical-cyclone guidance parser."""

    def supports(self, normalized: str) -> bool:
        heading = parse_heading(normalized)
        text = normalize_tac(normalized).upper()
        return bool(
            heading
            and heading.get("center") == "RJTD"
            and heading.get("ttaa") == "FXPQ"
            and "RSMC GUIDANCE FOR FORECAST" in text
        )

    def parse(self, raw: str) -> dict[str, Any]:
        normalized = normalize_tac(raw)
        heading = parse_heading(normalized)
        result = ParseResult(
            family="rjtd_tropical_cyclone_guidance",
            raw=raw,
            normalized=normalized,
            heading=heading,
        )
        result.fields["source_profile"] = {
            "value": "RJTD/RSMC Tokyo",
            "meaning": "Japan Meteorological Agency RSMC tropical-cyclone guidance",
            "confidence": "high",
        }
        result.fields["guidance_type"] = Field(
            "RSMC GUIDANCE FOR FORECAST",
            "熱帶氣旋預報指引",
            meaning="RSMC tropical-cyclone forecast guidance",
        ).to_dict()

        system: dict[str, Any] = {"identity": "UNKNOWN", "raw": normalized, "fields": {}}
        initial_pressure: int | None = None
        initial_wind: int | None = None
        forecast_model: str | None = None
        for line in normalized.splitlines():
            stripped = line.strip().strip("`").strip()
            if not stripped or (heading and stripped == heading["raw"]):
                continue
            upper = stripped.upper()
            if upper in {
                "RSMC GUIDANCE FOR FORECAST",
                "TIME PSTN PRES MXWD",
                "(CHANGE FROM T=0)",
            }:
                continue
            if match := GUIDANCE_NAME_RE.match(stripped):
                classification = match.group("classification").upper()
                name = match.group("name").upper()
                number = match.group("number")
                system["identity"] = f"{name} / {number}"
                system["fields"].update({
                    "name": Field(name, name, meaning="storm name").to_dict(),
                    "storm_number": Field(number, number, meaning="tropical cyclone number").to_dict(),
                    "classification": Field(classification, self._classification_text(classification), meaning="current classification").to_dict(),
                })
                international = match.group("international")
                if international:
                    system["fields"]["international_number"] = Field(
                        international, international, meaning="international cyclone number"
                    ).to_dict()
                continue
            if match := GUIDANCE_POSITION_RE.match(stripped):
                position = self._position_field(match)
                system["fields"].update({
                    "position": position,
                    "analysis_time": Field(match.group("time") + "UTC", match.group("time") + "UTC", meaning="analysis time").to_dict(),
                })
                continue
            if match := GUIDANCE_PRESSURE_RE.match(stripped):
                initial_pressure = int(match.group("pressure"))
                system["fields"]["pressure"] = Field(stripped, initial_pressure, "hPa", "initial central pressure").to_dict()
                continue
            if match := GUIDANCE_WIND_RE.match(stripped):
                initial_wind = int(match.group("wind"))
                system["fields"]["max_wind"] = Field(stripped, initial_wind, "kt", "initial maximum sustained wind").to_dict()
                continue
            if match := GUIDANCE_MODEL_RE.match(stripped):
                forecast_model = match.group("model").upper()
                result.fields["forecast_model"] = Field(
                    stripped,
                    forecast_model,
                    meaning="forecast model producing this guidance",
                ).to_dict()
                continue
            if forecast_match := GUIDANCE_FORECAST_RE.match(stripped):
                result.forecasts.append(self._forecast(forecast_match, stripped, initial_pressure, initial_wind))
                continue
            if upper.startswith("TIME "):
                continue
            result.remarks.append(stripped)

        if system["identity"] == "UNKNOWN":
            result.warnings.append("No tropical cyclone identity was found in the NAME group.")
        if not result.forecasts:
            result.warnings.append("No T= forecast guidance rows were found.")
        if system["fields"]:
            result.systems.append(system)
        result.fields["change_reference"] = Field(
            "CHANGE FROM T=0",
            0,
            "hour",
            "forecast pressure and wind values are changes from the initial analysis",
        ).to_dict()
        result.fields["human_summary"] = self._summary(result, system, forecast_model)
        return result.to_dict()

    def _position_field(self, match: re.Match[str]) -> dict[str, Any]:
        return Field(
            f"{match.group('lat')}{match.group('lat_h')} {match.group('lon')}{match.group('lon_h')}",
            {
                "lat": _signed_coordinate(match.group("lat"), match.group("lat_h")),
                "lon": _signed_coordinate(match.group("lon"), match.group("lon_h")),
            },
            "degree",
            "storm center position",
        ).to_dict()

    def _forecast(
        self,
        match: re.Match[str],
        raw: str,
        initial_pressure: int | None,
        initial_wind: int | None,
    ) -> dict[str, Any]:
        lead = int(match.group("lead"))
        pressure_change = int(match.group("pressure_change"))
        wind_change = int(match.group("wind_change"))
        pressure_delta = Field(
            match.group("pressure_change") + "HPA",
            pressure_change,
            "hPa",
            "pressure change from initial analysis",
        ).to_dict()
        wind_delta = Field(
            match.group("wind_change") + "KT",
            wind_change,
            "kt",
            "maximum-wind change from initial analysis",
        ).to_dict()
        forecast: dict[str, Any] = {
            "tau": f"T={lead:03d}",
            "hour": lead,
            "valid_time": Field(f"T+{lead:03d}h", f"T+{lead:03d}h", meaning="forecast lead from analysis time").to_dict(),
            "position": Field(
                f"{match.group('lat')}{match.group('lat_h')} {match.group('lon')}{match.group('lon_h')}",
                {
                    "lat": _signed_coordinate(match.group("lat"), match.group("lat_h")),
                    "lon": _signed_coordinate(match.group("lon"), match.group("lon_h")),
                },
                "degree",
                "forecast storm center position",
            ).to_dict(),
            "pressure_change_from_initial": pressure_delta,
            "max_wind_change_from_initial": wind_delta,
            "raw": raw,
        }
        if initial_pressure is not None:
            forecast["pressure"] = Field(
                f"{initial_pressure + pressure_change} hPa",
                initial_pressure + pressure_change,
                "hPa",
                "guidance pressure derived from initial pressure plus reported change",
                "medium",
            ).to_dict()
        if initial_wind is not None:
            forecast["max_wind"] = Field(
                f"{initial_wind + wind_change} kt",
                initial_wind + wind_change,
                "kt",
                "guidance maximum wind derived from initial wind plus reported change",
                "medium",
            ).to_dict()
        return forecast

    def _classification_text(self, value: str) -> str:
        return {
            "TY": "TYPHOON",
            "TS": "TROPICAL STORM",
            "TD": "TROPICAL DEPRESSION",
            "STY": "SUPER TYPHOON",
        }.get(value.upper(), value.upper())

    def _summary(self, result: ParseResult, system: dict[str, Any], model: str | None) -> str:
        issue = (result.heading or {}).get("issue_time", {}).get("raw", "")
        fields = system["fields"]
        position = fields.get("position", {}).get("value")
        lines = [f"日本氣象廳 RSMC 於 {issue}Z 發布熱帶氣旋預報指引。"]
        if system["identity"] != "UNKNOWN":
            lines.append(f"分析對象：{system['identity']}。")
        if position:
            lat_hemisphere = "N" if position["lat"] >= 0 else "S"
            lon_hemisphere = "E" if position["lon"] >= 0 else "W"
            lines.append(
                f"初始位置：{abs(position['lat']):g}{lat_hemisphere}、"
                f"{abs(position['lon']):g}{lon_hemisphere}。"
            )
        if "pressure" in fields or "max_wind" in fields:
            lines.append(
                f"初始氣壓 {fields.get('pressure', {}).get('value', '-')} hPa，"
                f"最大風速 {fields.get('max_wind', {}).get('value', '-')} kt。"
            )
        if model:
            lines.append(f"預報模式：{model}；共有 {len(result.forecasts)} 筆時效資料。")
        return "\n".join(lines)


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
