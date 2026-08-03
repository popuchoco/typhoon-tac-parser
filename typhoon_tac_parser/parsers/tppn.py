from __future__ import annotations

import re
from typing import Any

from ..models import Field, ParseResult
from ..normalization import normalize_tac, parse_heading
from .base import BaseParser


ST_WIND_TABLE = {
    1.5: {"min": 25, "max": 30},
    2.5: {"min": 35, "max": 40},
    3.0: {"min": 45, "max": 50},
    3.5: {"min": 55, "max": 65},
}

DVORAK_WIND_TABLE = {
    1.0: 25,
    1.5: 25,
    2.0: 30,
    2.5: 35,
    3.0: 45,
    3.5: 55,
    4.0: 65,
    4.5: 77,
    5.0: 90,
    5.5: 102,
    6.0: 115,
    6.5: 127,
    7.0: 140,
    7.5: 155,
    8.0: 170,
}

TREND_MEANINGS = {
    "S": "steady",
    "D": "developing",
    "W": "weakening",
}


class TppnSubtropicalParser(BaseParser):
    """JTWC TPPN/TPPZ satellite analysis parser for Dvorak T and Hebert-Poteat ST bulletins."""

    def supports(self, normalized: str) -> bool:
        heading = parse_heading(normalized)
        return bool(heading and heading["center"] == "PGTW" and heading["ttaa"] in {"TPPN", "TPPZ"})

    def parse(self, raw: str) -> dict[str, Any]:
        normalized = normalize_tac(raw)
        heading = parse_heading(normalized)
        fields = self._letter_fields(normalized)
        is_st = fields.get("F", "").upper().startswith("ST") or "SUBTROPICAL" in fields.get("A", "").upper()
        family = "hebert_poteat_subtropical_analysis" if is_st else "dvorak_tropical_satellite_analysis"
        result = ParseResult(
            family=family,
            raw=raw,
            normalized=normalized,
            heading=heading,
        )
        result.fields["source_profile"] = {
            "value": "JTWC",
            "meaning": "JTWC satellite analysis bulletin",
            "confidence": "high",
        }
        technique = "Hebert-Poteat" if is_st else "Dvorak"
        result.fields["technique"] = {
            "value": technique,
            "meaning": "Subtropical cyclone satellite classification technique" if is_st else "Tropical cyclone satellite intensity analysis technique",
            "confidence": "high",
        }
        result.systems = [self._system(fields, is_st)] if fields else []
        result.fields["human_summary"] = self._summary(heading, fields)
        return result.to_dict()

    def _letter_fields(self, text: str) -> dict[str, str]:
        fields: dict[str, str] = {}
        current: str | None = None
        chunks: list[str] = []
        for line in text.splitlines():
            match = re.match(r"^([A-I])\.\s*(.*)$", line.strip())
            if match:
                if current:
                    fields[current] = " ".join(chunks).strip()
                current = match.group(1)
                chunks = [match.group(2).strip()]
            elif current:
                chunks.append(line.strip())
        if current:
            fields[current] = " ".join(chunks).strip()
        return fields

    def _system(self, fields: dict[str, str], is_st: bool) -> dict[str, Any]:
        subject = fields.get("A", "")
        identity = self._identity(subject)
        system = {
            "identity": identity,
            "name": subject,
            "raw": subject,
            "fields": {},
            "discussion": [],
        }
        if fields.get("B"):
            system["fields"]["analysis_time"] = Field(fields["B"], fields["B"], meaning="analysis time").to_dict()
        if fields.get("C") and fields.get("D"):
            system["fields"]["position"] = self._position(fields["C"], fields["D"])
        if fields.get("E"):
            system["fields"]["satellite_fix"] = Field(fields["E"], fields["E"], meaning="satellite and fix method").to_dict()
        if fields.get("F"):
            if is_st:
                system["fields"]["st_classification"] = self._st_classification(fields["F"])
            else:
                system["fields"]["dvorak_classification"] = self._dvorak_classification(fields["F"])
        if fields.get("G"):
            system["fields"]["imagery"] = Field(fields["G"], fields["G"].split("/"), meaning="imagery channels used").to_dict()
        if fields.get("H"):
            system["discussion"].append(fields["H"].removeprefix("REMARKS:").strip())
        if fields.get("I"):
            system["fields"]["additional_positions"] = Field(fields["I"].removeprefix("ADDITIONAL POSITIONS:").strip(), fields["I"], meaning="additional positions").to_dict()
        return system

    def _identity(self, subject: str) -> str:
        match = re.search(r"\b(\d{2}[A-Z])\b", subject)
        return match.group(1) if match else subject

    def _position(self, lat_raw: str, lon_raw: str) -> dict[str, Any]:
        lat_match = re.match(r"(?P<value>\d+(?:\.\d+)?)(?P<hemi>[NS])", lat_raw)
        lon_match = re.match(r"(?P<value>\d+(?:\.\d+)?)(?P<hemi>[EW])", lon_raw)
        lat = float(lat_match.group("value")) if lat_match else None
        lon = float(lon_match.group("value")) if lon_match else None
        if lat_match and lat_match.group("hemi") == "S":
            lat *= -1
        if lon_match and lon_match.group("hemi") == "W":
            lon *= -1
        return Field(f"{lat_raw} {lon_raw}", {"lat": lat, "lon": lon}, "degree", "analyzed subtropical position").to_dict()

    def _st_classification(self, raw: str) -> dict[str, Any]:
        match = re.search(r"ST(?P<st>\d+(?:\.\d+)?)(?:/(?P<trend>\d+(?:\.\d+)?))?", raw, re.I)
        value: dict[str, Any] = {"raw_code": raw}
        if match:
            st = float(match.group("st"))
            value["st_number"] = st
            if match.group("trend"):
                value["trend_number"] = float(match.group("trend"))
            if st in ST_WIND_TABLE:
                value["cloud_feature_wind_kt"] = ST_WIND_TABLE[st]
        return Field(raw, value, meaning="Hebert-Poteat subtropical classification").to_dict()

    def _dvorak_classification(self, raw: str) -> dict[str, Any]:
        match = re.search(r"T(?P<t>\d+(?:\.\d+)?)(?:/(?P<ci>\d+(?:\.\d+)?))?(?:/(?P<trend_code>[SDW])(?P<trend_value>-?\d+(?:\.\d+)?)/(?P<period>\d+HRS)|/(?P<note>INITIAL FIX|INIT OBS))?(?:\s+STT:\s*(?P<short_code>[SDW])(?P<short_value>-?\d+(?:\.\d+)?)/(?P<short_period>\d+HRS))?", raw, re.I)
        value: dict[str, Any] = {"raw_code": raw}
        if match:
            t_number = float(match.group("t"))
            value["t_number"] = t_number
            if match.group("ci"):
                ci = float(match.group("ci"))
                value["ci_number"] = ci
                if ci in DVORAK_WIND_TABLE:
                    value["ci_wind_kt"] = DVORAK_WIND_TABLE[ci]
            if t_number in DVORAK_WIND_TABLE:
                value["t_wind_kt"] = DVORAK_WIND_TABLE[t_number]
            if match.group("trend_code"):
                value["trend_24h"] = self._trend(match.group("trend_code"), match.group("trend_value"), match.group("period"))
            if match.group("note"):
                value["note"] = match.group("note").upper()
            if match.group("short_code"):
                value["short_term_trend"] = self._trend(match.group("short_code"), match.group("short_value"), match.group("short_period"))
        return Field(raw, value, meaning="Dvorak T-number classification").to_dict()

    def _trend(self, code: str, value: str, period: str) -> dict[str, Any]:
        code = code.upper()
        return {
            "code": code,
            "value": float(value),
            "period": period,
            "direction": TREND_MEANINGS.get(code, "unknown"),
        }

    def _summary(self, heading: dict[str, Any] | None, fields: dict[str, str]) -> str:
        issue = heading.get("issue_time", {}).get("raw", "") if heading else ""
        is_st = fields.get("F", "").upper().startswith("ST") or "SUBTROPICAL" in fields.get("A", "").upper()
        subject = fields.get("A", "unknown system")
        classification = fields.get("F", "")
        remarks = fields.get("H", "").removeprefix("REMARKS:").strip()
        parts = [
            f"JTWC issued TPPN {'subtropical' if is_st else 'tropical'} satellite analysis at {issue}Z.",
            f"Analysis subject: {subject}.",
        ]
        if classification:
            parts.append(f"{'Hebert-Poteat' if is_st else 'Dvorak'} classification: {classification}.")
        if remarks:
            parts.append(f"Remarks: {remarks}")
        return "\n".join(parts)
