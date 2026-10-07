"""Parser for the workbench's plain-text multi-agency track comparison format.

This is intentionally separate from the five allow-listed WMO TAC bulletins.
It accepts files such as NOUL.TXT, where each agency has its own labelled
forecast track, and keeps every track independent for plotting.
"""

from __future__ import annotations

import re
from typing import Any


_TITLE_RE = re.compile(r"^\s*TROPICAL\s+CYCLONE\s+(?P<name>[^\r\n]+?)\s*$", re.I)
_PLAIN_TEXT_TITLE_RE = re.compile(
    r"^\s*Plain\s+text\s+data\s+for\s+tropical\s+cyclone\s+"
    r"(?P<name>[^()\r\n]+?)\s*(?:\((?P<details>[^)]*)\))?\s*$",
    re.I,
)
_ISSUE_RE = re.compile(r"^\s*\((?P<time>[^)]+?)\)\s*$")
_SECTION_RE = re.compile(
    r"^\s*(?P<agency>[A-Za-z][A-Za-z0-9_/-]{1,31})\s*(?::|>|-\s+)\s*(?P<label>[^\r\n]*)$"
)
_GENERATED_RE = re.compile(r"^\s*File\s+generated\s+at\s+(?P<time>[^\r\n]+?)\s*$", re.I)
_TABLE_HEADER_RE = re.compile(r"^\s*Tau\s+Date/Time\s+Latitude\s+Longitude\b", re.I)
_NOTES_RE = re.compile(r"^\s*Notes\s*:\s*$", re.I)
_POINT_RE = re.compile(
    r"^\s*"
    r"(?:(?:\(\s*\+\s*(?P<lead>\d{1,4})\s*H?\s*\))\s*)?"
    r"(?:(?P<valid>\d{6}Z)\s+)?"
    r"(?P<lat>[+-]?\d+(?:\.\d+)?)\s*(?P<lat_hemi>[NS])\s+"
    r"(?P<lon>[+-]?\d+(?:\.\d+)?)\s*(?P<lon_hemi>[EW])\s+"
    r"(?P<wind>---|\d+(?:\.\d+)?)\s*KT\s*$",
    re.I,
)
_TABLE_POINT_RE = re.compile(
    r"^\s*"
    r"(?P<lead>\d{3,4})\s+"
    r"(?P<date>\d{4}/\d{2}/\d{2})\s+(?P<time>\d{2}Z)\s+"
    r"(?P<lat>[+-]?\d+(?:\.\d+)?)\s*(?P<lat_hemi>[NS])\s+"
    r"(?P<lon>[+-]?\d+(?:\.\d+)?)\s*(?P<lon_hemi>[EW])\s+"
    r"(?P<category>.*?)\s+"
    r"(?P<wind_kmh>---|--|-|\d+(?:\.\d+)?)\s*km/h\s+"
    r"\(\s*(?P<wind_kt>---|--|-|\d+(?:\.\d+)?)\s*kt\s*\)\s+"
    r"(?P<pressure>---|--|-|\d+(?:\.\d+)?)\s*hPa\s*$",
    re.I,
)


AGENCY_LABELS: dict[str, str] = {
    "JMA": "日本氣象廳",
    "HKO": "香港天文台",
    "CWA": "中央氣象署",
    "CMA": "中國氣象局",
    "NMC": "中國氣象局",
    "CMA/NMC": "中國氣象局",
    "KMA": "韓國氣象廳",
    "SMG": "澳門氣象局",
    "NCHMF": "越南中央氣象水文中心",
    "TMD": "泰國氣象局",
    "PAGASA": "菲律賓氣象局",
    "JTWC": "聯合颱風警報中心",
}


def _signed_coordinate(value: str, hemisphere: str) -> float:
    number = abs(float(value))
    return -number if hemisphere.upper() in {"S", "W"} else number


def _optional_number(value: str | None) -> float | None:
    if value is None or re.fullmatch(r"-{1,3}", value.strip()):
        return None
    return float(value)


def _track_for_agency(
    agency: str,
    inline_label: str,
    by_agency: dict[str, dict[str, Any]],
    tracks: list[dict[str, Any]],
) -> dict[str, Any]:
    track = by_agency.get(agency)
    if track is not None:
        return track
    institution_name = inline_label or AGENCY_LABELS.get(agency, "")
    track = {
        "name": agency,
        "legend": f"{agency}／{institution_name}" if institution_name else agency,
        "institution_code": agency,
        "institution_name": institution_name,
        "source": "multi_agency",
        "readOnly": True,
        "points": [],
    }
    by_agency[agency] = track
    tracks.append(track)
    return track


def interpret_multi_track(raw: str) -> dict[str, Any]:
    """Decode a labelled multi-agency track text without changing its raw text."""

    original_raw = raw
    lines = raw.replace("\ufeff", "").splitlines()
    storm_name = ""
    issue_time = ""
    metadata: dict[str, str] = {}
    current_agency: str | None = None
    in_notes = False
    tracks: list[dict[str, Any]] = []
    by_agency: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or set(stripped) == {"="}:
            continue
        if not storm_name:
            title = _TITLE_RE.match(line)
            if title:
                storm_name = title.group("name").strip()
                continue
            plain_title = _PLAIN_TEXT_TITLE_RE.match(line)
            if plain_title:
                storm_name = plain_title.group("name").strip()
                details = plain_title.group("details") or ""
                international = re.search(r"International\s+No\.\s*:\s*([^;,]+)", details, re.I)
                jtwc = re.search(r"JTWC\s+No\.\s*:\s*([^;,]+)", details, re.I)
                if international:
                    metadata["international_number"] = international.group(1).strip()
                if jtwc:
                    metadata["jtwc_number"] = jtwc.group(1).strip()
                continue
        if not issue_time:
            issue = _ISSUE_RE.match(line)
            if issue:
                issue_time = issue.group("time").strip()
                continue
            generated = _GENERATED_RE.match(line)
            if generated:
                issue_time = generated.group("time").strip()
                metadata["generated_at"] = issue_time
                continue
        if in_notes:
            continue
        if _NOTES_RE.match(line):
            in_notes = True
            current_agency = None
            continue
        if _TABLE_HEADER_RE.match(line):
            continue
        section = _SECTION_RE.match(line)
        if section:
            agency = section.group("agency").upper()
            inline_label = section.group("label").strip()
            current_agency = agency
            in_notes = False
            _track_for_agency(agency, inline_label, by_agency, tracks)
            continue
        if current_agency is None:
            warnings.append(f"第 {line_number} 行在機構區段前，已保留但未解讀。")
            continue
        table_point = _TABLE_POINT_RE.match(line)
        if table_point:
            by_agency[current_agency]["points"].append(
                {
                    "hour": int(table_point.group("lead")),
                    "valid_time": f"{table_point.group('date')} {table_point.group('time')}",
                    "lat": _signed_coordinate(table_point.group("lat"), table_point.group("lat_hemi")),
                    "lon": _signed_coordinate(table_point.group("lon"), table_point.group("lon_hemi")),
                    "category": None if table_point.group("category").strip() == "---" else table_point.group("category").strip(),
                    "wind_kmh": _optional_number(table_point.group("wind_kmh")),
                    "wind_kt": _optional_number(table_point.group("wind_kt")),
                    "pressure_hpa": _optional_number(table_point.group("pressure")),
                }
            )
            continue
        point = _POINT_RE.match(line)
        if not point:
            warnings.append(f"第 {line_number} 行不符合多路徑座標格式，已保留但未解讀。")
            continue
        lead_text = point.group("lead")
        wind_text = point.group("wind")
        by_agency[current_agency]["points"].append(
            {
                "hour": int(lead_text) if lead_text is not None else 0,
                "valid_time": point.group("valid"),
                "lat": _signed_coordinate(point.group("lat"), point.group("lat_hemi")),
                "lon": _signed_coordinate(point.group("lon"), point.group("lon_hemi")),
                "wind_kt": None if wind_text == "---" else float(wind_text),
            }
        )

    for track in tracks:
        track["points"].sort(key=lambda item: item["hour"])

    if not tracks or not any(track["points"] for track in tracks):
        return {
            "supported": False,
            "format": "multi_agency_track",
            "reason": "找不到可繪製的多機構路徑。需使用機構名稱區段與時效、緯度、經度、風速格式。",
            "storm_name": storm_name,
            "issue_time": issue_time,
            "metadata": metadata,
            "tracks": [],
            "warnings": warnings,
            "original_raw": original_raw,
        }

    return {
        "supported": True,
        "format": "multi_agency_track",
        "storm_name": storm_name,
        "issue_time": issue_time,
        "metadata": metadata,
        "tracks": tracks,
        "warnings": warnings,
        "original_raw": original_raw,
    }
