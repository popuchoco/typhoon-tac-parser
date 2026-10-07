"""Normalize allow-listed TAC reports for side-by-side center comparison."""

from __future__ import annotations

import math
import re
from typing import Any

from .allowed_reports import interpret_allowed_report


MAX_COMPARISON_REPORTS = 20
_LEAD_RE = re.compile(r"(?P<hours>\d{1,4})\s*H", re.I)
_WIND_TO_KT = {
    "kt": 1.0,
    "kts": 1.0,
    "knot": 1.0,
    "knots": 1.0,
    "m/s": 1.9438444924406,
    "ms-1": 1.9438444924406,
    "km/h": 1 / 1.852,
    "kmh": 1 / 1.852,
}


def _value(field: Any) -> Any:
    if isinstance(field, dict) and "value" in field:
        return field["value"]
    return field


def _number(field: Any) -> float | None:
    value = _value(field)
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _position(field: Any) -> dict[str, float] | None:
    value = _value(field)
    if not isinstance(value, dict):
        return None
    lat = _number(value.get("lat"))
    lon = _number(value.get("lon"))
    if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 360:
        return None
    return {"lat": lat, "lon": lon}


def _wind_kt(field: Any) -> float | None:
    number = _number(field)
    if number is None or not isinstance(field, dict):
        return None
    unit = str(field.get("unit") or "").strip().lower().replace(" ", "")
    factor = _WIND_TO_KT.get(unit)
    if factor is None:
        return None
    return round(number * factor, 1)


def _lead_hours(field: Any) -> float | None:
    value = _number(field)
    if value is not None:
        return value
    raw = field.get("raw") if isinstance(field, dict) else field
    match = _LEAD_RE.search(str(raw or ""))
    return float(match.group("hours")) if match else None


def _metric(fields: dict[str, Any], *keys: str) -> Any:
    return next((fields[key] for key in keys if fields.get(key) is not None), None)


def _entry(
    fields: dict[str, Any],
    *,
    column_id: str,
    column_label: str,
    center: str,
    agency: str,
    identity: str,
    report_label: str,
    issue_time: str,
    lead_time_hours: float | None = None,
    valid_time: str = "",
) -> dict[str, Any]:
    wind = _metric(fields, "max_wind", "maximum_wind", "wind_speed")
    pressure = _metric(fields, "pressure", "central_pressure", "minimum_pressure")
    movement = _metric(fields, "movement", "motion")
    return {
        "column_id": column_id,
        "column_label": column_label,
        "center": center,
        "agency": agency,
        "identity": identity,
        "report_label": report_label,
        "issue_time": issue_time,
        "lead_time_hours": lead_time_hours,
        "valid_time": str(_value(valid_time) or "") if valid_time else "",
        "position": _position(fields.get("position")),
        "max_wind_raw": str(wind.get("raw", "")) if isinstance(wind, dict) else "",
        "max_wind_value": _number(wind),
        "max_wind_unit": str(wind.get("unit", "")) if isinstance(wind, dict) else "",
        "max_wind_kt": _wind_kt(wind),
        "pressure_hpa": _number(pressure),
        "movement": _value(movement),
    }


def compare_center_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Parse two or more allow-listed reports and align forecast points by lead hour.

    The comparison preserves report identity and does not attempt to decide
    whether differently named storms are the same system. Wind values are
    normalized to knots only when a recognized source unit is provided.
    """

    if not isinstance(reports, list) or len(reports) < 2:
        raise ValueError("至少要提供兩份報文，才能進行多中心比較。")
    if len(reports) > MAX_COMPARISON_REPORTS:
        raise ValueError(f"單次最多比較 {MAX_COMPARISON_REPORTS} 份報文。")

    parsed_reports: list[dict[str, Any]] = []
    current_rows: list[dict[str, Any]] = []
    forecast_groups: dict[float | None, list[dict[str, Any]]] = {}
    map_tracks: list[dict[str, Any]] = []
    warnings: list[str] = []

    for report_index, item in enumerate(reports):
        if not isinstance(item, dict):
            raise ValueError(f"第 {report_index + 1} 份報文必須是物件。")
        raw = item.get("raw")
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f"第 {report_index + 1} 份報文必須包含非空 raw 字串。")
        label = item.get("label")
        label = label.strip() if isinstance(label, str) and label.strip() else f"第 {report_index + 1} 份報文"

        try:
            interpreted = interpret_allowed_report(raw)
        except Exception as exc:
            parsed_reports.append({"label": label, "supported": False, "reason": f"解析失敗：{exc}"})
            warnings.append(f"{label}：解析失敗。")
            continue

        if not interpreted.get("supported"):
            parsed_reports.append({
                "label": label,
                "supported": False,
                "reason": interpreted.get("reason", "不支援此報文。"),
                "heading": interpreted.get("heading"),
            })
            warnings.append(f"{label}：報文不在支援白名單，未納入比較。")
            continue

        parsed = interpreted.get("parsed") or {}
        profile = interpreted.get("profile") or {}
        heading = parsed.get("heading") or interpreted.get("heading") or {}
        center = str(profile.get("center") or heading.get("center") or "").upper()
        agency = str(parsed.get("issuing_agency") or profile.get("label") or center)
        issue_info = heading.get("issue_time") or {}
        issue_time = str(issue_info.get("raw") or "")
        systems = parsed.get("systems") or []
        if not systems:
            root_fields = parsed.get("fields") or {}
            systems = [{"identity": center or "未命名系統", "fields": root_fields}]

        report_output = {
            "label": label,
            "supported": True,
            "center": center,
            "agency": agency,
            "issue_time": issue_time,
            "storms": [],
        }
        report_id = f"r{report_index}"
        forecast_source = parsed.get("forecasts") or []

        for system_index, system in enumerate(systems):
            fields = system.get("fields") or {}
            identity = str(system.get("identity") or system.get("name") or center or "未命名系統")
            column_id = f"{report_id}s{system_index}"
            column_label = f"{center}／{identity}" if identity != center else center
            current = _entry(
                fields,
                column_id=column_id,
                column_label=column_label,
                center=center,
                agency=agency,
                identity=identity,
                report_label=label,
                issue_time=issue_time,
            )
            current_rows.append(current)
            report_output["storms"].append({
                "identity": identity,
                "position": current["position"],
                "max_wind_kt": current["max_wind_kt"],
                "max_wind_value": current["max_wind_value"],
                "max_wind_unit": current["max_wind_unit"],
                "pressure_hpa": current["pressure_hpa"],
            })

            points: list[dict[str, Any]] = []
            if current["position"]:
                points.append({"hour": 0, **current["position"], "kind": "initial"})
            if len(systems) == 1:
                for forecast_index, forecast in enumerate(forecast_source):
                    lead = _lead_hours(forecast.get("lead_time"))
                    position = _position(forecast.get("position"))
                    if not position:
                        continue
                    points.append({
                        "hour": lead if lead is not None else float(forecast_index + 1),
                        **position,
                        "kind": "forecast",
                    })
                    row = _entry(
                        forecast,
                        column_id=column_id,
                        column_label=column_label,
                        center=center,
                        agency=agency,
                        identity=identity,
                        report_label=label,
                        issue_time=issue_time,
                        lead_time_hours=lead,
                        valid_time=forecast.get("valid_time", ""),
                    )
                    forecast_groups.setdefault(lead, []).append(row)
            if points:
                map_tracks.append({
                    "name": column_label,
                    "legend": center or column_label,
                    "source": "center-comparison",
                    "readOnly": True,
                    "points": points,
                })

        parsed_reports.append(report_output)
        for warning in parsed.get("warnings", []) or []:
            warnings.append(f"{label}：{warning}")

    known_centers = [item.get("center") for item in parsed_reports if item.get("supported") and item.get("center")]
    if len(set(known_centers)) < 2:
        warnings.append("有效報文不足兩個不同中心；請確認輸入來源。")

    groups = [
        {"lead_time_hours": lead, "entries": entries}
        for lead, entries in sorted(
            forecast_groups.items(),
            key=lambda pair: (pair[0] is None, pair[0] if pair[0] is not None else float("inf")),
        )
    ]
    supported_count = sum(bool(report.get("supported")) for report in parsed_reports)
    return {
        "format": "multi_center_tac_comparison",
        "supported_report_count": supported_count,
        "reports": parsed_reports,
        "current_comparison": current_rows,
        "forecast_comparison": groups,
        "map_tracks": map_tracks,
        "warnings": warnings,
        "note": "風速只在來源單位可辨識時換算為 kt；預報以各報文時效對齊，發報時間可能不同。風暴名稱或編號保留來源寫法，不自動判定跨中心身分。",
    }
