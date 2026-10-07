from __future__ import annotations

import re
from typing import Any

from ..models import Field, ParseResult
from ..normalization import normalize_tac, parse_heading
from .base import BaseParser


STORM_RE = re.compile(
    r"(?:SUBJ/)?(?P<classification>TYPHOON|TROPICAL STORM|TROPICAL DEPRESSION|SUBTROPICAL STORM)\s+"
    r"(?P<number>\d{2}[A-Z])\s+\((?P<name>[^)]+)\)",
    re.I,
)
FORECAST_HEADER_RE = re.compile(r"^(?P<lead>\d{1,3})\s+HRS,\s+VALID\s+AT:\s*$", re.I)
POSITION_RE = re.compile(
    r"^(?P<time>\d{6})Z\s+---\s+(?:NEAR\s+)?"
    r"(?P<lat>\d{1,2}(?:\.\d+)?)(?P<lat_h>[NS])\s+"
    r"(?P<lon>\d{1,3}(?:\.\d+)?)(?P<lon_h>[EW])\s*$",
    re.I,
)
WARNING_POSITION_RE = re.compile(
    r"^(?P<time>\d{6})Z\s+---\s+NEAR\s+"
    r"(?P<lat>\d{1,2}(?:\.\d+)?)(?P<lat_h>[NS])\s+"
    r"(?P<lon>\d{1,3}(?:\.\d+)?)(?P<lon_h>[EW])\s*$",
    re.I,
)
ACCURACY_RE = re.compile(r"POSITION ACCURATE TO WITHIN\s+(?P<accuracy>\d+)\s+NM", re.I)
WIND_RE = re.compile(r"MAX SUSTAINED WINDS\s+-\s+(?P<wind>\d+)\s+KT,\s+GUSTS\s+(?P<gust>\d+)\s+KT", re.I)
MOVEMENT_RE = re.compile(r"MOVEMENT PAST SIX HOURS\s+-\s+(?P<direction>\d+)\s+DEGREES\s+AT\s+(?P<speed>\d+)\s+KTS", re.I)
VECTOR_RE = re.compile(r"VECTOR TO\s+(?P<hour>\d+)\s+HR POSIT:\s+(?P<direction>\d+)\s+DEG/\s*(?P<speed>\d+)\s+KTS", re.I)
RADIUS_START_RE = re.compile(
    r"^RADIUS OF\s+(?P<threshold>\d+)\s+KT WINDS\s+-\s+(?P<radius>\d+)\s+NM\s+"
    r"(?P<quadrant>NORTHEAST|SOUTHEAST|SOUTHWEST|NORTHWEST)\s+QUADRANT$",
    re.I,
)
RADIUS_CONT_RE = re.compile(
    r"^(?P<radius>\d+)\s+NM\s+(?P<quadrant>NORTHEAST|SOUTHEAST|SOUTHWEST|NORTHWEST)\s+QUADRANT$",
    re.I,
)


def _signed_coordinate(value: str, hemisphere: str) -> float:
    number = float(value)
    return -number if hemisphere.upper() in {"S", "W"} else number


class PgtwWarningParser(BaseParser):
    """JTWC/WRNCEN PGTW WTPN/WDPN tropical cyclone warning parser."""

    def supports(self, normalized: str) -> bool:
        heading = parse_heading(normalized)
        return bool(
            heading
            and heading.get("center") == "PGTW"
            and heading.get("ttaa") in {"WTPN", "WDPN"}
            and ("WARNING POSITION" in normalized.upper() or "FORECASTS:" in normalized.upper())
        )

    def parse(self, raw: str) -> dict[str, Any]:
        normalized = normalize_tac(raw)
        heading = parse_heading(normalized)
        result = ParseResult(
            family="pgtw_tropical_cyclone_warning",
            raw=raw,
            normalized=normalized,
            heading=heading,
        )
        result.fields["source_profile"] = {
            "value": "PGTW/JTWC",
            "meaning": "Joint Typhoon Warning Center tropical cyclone warning",
            "confidence": "high",
        }

        storm = STORM_RE.search(normalized)
        system: dict[str, Any] = {
            "identity": f"{storm.group('name').strip().upper()} / {storm.group('number').upper()}" if storm else "UNKNOWN",
            "raw": normalized,
            "fields": {},
            "discussion": [],
        }
        if storm:
            classification = storm.group("classification").upper()
            system["fields"].update({
                "name": Field(storm.group("name").strip().upper(), storm.group("name").strip().upper(), meaning="storm name").to_dict(),
                "storm_number": Field(storm.group("number").upper(), storm.group("number").upper(), meaning="JTWC storm number").to_dict(),
                "classification": Field(classification, classification, meaning="current classification").to_dict(),
            })

        current_forecast: dict[str, Any] | None = None
        pending_lead: int | None = None
        pending_radius_threshold: int | None = None
        in_remarks = False
        section = ""
        for line in normalized.splitlines():
            stripped = line.strip()
            if not stripped or (heading and stripped == heading["raw"]):
                continue
            upper = stripped.upper()
            if upper in {"NNNN", "---", "REMARKS:"}:
                if upper == "REMARKS:":
                    in_remarks = True
                pending_radius_threshold = None
                continue
            if in_remarks:
                continue
            if upper.startswith("MSGID/") or upper.startswith("SUBJ/") or upper in {"RMKS/", "FORECASTS:", "EXTENDED OUTLOOK:", "LONG RANGE OUTLOOK:"}:
                if upper == "FORECASTS:" or upper.endswith("OUTLOOK:"):
                    section = "forecast"
                continue
            if upper == "WARNING POSITION:":
                section = "current"
                current_forecast = None
                pending_radius_threshold = None
                continue
            if match := FORECAST_HEADER_RE.match(stripped):
                pending_lead = int(match.group("lead"))
                current_forecast = None
                pending_radius_threshold = None
                section = "forecast"
                continue
            if pending_lead is not None and (position := POSITION_RE.match(stripped)):
                current_forecast = {
                    "lead_time": Field(f"{pending_lead}H", pending_lead, "hour", "forecast lead time").to_dict(),
                    "valid_time": Field(position.group("time") + "UTC", position.group("time") + "UTC", meaning="forecast valid time").to_dict(),
                    "position": self._position_field(position),
                    "raw": stripped,
                }
                result.forecasts.append(current_forecast)
                pending_lead = None
                pending_radius_threshold = None
                continue
            if section == "current" and (position := WARNING_POSITION_RE.match(stripped)):
                system["fields"]["position"] = self._position_field(position)
                system["fields"]["analysis_time"] = Field(position.group("time") + "UTC", position.group("time") + "UTC", meaning="warning position valid time").to_dict()
                continue

            target = current_forecast if current_forecast is not None else system["fields"]
            if accuracy := ACCURACY_RE.search(stripped):
                target["position_accuracy"] = Field(accuracy.group(0), int(accuracy.group("accuracy")), "nm", "position uncertainty radius").to_dict()
                continue
            if wind := WIND_RE.search(stripped):
                target["max_wind"] = Field(wind.group(0), int(wind.group("wind")), "kt", "maximum sustained wind").to_dict()
                target["gust"] = Field(wind.group(0), int(wind.group("gust")), "kt", "gust wind").to_dict()
                continue
            if movement := MOVEMENT_RE.search(stripped):
                target["movement"] = Field(stripped, {"direction_degree": int(movement.group("direction")), "speed": int(movement.group("speed"))}, "kt", "past six-hour movement").to_dict()
                continue
            if vector := VECTOR_RE.search(stripped):
                target["movement"] = Field(stripped, {"direction_degree": int(vector.group("direction")), "speed": int(vector.group("speed")), "to_hour": int(vector.group("hour"))}, "kt", "forecast vector").to_dict()
                continue
            if radius := RADIUS_START_RE.match(stripped):
                pending_radius_threshold = int(radius.group("threshold"))
                self._append_radius(target, stripped, pending_radius_threshold, radius.group("radius"), radius.group("quadrant"))
                continue
            if pending_radius_threshold is not None and (radius := RADIUS_CONT_RE.match(stripped)):
                self._append_radius(target, stripped, pending_radius_threshold, radius.group("radius"), radius.group("quadrant"))
                continue
            if pending_radius_threshold is not None:
                pending_radius_threshold = None
            if re.match(r"^(?:BECOMING|SUBTROPICAL|EXTRATROPICAL)\b", stripped, re.I):
                target["status"] = Field(stripped, stripped, meaning="forecast status").to_dict()
                continue

        if system["identity"] != "UNKNOWN" or system["fields"]:
            result.systems.append(system)
        result.fields["human_summary"] = self._summary(result)
        return result.to_dict()

    def _position_field(self, match: re.Match[str]) -> dict[str, Any]:
        return Field(
            match.group(0),
            {
                "lat": _signed_coordinate(match.group("lat"), match.group("lat_h")),
                "lon": _signed_coordinate(match.group("lon"), match.group("lon_h")),
            },
            "degree",
            "storm center position",
        ).to_dict()

    def _append_radius(self, target: dict[str, Any], raw: str, threshold: int, radius: str, quadrant: str) -> None:
        radius_nm = int(radius)
        target.setdefault("wind_radii", []).append(Field(raw, {
            "threshold_kt": threshold,
            "radius_nm": radius_nm,
            "radius_km": round(radius_nm * 1.852, 1),
            "quadrant": quadrant.upper(),
        }, "nm", "wind radius by quadrant").to_dict())

    def _summary(self, result: ParseResult) -> str:
        heading = result.heading or {}
        issue = heading.get("issue_time", {}).get("raw", "")
        system = result.systems[0] if result.systems else None
        if not system:
            return f"JTWC(PGTW)於 {issue}Z 發布熱帶氣旋警報。"
        position = system.get("fields", {}).get("position", {}).get("value")
        suffix = f"目前位置 {position['lat']}N、{position['lon']}E。" if position else ""
        return f"JTWC(PGTW)於 {issue}Z 發布 {system['identity']} 警報。{suffix}預報位置 {len(result.forecasts)} 筆。"
