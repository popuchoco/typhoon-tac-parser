from __future__ import annotations

import re
from typing import Any

from ..models import Field, ParseResult
from ..normalization import normalize_tac, parse_heading, tokenize
from .base import BaseParser


COORD_RE = re.compile(r"(?P<lat>\d{1,2}(?:\.\d+)?)(?P<lat_h>[NS])\s+(?P<lon>\d{1,3}(?:\.\d+)?)(?P<lon_h>[EW])")
COMPACT_COORD_RE = re.compile(r"(?P<lat>\d{2,4})(?P<lat_h>[NS])?\s+(?P<lon>\d{3,5})(?P<lon_h>[EW])?")
TIME_RE = re.compile(r"\b(?P<day>\d{2})(?P<hour>\d{2})(?P<minute>\d{2})Z?\b")
WIND_RE = re.compile(r"(?:MAX(?:IMUM)?(?: SUSTAINED(?: SURFACE)?)? WINDS?(?: WERE ESTIMATED AT)?|WINDS?)\s+(?P<wind>\d{1,3})(?:\s*TO\s*(?P<wind_to>\d{1,3}))?\s*(?P<unit>KT|KTS|KNOTS|M/S)", re.I)
BARE_WIND_RE = re.compile(r"\b(?P<wind>\d{1,3})(?P<unit>M/S|KT|KTS)\b", re.I)
GUST_RE = re.compile(r"GUST(?:ING)?(?: TO)?\s+(?P<gust>\d{1,3})\s*(?P<unit>KT|KTS|KNOTS|M/S)", re.I)
PRESSURE_RE = re.compile(r"(?:(?:CENTRAL|SEA LEVEL|MINIMUM SEA LEVEL) PRESSURE(?: IS ESTIMATED TO BE)?(?: NEAR)?|(?P<short>\d{3,4})HPA)\s*(?P<pressure>\d{3,4})?\s*(?P<unit>HPA|MB)?", re.I)
MOVE_RE = re.compile(r"(?:MOVE|MOV|TRACKED)\s+(?P<dir>[A-Z-]+)(?:WARD)?(?: AT)?\s+(?P<speed>\d{1,3})\s*(?P<unit>KT|KTS|KNOTS|KM/H)", re.I)
WIND_RADIUS_RE = re.compile(r"(?:(?P<threshold>\d{1,3})KTS?\s+WINDS\s+)?(?P<radius>\d{1,4})KM\s+(?P<quadrant>NORTHEAST|SOUTHEAST|SOUTHWEST|NORTHWEST|NORTH|EAST|SOUTH|WEST)", re.I)
FORECAST_RE = re.compile(r"^(?:P\+|TAU\s*)(?P<hour>\d{1,3})HR?\s+", re.I)
NAME_RE = re.compile(r"\b(?:SUPER\s*)?(?:TY|TS|TD|STY|TYPHOON|TROPICAL STORM|TROPICAL DEPRESSION)\s+(?P<name>[A-Z0-9-]+)", re.I)
INVEST_RE = re.compile(r"\bINVEST\s+(?P<id>\d{2}[A-Z])\b", re.I)


def signed_coord(value: str, hemi: str) -> float:
    signed = float(value)
    if hemi.upper() in {"S", "W"}:
        signed *= -1
    return signed


class TropicalCycloneParser(BaseParser):
    """Lossless parser for tropical cyclone TAC-style bulletins."""

    def parse(self, raw: str) -> dict[str, Any]:
        normalized = normalize_tac(raw)
        heading = parse_heading(normalized)
        result = ParseResult(
            family="tropical_cyclone",
            raw=raw,
            normalized=normalized,
            heading=heading,
        )
        result.fields["times"] = [self._time(m) for m in TIME_RE.finditer(normalized)]
        lines = normalized.splitlines()
        current: dict[str, Any] | None = None

        for line in lines:
            if heading and line == heading["raw"]:
                continue
            new_system = self._system_from_line(line)
            if new_system:
                current = new_system
                result.systems.append(current)
                continue
            forecast = self._forecast_from_line(line)
            if forecast:
                result.forecasts.append(forecast)
                continue
            extracted = self._extract_line_fields(line)
            if extracted and current is not None:
                if "wind_radius" in extracted and extracted["wind_radius"]["value"].get("threshold_kt") is None:
                    previous = current.get("fields", {}).get("wind_radii", [])
                    if previous:
                        extracted["wind_radius"]["value"]["threshold_kt"] = previous[-1]["value"].get("threshold_kt")
                current.setdefault("fields", {}).update(extracted)
                if "wind_radius" in extracted:
                    fields = current.setdefault("fields", {})
                    radii = fields.setdefault("wind_radii", [])
                    radii.append(extracted["wind_radius"])
                    fields.pop("wind_radius", None)
            elif extracted:
                result.fields.update(extracted)
            else:
                result.remarks.append(line)

        if not result.systems:
            result.warnings.append("No explicit tropical cyclone system identity was found.")
        if not any("position" in s.get("fields", {}) for s in result.systems) and not result.forecasts:
            result.warnings.append("No latitude/longitude position was found.")
        result.unparsed_tokens = self._unknown_tokens(normalized)
        return result.to_dict()

    def _time(self, match: re.Match[str]) -> dict[str, Any]:
        return Field(
            raw=match.group(0),
            value={
                "day": int(match.group("day")),
                "hour": int(match.group("hour")),
                "minute": int(match.group("minute")),
                "timezone": "UTC",
            },
            meaning="UTC date-time group",
        ).to_dict()

    def _system_from_line(self, line: str) -> dict[str, Any] | None:
        if "JOINT TYPHOON WRNCEN" in line.upper():
            return None
        name = NAME_RE.search(line)
        invest = INVEST_RE.search(line)
        if not name and not invest:
            return None
        identity = name.group("name").upper() if name else invest.group("id").upper()
        system = {"identity": identity, "raw": line, "fields": {}}
        fields = self._extract_line_fields(line)
        if fields:
            system["fields"] = fields
        return system

    def _forecast_from_line(self, line: str) -> dict[str, Any] | None:
        match = FORECAST_RE.search(line)
        if not match:
            return None
        data = {
            "lead_time": Field(match.group(0).strip(), int(match.group("hour")), "hour", "forecast lead time").to_dict(),
            "raw": line,
        }
        data.update(self._extract_line_fields(line))
        return data

    def _extract_line_fields(self, line: str) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        coord = COORD_RE.search(line)
        if coord:
            fields["position"] = Field(
                raw=coord.group(0),
                value={
                    "lat": signed_coord(coord.group("lat"), coord.group("lat_h")),
                    "lon": signed_coord(coord.group("lon"), coord.group("lon_h")),
                },
                unit="degree",
                meaning="storm center position",
            ).to_dict()
        wind = WIND_RE.search(line)
        if wind:
            value: Any = int(wind.group("wind"))
            if wind.group("wind_to"):
                value = {"from": value, "to": int(wind.group("wind_to"))}
            fields["max_wind"] = Field(wind.group(0), value, self._unit(wind.group("unit")), "maximum sustained wind").to_dict()
        elif "HPA" in line.upper():
            bare_wind = BARE_WIND_RE.search(line)
            if bare_wind:
                fields["max_wind"] = Field(
                    bare_wind.group(0),
                    int(bare_wind.group("wind")),
                    self._unit(bare_wind.group("unit")),
                    "maximum sustained wind inferred from position-pressure-wind line",
                    "medium",
                ).to_dict()
        gust = GUST_RE.search(line)
        if gust:
            fields["gust"] = Field(gust.group(0), int(gust.group("gust")), self._unit(gust.group("unit")), "gust wind").to_dict()
        pressure = self._pressure(line)
        if pressure:
            fields["pressure"] = pressure
        move = MOVE_RE.search(line)
        if move:
            fields["movement"] = Field(
                move.group(0),
                {"direction": move.group("dir").upper(), "speed": int(move.group("speed"))},
                self._unit(move.group("unit")),
                "storm movement",
            ).to_dict()
        radius = WIND_RADIUS_RE.search(line)
        if radius:
            fields["wind_radius"] = Field(
                radius.group(0),
                {
                    "threshold_kt": int(radius.group("threshold")) if radius.group("threshold") else None,
                    "radius_km": int(radius.group("radius")),
                    "quadrant": radius.group("quadrant").upper(),
                },
                "km",
                "wind radius by quadrant",
            ).to_dict()
        return fields

    def _pressure(self, line: str) -> dict[str, Any] | None:
        compact = re.search(r"\b(?P<value>\d{3,4})(?P<unit>HPA|MB)\b", line, re.I)
        verbose = re.search(r"PRESSURE.*?(?P<value>\d{3,4})\s*(?P<unit>HPA|MB)\b", line, re.I)
        match = verbose or compact
        if not match:
            return None
        return Field(match.group(0), int(match.group("value")), match.group("unit").lower(), "central or sea-level pressure").to_dict()

    def _unit(self, unit: str) -> str:
        unit = unit.upper()
        if unit in {"KT", "KTS", "KNOTS"}:
            return "kt"
        return unit.lower()

    def _unknown_tokens(self, text: str) -> list[str]:
        known = {"TYPHOON", "TROPICAL", "CYCLONE", "STORM", "DEPRESSION", "MAXIMUM", "SUSTAINED", "WINDS", "GUSTING", "PRESSURE", "MOVE", "MOV", "PRESENT", "POSITION"}
        return sorted({t for t in tokenize(text) if t.isalpha() and t.upper() not in known and len(t) > 14})
