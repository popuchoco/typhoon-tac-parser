from __future__ import annotations

import base64
import ast
import json
import logging
import math
import re
from dataclasses import dataclass
from typing import Any

from .centers import TROPICAL_CYCLONE_CENTERS, issuing_agency


ECMWF_BUFR_VALIDATOR_URL = "https://codes.ecmwf.int/bufr/validator"
MAX_ECMWF_VALIDATOR_BYTES = 2 * 1024 * 1024
WMO_BINARY_HEADING_RE = re.compile(rb"(?P<ttaa>[A-Z]{4})(?P<ii>\d{0,2})\s+(?P<center>[A-Z]{4})\s+(?P<time>\d{6})")


ISSUING_CENTERS = TROPICAL_CYCLONE_CENTERS
LOGGER = logging.getLogger(__name__)


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
    decoded = decode_bufr_payload(
        data[marker:bufr_end],
        product_code=heading.get("ttaa") if heading else None,
    )
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


def decode_bufr_payload(payload: bytes, product_code: str | None = None) -> dict[str, Any] | None:
    try:
        from pybufrkit.decoder import Decoder
        from pybufrkit.renderer import FlatJsonRenderer
    except Exception as exc:
        LOGGER.warning("BUFR decoder is unavailable: %s", exc)
        return {"status": "decoder_unavailable", "error": str(exc)}
    try:
        message = Decoder().process(payload)
        rendered = FlatJsonRenderer().render(message)
        flat = ast.literal_eval(rendered) if isinstance(rendered, str) else rendered
        unexpanded_descriptors = flat[2][6] if len(flat) > 2 and len(flat[2]) > 6 else []
        subsets = _flat_subset_values(flat)
        decoded: dict[str, Any] = {
            "status": "decoded",
            "table_group": str(getattr(message, "table_group_key", "")),
            "unexpanded_descriptors": _json_safe(unexpanded_descriptors),
            "subset_count": len(subsets),
            "is_compressed": bool(flat[2][4]) if len(flat) > 2 and len(flat[2]) > 4 else False,
        }
        if subsets:
            # IUCC carries the WMO tropical-cyclone satellite-analysis sequence.
            # Other BUFR products must not be interpreted using those fixed offsets.
            if product_code == "IUCC" and 316052 in unexpanded_descriptors and len(subsets[0]) >= 32:
                decoded["values"] = _iucc_tropical_cyclone_analysis(subsets[0])
            else:
                decoded["values"] = _generic_bufr_values(
                    message, subsets, unexpanded_descriptors, product_code=product_code
                )
        return decoded
    except Exception as exc:
        LOGGER.exception("BUFR payload decoding failed")
        return {"status": "decode_failed", "error": str(exc)}


def _flat_subset_values(flat: list[Any]) -> list[list[Any]]:
    try:
        subsets = flat[3][2]
        if not isinstance(subsets, (list, tuple)):
            return []
        if not subsets:
            return []
        if isinstance(subsets[0], (list, tuple)):
            return [list(subset) for subset in subsets]
        return [list(subsets)]
    except Exception:
        return []


def _generic_bufr_values(
    message: Any,
    subsets: list[list[Any]],
    unexpanded_descriptors: list[Any],
    product_code: str | None = None,
) -> dict[str, Any]:
    """Return generic BUFR values with descriptor metadata when the decoder exposes it."""
    template_data = getattr(getattr(message, "_template_data", None), "value", None)
    descriptor_sets = getattr(template_data, "decoded_descriptors_all_subsets", []) or []
    compressed_parameter = getattr(message, "is_compressed", None)
    is_compressed = getattr(compressed_parameter, "value", compressed_parameter)
    fields = []
    for subset_index, values in enumerate(subsets):
        descriptors = descriptor_sets[subset_index] if subset_index < len(descriptor_sets) else []
        for value_index, value in enumerate(values):
            descriptor = descriptors[value_index] if value_index < len(descriptors) else None
            descriptor_id = getattr(descriptor, "id", None)
            descriptor_code = None
            if descriptor is not None:
                try:
                    descriptor_code = f"{descriptor.F}-{descriptor.X:02d}-{descriptor.Y:03d}"
                except (AttributeError, TypeError, ValueError):
                    descriptor_code = None
            descriptor_name = getattr(descriptor, "name", None)
            unit = getattr(descriptor, "unit", None)
            field_label = descriptor_name or f"值 {value_index + 1}"
            if descriptor_code:
                field_label = f"{field_label} ({descriptor_code})"
            fields.append(
                {
                    "key": f"subset_{subset_index + 1}_value_{value_index + 1}",
                    "label": field_label,
                    "subset": subset_index + 1,
                    "index": value_index + 1,
                    "descriptor": descriptor_code,
                    "descriptor_id": descriptor_id,
                    "descriptor_name": descriptor_name,
                    "unit": unit,
                    "value": _json_safe(value),
                }
            )

    result = {
        "kind": "generic_bufr",
        "label": "一般 BUFR 解碼欄位",
        "subset_count": len(subsets),
        "is_compressed": bool(is_compressed),
        "unexpanded_descriptors": _json_safe(unexpanded_descriptors),
        "fields": fields,
    }
    # IUCC10's repeated 0-01-027 groups identify separate tropical cyclones.
    # Keep the generic descriptor table intact while exposing only confidently
    # identified point locations as cyclone records for the BUFR dashboard map.
    if product_code == "IUCC" and {1027, 19150, 19106}.issubset(set(unexpanded_descriptors)):
        storms = _extract_iucc_storms(message, subsets)
        if storms:
            result["storms"] = storms
            result["label"] = "IUCC 熱帶氣旋衛星分析"
    return result


def _extract_iucc_storms(message: Any, subsets: list[list[Any]]) -> list[dict[str, Any]]:
    """Extract cyclone identity and center coordinates from repeated IUCC descriptors."""
    template_data = getattr(getattr(message, "_template_data", None), "value", None)
    descriptor_sets = getattr(template_data, "decoded_descriptors_all_subsets", []) or []
    storms: list[dict[str, Any]] = []

    for subset_index, values in enumerate(subsets):
        descriptors = descriptor_sets[subset_index] if subset_index < len(descriptor_sets) else []
        storm_starts = [
            index for index, descriptor in enumerate(descriptors)
            if getattr(descriptor, "id", None) == 1027
        ]
        for storm_index, start in enumerate(storm_starts):
            end = storm_starts[storm_index + 1] if storm_index + 1 < len(storm_starts) else min(len(descriptors), len(values))
            block = list(zip(descriptors[start:end], values[start:end]))
            record = {
                "subset": subset_index + 1,
                "name": None,
                "international_number": None,
                "tc_identifier": None,
                "latitude": None,
                "longitude": None,
            }
            descriptor_fields = {
                1027: "name",
                19150: "international_number",
                19106: "tc_identifier",
                5001: "latitude",
                5002: "latitude",
                6001: "longitude",
                6002: "longitude",
            }
            for descriptor, value in block:
                field = descriptor_fields.get(getattr(descriptor, "id", None))
                if field is None or record[field] is not None:
                    continue
                safe_value = _json_safe(value)
                if field in {"name", "international_number"}:
                    text_value = str(safe_value).strip() if safe_value is not None else ""
                    record[field] = text_value or None
                elif field == "tc_identifier":
                    record[field] = safe_value
                else:
                    try:
                        numeric_value = float(safe_value)
                    except (TypeError, ValueError):
                        continue
                    if math.isfinite(numeric_value):
                        record[field] = numeric_value
            # A storm block is useful on a map only when it has usable identity
            # and a complete, valid coordinate pair. Retain a single missing
            # international number as None (e.g. WMO name "nameless").
            if record["name"] is None and record["tc_identifier"] is None:
                continue
            latitude, longitude = record["latitude"], record["longitude"]
            if not _valid_coordinates(latitude, longitude):
                continue
            storms.append(record)
    return storms


def _valid_coordinates(latitude: Any, longitude: Any) -> bool:
    try:
        latitude_value = float(latitude)
        longitude_value = float(longitude)
    except (TypeError, ValueError):
        return False
    return (
        math.isfinite(latitude_value)
        and math.isfinite(longitude_value)
        and -90 <= latitude_value <= 90
        and -180 <= longitude_value <= 180
    )


def _json_safe(value: Any) -> Any:
    """Convert pybufrkit values to JSON-safe primitives, including padded IA5 bytes."""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace").replace("\x00", "").strip()
    if isinstance(value, bytearray):
        return _json_safe(bytes(value))
    if isinstance(value, dict):
        return {str(_json_safe(key)): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    return str(value)


def _decode_ascii(value: Any) -> str:
    if value is None:
        return ""
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
    decoded = {
        "kind": "tropical_cyclone_satellite_analysis",
        "label": "熱帶氣旋衛星強度分析",
        "fields": [{"key": key, "label": label, "value": value} for key, label, value in fields],
    }
    storm = {
        "subset": 1,
        "name": _decode_ascii(values[10]) if len(values) > 10 else None,
        "international_number": _decode_ascii(values[11]) if len(values) > 11 else None,
        "tc_identifier": values[12] if len(values) > 12 else None,
        "latitude": values[14] if len(values) > 14 else None,
        "longitude": values[15] if len(values) > 15 else None,
    }
    if _valid_coordinates(storm["latitude"], storm["longitude"]):
        storm["latitude"] = float(storm["latitude"])
        storm["longitude"] = float(storm["longitude"])
        decoded["storms"] = [storm]
    return decoded


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
