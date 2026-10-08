from __future__ import annotations

import re
from typing import Any

from ..models import Field, ParseResult
from ..normalization import normalize_tac, parse_heading
from .base import BaseParser


COORDINATE_PAIR_RE = re.compile(
    r"(?P<lat>[NS]\d{4}|\d{4}[NS])\s+(?P<lon>[EW]\d{5}|\d{5}[EW])",
    re.I,
)
OBS_POSITION_RE = re.compile(
    r"^OBS PSN:\s*(?P<time>\d{2}/\d{4}Z)\s+"
    r"(?P<lat>[NS]\d{4}|\d{4}[NS])\s+(?P<lon>[EW]\d{5}|\d{5}[EW])$",
    re.I,
)
FORECAST_POSITION_RE = re.compile(
    r"^FCST PSN\s+\+(?P<lead>\d{1,3})\s+HR:\s*(?P<time>\d{2}/\d{4}Z)\s+"
    r"(?P<lat>[NS]\d{4}|\d{4}[NS])\s+(?P<lon>[EW]\d{5}|\d{5}[EW])$",
    re.I,
)
FORECAST_WIND_RE = re.compile(r"^FCST MAX WIND\s+\+(?P<lead>\d{1,3})\s+HR:\s*(?P<wind>\d{1,3})\s*KT$", re.I)
MOVEMENT_RE = re.compile(r"^(?P<direction>[A-Z]{1,3}|STNR)\s+(?P<speed>\d{1,3})\s*KT$", re.I)
TC_HEADER_RE = re.compile(r"^TC\s+ADVISORY$", re.I)


def _clean_rjtd_advisory(raw: str) -> str:
    # Some message gateways copy these TACs with NBSPs and add a literal \\ at
    # each line ending. Neither is part of the bulletin itself.
    text = raw.replace("\u00a0", " ").replace("\u202f", " ").replace("\u2009", " ")
    text = re.sub(r"\\[ \t]*$", "", text, flags=re.MULTILINE)
    return normalize_tac(text)


def _compact_dm(value: str) -> float:
    value = value.upper()
    hemisphere = value[0] if value[0] in "NSEW" else value[-1]
    digits = value[1:] if value[0] in "NSEW" else value[:-1]
    degree_width = 2 if hemisphere in "NS" else 3
    degrees = int(digits[:degree_width])
    minutes = int(digits[degree_width:])
    if minutes >= 60:
        raise ValueError(f"座標分值超出範圍：{value}")
    coordinate = degrees + minutes / 60
    limit = 90 if hemisphere in "NS" else 180
    if coordinate > limit:
        raise ValueError(f"座標超出有效範圍：{value}")
    return -coordinate if hemisphere in "SW" else coordinate


def _position(raw: str, lat_token: str, lon_token: str, meaning: str) -> dict[str, Any]:
    return Field(
        raw,
        {"lat": _compact_dm(lat_token), "lon": _compact_dm(lon_token)},
        "degree",
        meaning,
    ).to_dict()


class RjtdTcAdvisoryParser(BaseParser):
    """Parser for RJTD FKPQ31/32 TC ADVISORY bulletins."""

    def supports(self, normalized: str) -> bool:
        text = _clean_rjtd_advisory(normalized)
        heading = parse_heading(text)
        return bool(
            heading
            and heading.get("ttaa") == "FKPQ"
            and heading.get("center") == "RJTD"
            and any(TC_HEADER_RE.match(line.strip()) for line in text.splitlines())
        )

    def parse(self, raw: str) -> dict[str, Any]:
        normalized = _clean_rjtd_advisory(raw)
        heading = parse_heading(normalized)
        result = ParseResult("rjtd_tc_advisory", raw, normalized, heading)
        result.fields["source_profile"] = {
            "value": "RJTD/RSMC Tokyo",
            "meaning": "Japan Meteorological Agency tropical cyclone advisory",
            "confidence": "high",
        }
        if heading and heading.get("ii"):
            product_number = heading["ii"]
            result.fields["product_code"] = Field(
                f"FKPQ{product_number}",
                f"FKPQ{product_number}",
                meaning="WMO tropical cyclone advisory product code",
            ).to_dict()

        system: dict[str, Any] = {"identity": "UNKNOWN", "raw": normalized, "fields": {}}
        forecasts: dict[int, dict[str, Any]] = {}
        cb_active = False
        cb_raw_lines: list[str] = []
        cb_boundary: list[dict[str, float]] = []
        cb_top: int | None = None
        in_remarks = False

        for line in normalized.splitlines():
            text = line.strip()
            upper = text.upper()
            if not text or (heading and text == heading["raw"]):
                continue
            if TC_HEADER_RE.match(text):
                continue

            if cb_active:
                top = re.match(r"^TOP\s+FL\s*(\d{2,3})$", text, re.I)
                if top:
                    cb_top = int(top.group(1))
                    cb_raw_lines.append(text)
                    cb_active = False
                    system["fields"]["cb_area"] = self._cb_field(cb_raw_lines, cb_boundary, cb_top)
                    continue
                pairs = list(COORDINATE_PAIR_RE.finditer(text))
                if pairs and (text.startswith("-") or text.upper().startswith("CB:")):
                    cb_raw_lines.append(text)
                    cb_boundary.extend(self._pair_values(pair) for pair in pairs)
                    continue
                # A new labeled advisory group closes an incomplete CB clause.
                if re.match(r"^(?:[A-Z][A-Z ]*):", upper):
                    system["fields"]["cb_area"] = self._cb_field(cb_raw_lines, cb_boundary, cb_top)
                    cb_active = False

            if upper.startswith("CB:"):
                cb_active = True
                cb_raw_lines = [text]
                cb_boundary = [self._pair_values(pair) for pair in COORDINATE_PAIR_RE.finditer(text)]
                cb_top = None
                continue

            if match := re.match(r"^DTG:\s*(\d{8}/\d{4}Z)$", text, re.I):
                value = match.group(1).upper()
                result.fields["advisory_time"] = Field(value, value, meaning="advisory issue time in UTC").to_dict()
                continue
            if match := re.match(r"^TCAC:\s*(.+)$", text, re.I):
                value = match.group(1).strip().upper()
                result.fields["tropical_cyclone_advisory_center"] = Field(value, value, meaning="tropical cyclone advisory center").to_dict()
                continue
            if match := re.match(r"^TC:\s*(.+)$", text, re.I):
                name = match.group(1).strip().upper()
                system["identity"] = name
                system["fields"]["name"] = Field(name, name, meaning="tropical cyclone name").to_dict()
                continue
            if match := re.match(r"^ADVISORY NR:\s*(.+)$", text, re.I):
                number = match.group(1).strip()
                result.fields["advisory_number"] = Field(number, number, meaning="advisory sequence number").to_dict()
                system["fields"]["advisory_number"] = Field(number, number, meaning="advisory sequence number").to_dict()
                if system["identity"] != "UNKNOWN":
                    system["identity"] = f"{system['identity']} / {number}"
                continue
            if match := OBS_POSITION_RE.match(text):
                try:
                    system["fields"]["position"] = _position(
                        f"{match.group('lat')} {match.group('lon')}",
                        match.group("lat"),
                        match.group("lon"),
                        "observed tropical cyclone center position",
                    )
                except ValueError as exc:
                    result.warnings.append(str(exc))
                    continue
                system["fields"]["analysis_time"] = Field(match.group("time").upper(), match.group("time").upper(), meaning="observed position valid time in UTC").to_dict()
                continue
            if upper.startswith("MOV:"):
                raw_movement = text.partition(":")[2].strip()
                match = MOVEMENT_RE.match(raw_movement)
                if match:
                    movement = {
                        "direction": match.group("direction").upper(),
                        "speed": int(match.group("speed")),
                    }
                    system["fields"]["movement"] = Field(raw_movement, movement, "kt", "current storm movement").to_dict()
                else:
                    result.remarks.append(text)
                continue
            if upper.startswith("INTST CHANGE:"):
                value = text.partition(":")[2].strip().upper()
                meaning = {"NC": "無變化", "WKN": "減弱中", "INTSF": "增強中"}.get(value, "強度變化代碼")
                system["fields"]["intensity_change"] = Field(value, value, meaning=meaning).to_dict()
                continue
            if match := re.match(r"^C:\s*(\d{3,4})\s*HPA$", text, re.I):
                pressure = int(match.group(1))
                system["fields"]["pressure"] = Field(text, pressure, "hPa", "minimum central pressure").to_dict()
                continue
            if match := re.match(r"^MAX WIND:\s*(\d{1,3})\s*KT$", text, re.I):
                wind = int(match.group(1))
                system["fields"]["max_wind"] = Field(text, wind, "kt", "maximum sustained wind").to_dict()
                continue
            if match := FORECAST_POSITION_RE.match(text):
                lead = int(match.group("lead"))
                try:
                    forecast = forecasts.setdefault(lead, {"tau": f"+{lead}h", "hour": lead})
                    forecast.update({
                        "valid_time": Field(match.group("time").upper(), match.group("time").upper(), meaning="forecast valid time in UTC").to_dict(),
                        "position": _position(
                            f"{match.group('lat')} {match.group('lon')}",
                            match.group("lat"),
                            match.group("lon"),
                            "forecast tropical cyclone center position",
                        ),
                        "raw": text,
                    })
                except ValueError as exc:
                    result.warnings.append(str(exc))
                continue
            if match := FORECAST_WIND_RE.match(text):
                lead = int(match.group("lead"))
                forecast = forecasts.setdefault(lead, {"tau": f"+{lead}h", "hour": lead})
                wind = int(match.group("wind"))
                forecast["max_wind"] = Field(f"{wind}KT", wind, "kt", "forecast maximum sustained wind").to_dict()
                forecast["raw_max_wind"] = text
                continue
            if upper.startswith("RMK:"):
                in_remarks = True
                value = text.partition(":")[2].strip()
                if value:
                    result.remarks.append(value)
                continue
            if upper.startswith("NXT MSG:"):
                in_remarks = False
                value = text.partition(":")[2].strip()
                result.fields["next_message"] = Field(value, value, meaning="next advisory schedule").to_dict()
                continue
            if in_remarks:
                result.remarks.append(text)
            else:
                result.remarks.append(text)

        if cb_active:
            system["fields"]["cb_area"] = self._cb_field(cb_raw_lines, cb_boundary, cb_top)
        result.systems = [system] if system["fields"] else []
        result.forecasts = [forecasts[lead] for lead in sorted(forecasts)]
        if not system["fields"].get("position"):
            result.warnings.append("No OBS PSN position was found.")
        if not result.forecasts:
            result.warnings.append("No FCST PSN forecast positions were found.")
        result.fields["human_summary"] = self._summary(result, system)
        return result.to_dict()

    def _pair_values(self, match: re.Match[str]) -> dict[str, float]:
        return {
            "lat": _compact_dm(match.group("lat")),
            "lon": _compact_dm(match.group("lon")),
        }

    def _cb_field(self, raw_lines: list[str], boundary: list[dict[str, float]], top: int | None) -> dict[str, Any]:
        value: dict[str, Any] = {"boundary": boundary}
        if top is not None:
            value["top_flight_level"] = top
        confidence = "high" if len(boundary) >= 3 else "low"
        return Field("\n".join(raw_lines), value, meaning="cumulonimbus area boundary and top", confidence=confidence).to_dict()

    def _summary(self, result: ParseResult, system: dict[str, Any]) -> str:
        issue = (result.heading or {}).get("issue_time", {}).get("raw", "")
        fields = system["fields"]
        lines = [f"日本氣象廳 RSMC 於 {issue}Z 發布熱帶氣旋 TC Advisory。"]
        if system["identity"] != "UNKNOWN":
            lines.append(f"氣旋：{system['identity']}。")
        if position := fields.get("position", {}).get("value"):
            lines.append(
                f"觀測中心 {position['lat']:.2f}, {position['lon']:.2f}；"
                f"最大風速 {fields.get('max_wind', {}).get('value', '-')} kt。"
            )
        lines.append(f"解析到 {len(result.forecasts)} 個預報位置。")
        return "\n".join(lines)
