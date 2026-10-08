from __future__ import annotations

import re
from typing import Any

from ..models import Field, ParseResult
from ..normalization import normalize_tac, parse_heading
from .base import BaseParser


ICAO_IDENTITY_RE = re.compile(
    r"^(?P<classification>HURRICANE|TYPHOON|TROPICAL STORM|TROPICAL DEPRESSION|"
    r"SUBTROPICAL STORM|POST-TROPICAL CYCLONE)\s+(?P<name>[A-Z0-9-]+)\s+"
    r"ICAO ADVISORY NUMBER\s+(?P<number>\d+)\s*$",
    re.I,
)
ICAO_CURRENT_POSITION_RE = re.compile(
    r"^OBS PSN:\s*(?P<time>\d{2}/\d{4}Z)\s+"
    r"(?P<lat>(?:[NS]\d{4}|\d{4}[NS]))\s+(?P<lon>(?:[EW]\d{5}|\d{5}[EW]))\s*$",
    re.I,
)
ICAO_FORECAST_POSITION_RE = re.compile(
    r"^FCST PSN\s+\+(?P<lead>\d{1,3})\s+HR:\s*(?P<time>\d{2}/\d{4}Z)\s+"
    r"(?P<lat>(?:[NS]\d{4}|\d{4}[NS]))\s+(?P<lon>(?:[EW]\d{5}|\d{5}[EW]))\s*$",
    re.I,
)
ICAO_FORECAST_WIND_RE = re.compile(
    r"^FCST MAX WIND\s+\+(?P<lead>\d{1,3})\s+HR:\s*(?P<wind>\d{1,3})KT\s*$",
    re.I,
)
ICAO_STORM_ID_RE = re.compile(r"\b(?P<identifier>[A-Z]{2}\d{6})\b", re.I)
ICAO_MOVEMENT_RE = re.compile(r"^(?P<direction>[A-Z-]+)\s+(?P<speed>\d{1,3})KT\s*$", re.I)
ICAO_LEAD_REMARK_RE = re.compile(r"^RMK:\s*(?P<text>.*)$", re.I)

TCMCP_IDENTITY_RE = re.compile(
    r"^(?P<classification>HURRICANE|TYPHOON|TROPICAL STORM|TROPICAL DEPRESSION|"
    r"SUBTROPICAL STORM|POST-TROPICAL CYCLONE)\s+(?P<name>[A-Z0-9-]+)\s+"
    r"FORECAST/ADVISORY NUMBER\s+(?P<number>\d+)\s*$",
    re.I,
)
TCMCP_CURRENT_POSITION_RE = re.compile(
    r"^(?:[A-Z-]+\s+)?CENTER LOCATED NEAR\s+"
    r"(?P<lat>\d{1,2}(?:\.\d+)?)(?P<lat_h>[NS])\s+"
    r"(?P<lon>\d{1,3}(?:\.\d+)?)(?P<lon_h>[EW])\s+AT\s+(?P<time>\d{2}/\d{4}Z)\s*$",
    re.I,
)
TCMCP_ACCURACY_RE = re.compile(r"^POSITION ACCURATE WITHIN\s+(?P<nm>\d+)\s+NM\s*$", re.I)
TCMCP_MOVEMENT_RE = re.compile(
    r"^PRESENT MOVEMENT TOWARD THE\s+(?P<direction>.+?)\s+OR\s+(?P<bearing>\d{1,3})\s+"
    r"DEGREES AT\s+(?P<speed>\d{1,3})\s+KT\s*$",
    re.I,
)
TCMCP_PRESSURE_RE = re.compile(r"^ESTIMATED MINIMUM CENTRAL PRESSURE\s+(?P<pressure>\d{3,4})\s+MB\s*$", re.I)
TCMCP_WIND_RE = re.compile(
    r"^MAX SUSTAINED WINDS\s+(?P<wind>\d{1,3})\s+KT WITH GUSTS TO\s+(?P<gust>\d{1,3})\s+KT\.?$",
    re.I,
)
TCMCP_FORECAST_RE = re.compile(
    r"^(?P<kind>FORECAST|OUTLOOK) VALID\s+(?P<time>\d{2}/\d{4}Z)"
    r"(?:\s+(?P<lat>\d{1,2}(?:\.\d+)?)(?P<lat_h>[NS])\s+"
    r"(?P<lon>\d{1,3}(?:\.\d+)?)(?P<lon_h>[EW]))?\s*(?P<tail>.*)$",
    re.I,
)
TCMCP_FORECAST_WIND_RE = re.compile(
    r"^MAX WIND\s+(?P<wind>\d{1,3})\s+KT(?:\s*\.{2,}\s*GUSTS\s+(?P<gust>\d{1,3})\s+KT)?\.?$",
    re.I,
)
TCMCP_RADIUS_RE = re.compile(
    r"^(?:(?P<threshold>\d{1,3})\s*KT|(?P<sea_height>\d{1,2})\s*M\s+SEAS)\s*\.{2,}\s*"
    r"(?P<ne>\d{1,4})\s*NE\s+(?P<se>\d{1,4})\s*SE\s+"
    r"(?P<sw>\d{1,4})\s*SW\s+(?P<nw>\d{1,4})\s*NW\.?$",
    re.I,
)
TCMCP_PREVIOUS_POSITION_RE = re.compile(
    r"^AT\s+(?P<time>\d{2}/\d{4}Z)\s+CENTER WAS LOCATED NEAR\s+"
    r"(?P<lat>\d{1,2}(?:\.\d+)?)(?P<lat_h>[NS])\s+"
    r"(?P<lon>\d{1,3}(?:\.\d+)?)(?P<lon_h>[EW])\s*$",
    re.I,
)
WMO_HEADING_LINE_RE = re.compile(r"^[A-Z]{4}\d{0,2}\s+[A-Z]{4}\s+\d{6}(?:\s+[A-Z]{3})?$", re.I)
PART_END_RE = re.compile(r"^//\s*END PART\s+(?P<part>\d{2})(?:/(?P<total>\d{2}))?\s*//\s*$", re.I)


def _signed_decimal(value: str, hemisphere: str) -> float:
    number = float(value)
    return -number if hemisphere.upper() in {"S", "W"} else number


def _compact_degrees_minutes(value: str) -> float:
    hemisphere = value[0].upper() if value[0].upper() in {"N", "S", "E", "W"} else value[-1].upper()
    digits = value[1:] if value[0].upper() in {"N", "S", "E", "W"} else value[:-1]
    degree_width = 2 if hemisphere in {"N", "S"} else 3
    degrees = int(digits[:degree_width])
    minutes = int(digits[degree_width:])
    if minutes >= 60:
        raise ValueError(f"Invalid degrees/minutes coordinate: {value}")
    result = degrees + minutes / 60
    limit = 90 if hemisphere in {"N", "S"} else 180
    if result > limit:
        raise ValueError(f"Coordinate is outside its valid range: {value}")
    return -result if hemisphere in {"S", "W"} else result


def _position_field(raw: str, latitude: float, longitude: float, meaning: str = "storm center position") -> dict[str, Any]:
    return Field(raw, {"lat": latitude, "lon": longitude}, "degree", meaning).to_dict()


def _classification_text(value: str) -> str:
    return {
        "HURRICANE": "颶風",
        "TYPHOON": "颱風",
        "TROPICAL STORM": "熱帶風暴",
        "TROPICAL DEPRESSION": "熱帶低氣壓",
        "SUBTROPICAL STORM": "副熱帶風暴",
        "POST-TROPICAL CYCLONE": "後熱帶氣旋",
    }.get(value.upper(), value.upper())


class PhfoIcaoAdvisoryParser(BaseParser):
    """PHFO TCAPA2 aviation tropical-cyclone advisory parser."""

    def supports(self, normalized: str) -> bool:
        heading = parse_heading(normalized)
        lines = {line.strip().upper() for line in normalize_tac(normalized).splitlines()}
        return bool(heading and heading.get("center") == "PHFO" and heading.get("ttaa") == "FKPA" and "TCAPA2" in lines)

    def parse(self, raw: str) -> dict[str, Any]:
        normalized = normalize_tac(raw)
        heading = parse_heading(normalized)
        result = ParseResult("phfo_icao_tropical_cyclone_advisory", raw, normalized, heading)
        result.fields["bulletin_type"] = Field("TCAPA2", "航空熱帶氣旋諮詢", meaning="NWS Aviation Tropical Cyclone Advisory").to_dict()
        result.fields["source_profile"] = {
            "value": "PHFO/CPHC",
            "meaning": "NWS Central Pacific Hurricane Center aviation advisory format",
            "confidence": "high",
        }
        system: dict[str, Any] = {"identity": "UNKNOWN", "raw": normalized, "fields": {}}
        forecasts: dict[int, dict[str, Any]] = {}
        in_remarks = False

        for line in normalized.splitlines():
            text = line.strip()
            upper = text.upper()
            if not text or (heading and text == heading["raw"]) or upper in {"TCAPA2", "TC ADVISORY", "$$"}:
                continue
            if match := ICAO_IDENTITY_RE.match(text):
                classification = match.group("classification").upper()
                name = match.group("name").upper()
                advisory_number = int(match.group("number"))
                system["identity"] = f"{name} / ADVISORY {advisory_number}"
                system["fields"].update({
                    "name": Field(name, name, meaning="tropical cyclone name").to_dict(),
                    "classification": Field(classification, _classification_text(classification), meaning="current classification").to_dict(),
                    "advisory_number": Field(str(advisory_number), advisory_number, meaning="ICAO advisory number").to_dict(),
                })
                continue
            storm_id = ICAO_STORM_ID_RE.search(text)
            if storm_id and "NWS" in upper:
                identifier = storm_id.group("identifier").upper()
                system["fields"]["storm_identifier"] = Field(identifier, identifier, meaning="basin and storm identifier").to_dict()
                if system["identity"] != "UNKNOWN":
                    system["identity"] = f"{system['fields']['name']['value']} / {identifier}"
                continue
            if match := ICAO_CURRENT_POSITION_RE.match(text):
                try:
                    position = _position_field(
                        f"{match.group('lat')} {match.group('lon')}",
                        _compact_degrees_minutes(match.group("lat")),
                        _compact_degrees_minutes(match.group("lon")),
                    )
                except ValueError as exc:
                    result.warnings.append(str(exc))
                    continue
                system["fields"]["position"] = position
                system["fields"]["analysis_time"] = Field(match.group("time"), match.group("time"), meaning="observation valid time in UTC").to_dict()
                continue
            if match := ICAO_FORECAST_POSITION_RE.match(text):
                lead = int(match.group("lead"))
                try:
                    position = _position_field(
                        f"{match.group('lat')} {match.group('lon')}",
                        _compact_degrees_minutes(match.group("lat")),
                        _compact_degrees_minutes(match.group("lon")),
                        "forecast storm center position",
                    )
                except ValueError as exc:
                    result.warnings.append(str(exc))
                    continue
                forecasts[lead] = {
                    "tau": f"+{lead}h",
                    "hour": lead,
                    "valid_time": Field(match.group("time"), match.group("time"), meaning="forecast valid time in UTC").to_dict(),
                    "position": position,
                    "raw": text,
                }
                continue
            if match := ICAO_FORECAST_WIND_RE.match(text):
                lead = int(match.group("lead"))
                forecast = forecasts.setdefault(lead, {"tau": f"+{lead}h", "hour": lead})
                wind = int(match.group("wind"))
                forecast["max_wind"] = Field(match.group("wind") + "KT", wind, "kt", "forecast maximum sustained wind").to_dict()
                forecast["raw_max_wind"] = text
                continue
            if text.upper().startswith("DTG:"):
                result.fields["advisory_time"] = Field(text.partition(":")[2].strip(), text.partition(":")[2].strip(), meaning="advisory issue time in UTC").to_dict()
                continue
            if text.upper().startswith("TCAC:"):
                value = text.partition(":")[2].strip().upper()
                result.fields["tropical_cyclone_advisory_center"] = Field(value, value, meaning="tropical cyclone advisory center").to_dict()
                continue
            if text.upper().startswith("TC:"):
                value = text.partition(":")[2].strip().upper()
                system["fields"]["name"] = Field(value, value, meaning="tropical cyclone name").to_dict()
                if system["identity"] == "UNKNOWN":
                    system["identity"] = value
                continue
            if text.upper().startswith("ADVISORY NR:"):
                value = text.partition(":")[2].strip()
                result.fields["advisory_number"] = Field(value, value, meaning="advisory sequence number").to_dict()
                continue
            if text.upper().startswith("MOV:"):
                value = text.partition(":")[2].strip()
                movement = ICAO_MOVEMENT_RE.match(value)
                if movement:
                    system["fields"]["movement"] = Field(
                        value,
                        {"direction": movement.group("direction").upper(), "speed": int(movement.group("speed"))},
                        "kt",
                        "current storm movement",
                    ).to_dict()
                else:
                    system["fields"]["movement"] = Field(value, value, meaning="current storm movement").to_dict()
                continue
            if text.upper().startswith("INTST CHANGE:"):
                value = text.partition(":")[2].strip().upper()
                meaning = {"NC": "no change", "WKN": "weakening", "INTSF": "intensifying"}.get(value, "intensity-change code")
                system["fields"]["intensity_change"] = Field(value, value, meaning=meaning).to_dict()
                continue
            if match := re.match(r"^C:\s*(?P<pressure>\d{3,4})HPA\s*$", text, re.I):
                pressure = int(match.group("pressure"))
                system["fields"]["pressure"] = Field(text, pressure, "hPa", "minimum central pressure").to_dict()
                continue
            if match := re.match(r"^MAX WIND:\s*(?P<wind>\d{1,3})KT\s*$", text, re.I):
                wind = int(match.group("wind"))
                system["fields"]["max_wind"] = Field(text, wind, "kt", "maximum sustained wind").to_dict()
                continue
            if match := ICAO_LEAD_REMARK_RE.match(text):
                in_remarks = True
                result.remarks.append(match.group("text"))
                continue
            if text.upper().startswith("NXT MSG:"):
                in_remarks = False
                value = text.partition(":")[2].strip()
                result.fields["next_message"] = Field(value, value, meaning="next advisory schedule").to_dict()
                continue
            if in_remarks:
                result.remarks.append(text)
            elif not text.upper().startswith(("NWS ", "ISSUED BY ", "\u00a7")) and not re.match(r"^\d{4} UTC ", text, re.I):
                result.remarks.append(text)

        result.systems = [system] if system["fields"] else []
        result.forecasts = [forecasts[lead] for lead in sorted(forecasts)]
        if not system["fields"].get("position"):
            result.warnings.append("No OBS PSN position was found.")
        if not result.forecasts:
            result.warnings.append("No FCST PSN forecast positions were found.")
        result.fields["human_summary"] = self._summary(result, system)
        return result.to_dict()

    def _summary(self, result: ParseResult, system: dict[str, Any]) -> str:
        fields = system["fields"]
        issue_time = (result.heading or {}).get("issue_time", {}).get("raw", "")
        lines = [f"PHFO 於 {issue_time}Z 發布 TCAPA2 航空熱帶氣旋諮詢。"]
        if system["identity"] != "UNKNOWN":
            lines.append(f"氣旋：{system['identity']}。")
        if position := fields.get("position", {}).get("value"):
            lines.append(f"觀測位置：{position['lat']:.2f}, {position['lon']:.2f}；風速 {fields.get('max_wind', {}).get('value', '-')} kt。")
        lines.append(f"解析到 {len(result.forecasts)} 個預報位置。")
        return "\n".join(lines)


class PhfoTcmcpAdvisoryParser(BaseParser):
    """PHFO TCMCP2 marine/aviation forecast-advisory parser."""

    def supports(self, normalized: str) -> bool:
        heading = parse_heading(normalized)
        lines = {line.strip().upper() for line in normalize_tac(normalized).splitlines()}
        return bool(heading and heading.get("center") == "PHFO" and heading.get("ttaa") == "WTPA" and "TCMCP2" in lines)

    def parse(self, raw: str) -> dict[str, Any]:
        normalized = normalize_tac(raw)
        heading = parse_heading(normalized)
        result = ParseResult("phfo_tcmcp_advisory", raw, normalized, heading)
        result.fields["bulletin_type"] = Field("TCMCP2", "海洋/航空熱帶氣旋預報諮詢", meaning="NWS Marine/Aviation Tropical Cyclone Advisory").to_dict()
        result.fields["source_profile"] = {
            "value": "PHFO/CPHC",
            "meaning": "NWS Central Pacific Hurricane Center forecast/advisory format",
            "confidence": "high",
        }
        system: dict[str, Any] = {"identity": "UNKNOWN", "raw": normalized, "fields": {}}
        forecasts: list[dict[str, Any]] = []
        current_forecast: dict[str, Any] | None = None
        received_parts: set[int] = set()
        expected_parts: int | None = None
        missing_continuation_rows = 0

        for line in normalized.splitlines():
            text = line.strip().rstrip("=").strip()
            upper = text.upper()
            if not text or (heading and text == heading["raw"]):
                continue
            if PART_END_RE.match(text):
                part = PART_END_RE.match(text)
                received_parts.add(int(part.group("part")))
                if part.group("total"):
                    expected_parts = int(part.group("total"))
                continue
            if WMO_HEADING_LINE_RE.match(text) or upper == "TCMCP2" or upper == "$$":
                continue
            if match := TCMCP_IDENTITY_RE.match(text):
                classification = match.group("classification").upper()
                name = match.group("name").upper()
                advisory_number = int(match.group("number"))
                system["identity"] = f"{name} / ADVISORY {advisory_number}"
                system["fields"].update({
                    "name": Field(name, name, meaning="tropical cyclone name").to_dict(),
                    "classification": Field(classification, _classification_text(classification), meaning="current classification").to_dict(),
                    "advisory_number": Field(str(advisory_number), advisory_number, meaning="forecast/advisory number").to_dict(),
                })
                continue
            storm_id = ICAO_STORM_ID_RE.search(text)
            if storm_id and "NWS" in upper:
                identifier = storm_id.group("identifier").upper()
                system["fields"]["storm_identifier"] = Field(identifier, identifier, meaning="basin and storm identifier").to_dict()
                if system["identity"] != "UNKNOWN":
                    system["identity"] = f"{system['fields']['name']['value']} / {identifier}"
                continue
            if match := TCMCP_CURRENT_POSITION_RE.match(text):
                position = _position_field(
                    f"{match.group('lat')}{match.group('lat_h')} {match.group('lon')}{match.group('lon_h')}",
                    _signed_decimal(match.group("lat"), match.group("lat_h")),
                    _signed_decimal(match.group("lon"), match.group("lon_h")),
                )
                system["fields"]["position"] = position
                system["fields"]["analysis_time"] = Field(match.group("time"), match.group("time"), meaning="analysis valid time in UTC").to_dict()
                continue
            if match := TCMCP_ACCURACY_RE.match(text):
                system["fields"]["position_accuracy"] = Field(text, int(match.group("nm")), "nm", "position accuracy radius").to_dict()
                continue
            if match := TCMCP_MOVEMENT_RE.match(text):
                system["fields"]["movement"] = Field(
                    text,
                    {"direction": match.group("direction").upper(), "bearing": int(match.group("bearing")), "speed": int(match.group("speed"))},
                    "kt",
                    "present storm movement",
                ).to_dict()
                continue
            if match := TCMCP_PRESSURE_RE.match(text):
                system["fields"]["pressure"] = Field(text, int(match.group("pressure")), "mb", "estimated minimum central pressure").to_dict()
                continue
            if match := TCMCP_WIND_RE.match(text):
                system["fields"]["max_wind"] = Field(text, int(match.group("wind")), "kt", "maximum sustained wind").to_dict()
                system["fields"]["gust"] = Field(text, int(match.group("gust")), "kt", "maximum gust").to_dict()
                continue
            if match := TCMCP_PREVIOUS_POSITION_RE.match(text):
                system["fields"]["previous_position"] = {
                    "valid_time": Field(match.group("time"), match.group("time"), meaning="previous position time in UTC").to_dict(),
                    "position": _position_field(
                        f"{match.group('lat')}{match.group('lat_h')} {match.group('lon')}{match.group('lon_h')}",
                        _signed_decimal(match.group("lat"), match.group("lat_h")),
                        _signed_decimal(match.group("lon"), match.group("lon_h")),
                        "previous storm center position",
                    ),
                }
                continue
            if match := TCMCP_FORECAST_RE.match(text):
                kind = match.group("kind").upper()
                current_forecast = {
                    "kind": kind.lower(),
                    "valid_time": Field(match.group("time"), match.group("time"), meaning="forecast valid time in UTC" if kind == "FORECAST" else "extended outlook valid time in UTC").to_dict(),
                    "raw": text,
                    "wind_radii": [],
                    "sea_radii": [],
                }
                if match.group("lat") and match.group("lon"):
                    current_forecast["position"] = _position_field(
                        f"{match.group('lat')}{match.group('lat_h')} {match.group('lon')}{match.group('lon_h')}",
                        _signed_decimal(match.group("lat"), match.group("lat_h")),
                        _signed_decimal(match.group("lon"), match.group("lon_h")),
                        "forecast storm center position",
                    )
                tail = match.group("tail").strip().lstrip(".").strip()
                if tail:
                    current_forecast["status"] = Field(tail, tail, meaning="forecast status").to_dict()
                forecasts.append(current_forecast)
                continue
            if match := TCMCP_FORECAST_WIND_RE.match(text):
                if current_forecast is None:
                    result.remarks.append(text)
                    continue
                current_forecast["max_wind"] = Field(match.group("wind") + " kt", int(match.group("wind")), "kt", "forecast maximum sustained wind").to_dict()
                if match.group("gust"):
                    current_forecast["gust"] = Field(match.group("gust") + " kt", int(match.group("gust")), "kt", "forecast maximum gust").to_dict()
                continue
            if match := TCMCP_RADIUS_RE.match(text):
                if current_forecast is None:
                    if system["fields"].get("position") and not forecasts:
                        target = system["fields"]
                    else:
                        missing_continuation_rows += 1
                        result.remarks.append(text)
                        continue
                else:
                    target = current_forecast
                radii_key = "sea_radii" if match.group("sea_height") else "wind_radii"
                rows = target.setdefault(radii_key, [])
                for quadrant in ("NE", "SE", "SW", "NW"):
                    radius: dict[str, Any] = {
                        "quadrant": quadrant,
                        "radius_nm": int(match.group(quadrant.lower())),
                    }
                    if match.group("threshold"):
                        radius["threshold_kt"] = int(match.group("threshold"))
                    else:
                        radius["sea_height_m"] = int(match.group("sea_height"))
                    rows.append(radius)
                continue
            if upper.startswith(("FORECAST VALID", "OUTLOOK VALID")):
                result.remarks.append(text)
                continue
            result.remarks.append(text)

        result.systems = [system] if system["fields"] else []
        result.forecasts = forecasts
        if received_parts:
            result.fields["message_parts"] = Field(
                ",".join(f"{part:02d}" for part in sorted(received_parts)),
                sorted(received_parts),
                meaning="multipart bulletin sections received",
            ).to_dict()
            complete_parts = {1, 2}.issubset(received_parts)
            if not complete_parts:
                part_text = ", ".join(f"{part:02d}" for part in sorted(received_parts))
                total_text = f" of {expected_parts:02d}" if expected_parts else ""
                result.warnings.append(
                    f"TCMCP2 is multipart; received part(s) {part_text}{total_text}. Combine all parts for complete forecast groups."
                )
        if missing_continuation_rows:
            result.warnings.append(
                f"{missing_continuation_rows} wind/sea-radius continuation row(s) had no preceding forecast header in this part."
            )
        if not system["fields"].get("position"):
            result.warnings.append("No current center position was found.")
        if not forecasts:
            result.warnings.append("No forecast/outlook positions were found.")
        result.fields["human_summary"] = self._summary(result, system)
        return result.to_dict()

    def _summary(self, result: ParseResult, system: dict[str, Any]) -> str:
        issue_time = (result.heading or {}).get("issue_time", {}).get("raw", "")
        fields = system["fields"]
        lines = [f"PHFO 於 {issue_time}Z 發布 TCMCP2 熱帶氣旋預報諮詢。"]
        if system["identity"] != "UNKNOWN":
            lines.append(f"氣旋：{system['identity']}。")
        if position := fields.get("position", {}).get("value"):
            lines.append(
                f"目前中心 {abs(position['lat']):g}{'N' if position['lat'] >= 0 else 'S'}、"
                f"{abs(position['lon']):g}{'E' if position['lon'] >= 0 else 'W'}；"
                f"最大風速 {fields.get('max_wind', {}).get('value', '-')} kt。"
            )
        lines.append(f"解析到 {len(result.forecasts)} 個預報/展望時效。")
        return "\n".join(lines)
