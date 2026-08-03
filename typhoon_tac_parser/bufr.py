from __future__ import annotations

import base64
import ast
import json
import re
from dataclasses import dataclass
from typing import Any

from .centers import TROPICAL_CYCLONE_CENTERS, issuing_agency


ECMWF_BUFR_VALIDATOR_URL = "https://codes.ecmwf.int/bufr/validator"
MAX_ECMWF_VALIDATOR_BYTES = 2 * 1024 * 1024
WMO_BINARY_HEADING_RE = re.compile(rb"(?P<ttaa>[A-Z]{4})(?P<ii>\d{0,2})\s+(?P<center>[A-Z]{4})\s+(?P<time>\d{6})")


ISSUING_CENTERS = TROPICAL_CYCLONE_CENTERS


@dataclass
class BufrSection:
    number: int
    offset: int
    length: int

    def to_dict(self) -> dict[str, int]:
        return {"number": self.number, "offset": self.offset, "length": self.length}


def is_bufr_payload(data: bytes) -> bool:
    return b"BUFR" in data[:128]


def parse_wmo_binary_heading(data: bytes) -> dict[str, Any] | None:
    marker = data.find(b"BUFR")
    prefix = data[:marker if marker >= 0 else min(len(data), 80)]
    match = WMO_BINARY_HEADING_RE.search(prefix)
    if not match:
        return None
    time = match.group("time").decode("ascii")
    center = match.group("center").decode("ascii")
    return {
        "ttaa": match.group("ttaa").decode("ascii"),
        "ii": match.group("ii").decode("ascii"),
        "center": center,
        "issuing_agency": issuing_agency(center) or "Unknown",
        "issue_time": {
            "day": int(time[:2]),
            "hour": int(time[2:4]),
            "minute": int(time[4:6]),
            "timezone": "UTC",
            "raw": time,
        },
        "raw": match.group(0).decode("ascii"),
    }


def parse_uint24(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 3], "big")


def parse_bufr_envelope(data: bytes) -> dict[str, Any]:
    marker = data.find(b"BUFR")
    if marker < 0:
        raise ValueError("BUFR marker was not found.")
    if len(data) < marker + 8:
        raise ValueError("BUFR payload is too short.")

    total_length = parse_uint24(data, marker + 4)
    edition = data[marker + 7]
    bufr_end = marker + total_length
    warnings = []
    if bufr_end > len(data):
        warnings.append("BUFR declared length exceeds available bytes.")
        bufr_end = len(data)
    if data[bufr_end - 4 : bufr_end] != b"7777":
        trailer = data.rfind(b"7777", marker)
        if trailer >= 0:
            warnings.append("BUFR trailer was not at declared end; using nearest 7777 marker.")
            bufr_end = trailer + 4
        else:
            warnings.append("BUFR 7777 trailer was not found.")

    sections = []
    offset = marker + 8
    section_number = 1
    section2_present = False
    while offset + 3 <= bufr_end - 4 and section_number <= 4:
        length = parse_uint24(data, offset)
        if length <= 0 or offset + length > bufr_end:
            warnings.append(f"Section {section_number} has invalid length {length}.")
            break
        sections.append(BufrSection(section_number, offset, length).to_dict())
        if section_number == 1 and offset + 8 < len(data):
            section2_present = bool(data[offset + 7] & 0x80)
            section_number = 2 if section2_present else 3
        else:
            section_number += 1
        offset += length

    heading = parse_wmo_binary_heading(data)
    center = heading["center"] if heading else None
    decoded = decode_bufr_payload(data[marker:bufr_end])
    result = {
        "family": "bufr",
        "format": "BUFR",
        "heading": heading,
        "issuing_center": center,
        "issuing_agency": (issuing_agency(center) or "Unknown") if center else None,
        "bufr": {
            "offset": marker,
            "declared_length": total_length,
            "available_length": max(0, bufr_end - marker),
            "edition": edition,
            "sections": sections,
            "section2_present": section2_present,
            "has_7777_trailer": b"7777" in data[marker:bufr_end],
        },
        "validation": {
            "provider": "ECMWF BUFR Validator",
            "url": ECMWF_BUFR_VALIDATOR_URL,
            "eligible_for_upload": len(data) <= MAX_ECMWF_VALIDATOR_BYTES,
            "status": "not_uploaded",
            "note": "ECMWF validator is an upload service; this parser records upload eligibility and BUFR envelope metadata.",
        },
        "warnings": warnings,
    }
    if decoded:
        result["decoded"] = decoded
    return result


def decode_bufr_payload(payload: bytes) -> dict[str, Any] | None:
    try:
        from pybufrkit.decoder import Decoder
        from pybufrkit.renderer import FlatJsonRenderer
    except Exception as exc:
        return {"status": "decoder_unavailable", "error": str(exc)}
    try:
        message = Decoder().process(payload)
        rendered = FlatJsonRenderer().render(message)
        flat = ast.literal_eval(rendered) if isinstance(rendered, str) else rendered
        decoded: dict[str, Any] = {
            "status": "decoded",
            "table_group": str(getattr(message, "table_group_key", "")),
            "unexpanded_descriptors": flat[2][6] if len(flat) > 2 and len(flat[2]) > 6 else [],
        }
        values = _flat_subset_values(flat)
        if values:
            decoded["values"] = _iucc_tropical_cyclone_analysis(values)
        return decoded
    except Exception as exc:
        return {"status": "decode_failed", "error": str(exc)}


def _flat_subset_values(flat: list[Any]) -> list[Any]:
    try:
        return flat[3][2][0]
    except Exception:
        return []


def _decode_ascii(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bytes):
        return value.decode("ascii", "ignore").strip()
    return str(value).strip()


def _iucc_tropical_cyclone_analysis(values: list[Any]) -> dict[str, Any]:
    trend_24h = values[27] if len(values) > 27 else None
    fields = [
        ("originating_centre", "ORIGINATING CENTRE", values[0] if len(values) > 0 else None),
        ("originating_subcentre", "ORIGINATING/GENERATING SUB-CENTRE", values[1] if len(values) > 1 else None),
        ("year", "YEAR", values[2] if len(values) > 2 else None),
        ("month", "MONTH", values[3] if len(values) > 3 else None),
        ("day", "DAY", values[4] if len(values) > 4 else None),
        ("hour", "HOUR", values[5] if len(values) > 5 else None),
        ("minute", "MINUTE", values[6] if len(values) > 6 else None),
        ("satellite_identifier", "SATELLITE IDENTIFIER", values[7] if len(values) > 7 else None),
        ("analysis_method", "METHOD OF TROPICAL CYCLONE INTENSITY ANALYSIS USING SATELLITE DATA", values[8] if len(values) > 8 else None),
        ("replication_factor", "DELAYED DESCRIPTOR REPLICATION FACTOR", values[9] if len(values) > 9 else None),
        ("storm_name", "WMO LONG STORM NAME", _decode_ascii(values[10]) if len(values) > 10 else None),
        ("international_number", "TYPHOON INTERNATIONAL COMMON NUMBER", _decode_ascii(values[11]) if len(values) > 11 else None),
        ("tc_identifier", "IDENTIFICATION NUMBER OF TROPICAL CYCLONE", values[12] if len(values) > 12 else None),
        ("attribute_significance", "METEOROLOGICAL ATTRIBUTE SIGNIFICANCE", values[13] if len(values) > 13 else None),
        ("latitude", "LATITUDE", values[14] if len(values) > 14 else None),
        ("longitude", "LONGITUDE", values[15] if len(values) > 15 else None),
        ("attribute_significance_end", "METEOROLOGICAL ATTRIBUTE SIGNIFICANCE", values[16] if len(values) > 16 else None),
        ("analysis_interval_hours", "TIME INTERVAL OF THE TROPICAL CYCLONE ANALYSIS", values[17] if len(values) > 17 else None),
        ("motion_direction_degree", "DIRECTION OF MOTION OF FEATURE", values[18] if len(values) > 18 else None),
        ("motion_speed", "SPEED OF MOTION OF FEATURE", values[19] if len(values) > 19 else None),
        ("position_accuracy_code", "ACCURACY OF GEOGRAPHICAL POSITION", values[20] if len(values) > 20 else None),
        ("overcast_cloud_diameter_code", "MEAN DIAMETER OF OVERCAST CLOUD", values[21] if len(values) > 21 else None),
        ("intensity_change_24h_code", "APPARENT 24-HOUR CHANGE IN INTENSITY", values[22] if len(values) > 22 else None),
        ("ci_number", "CURRENT INTENSITY (CI) NUMBER", values[23] if len(values) > 23 else None),
        ("dt_number", "DATA TROPICAL (DT) NUMBER", values[24] if len(values) > 24 else None),
        ("dt_cloud_pattern_type", "CLOUD PATTERN TYPE OF DT NUMBER", values[25] if len(values) > 25 else None),
        ("met_number", "MODEL EXPECTED TROPICAL (MET) NUMBER", values[26] if len(values) > 26 else None),
        ("trend_24h", "TREND OF PAST 24-HOUR CHANGE", trend_24h),
        ("trend_24h_code", "24-HOUR TREND CODE", _dvorak_trend_code(trend_24h)),
        ("pt_number", "PATTERN TROPICAL (PT) NUMBER", values[28] if len(values) > 28 else None),
        ("pt_cloud_picture_type", "CLOUD PICTURE TYPE OF PT NUMBER", values[29] if len(values) > 29 else None),
        ("final_t_number", "FINAL TROPICAL (T) NUMBER", values[30] if len(values) > 30 else None),
        ("final_t_type", "TYPE OF FINAL T-NUMBER", values[31] if len(values) > 31 else None),
    ]
    return {
        "kind": "tropical_cyclone_satellite_analysis",
        "label": "熱帶氣旋衛星強度分析",
        "fields": [{"key": key, "label": label, "value": value} for key, label, value in fields],
    }


def _dvorak_trend_code(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 0:
        return {"code": "D", "value": number, "period": "24h", "direction": "developing", "text": f"D{number:g}/24h（增強）"}
    if number < 0:
        return {"code": "W", "value": abs(number), "period": "24h", "direction": "weakening", "text": f"W{abs(number):g}/24h（減弱）"}
    return {"code": "S", "value": 0, "period": "24h", "direction": "steady", "text": "S0.0/24h（維持）"}


def encode_record_bytes(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def decode_record_bytes(encoded: str) -> bytes:
    return base64.b64decode(encoded.encode("ascii"))
