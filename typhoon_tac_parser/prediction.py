"""A small, transparent, manual-input track forecast model.

This is a Python-first heuristic inspired by the archived DoraBoy inputs:
inertia, steering highs, the southern edge of the westerlies, and nearby
systems.  It is intentionally not presented as an official forecast model.
"""

from __future__ import annotations

import math
from typing import Any


EARTH_KM_PER_DEGREE = 111.2
KT_TO_KMH = 1.852

# The archived DoraBoy documentation reports these route-error reference
# values.  They are used only as a transparent uncertainty overlay.
ERROR_REFERENCE_KM = {
    12: 104,
    24: 207,
    48: 406,
    72: 633,
    120: 856,
    168: 964,
    240: 2711,
}


def _number(payload: dict[str, Any], key: str, default: float | None = None) -> float | None:
    value = payload.get(key, default)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} 必須是數字。") from exc


def _required(payload: dict[str, Any], key: str) -> float:
    value = _number(payload, key)
    if value is None:
        raise ValueError(f"缺少必要欄位：{key}。")
    return value


def _validate_lat_lon(lat: float, lon: float, label: str) -> None:
    if not -90 <= lat <= 90:
        raise ValueError(f"{label} 緯度必須介於 -90 到 90。")
    if not -180 <= lon <= 180:
        raise ValueError(f"{label} 經度必須介於 -180 到 180。")


def _east_north_km(origin: tuple[float, float], target: tuple[float, float]) -> tuple[float, float]:
    lat, lon = origin
    target_lat, target_lon = target
    mean_lat = math.radians((lat + target_lat) / 2)
    east = (target_lon - lon) * EARTH_KM_PER_DEGREE * max(math.cos(mean_lat), 0.15)
    north = (target_lat - lat) * EARTH_KM_PER_DEGREE
    return east, north


def _destination(origin: tuple[float, float], east_km: float, north_km: float) -> tuple[float, float]:
    lat, lon = origin
    new_lat = lat + north_km / EARTH_KM_PER_DEGREE
    mean_lat = math.radians((lat + new_lat) / 2)
    new_lon = lon + east_km / (EARTH_KM_PER_DEGREE * max(math.cos(mean_lat), 0.15))
    return new_lat, new_lon


def _uncertainty_km(hours: int) -> float:
    points = sorted(ERROR_REFERENCE_KM.items())
    if hours <= points[0][0]:
        return float(points[0][1]) * max(hours, 1) / points[0][0]
    for (left_h, left_v), (right_h, right_v) in zip(points, points[1:]):
        if hours <= right_h:
            ratio = (hours - left_h) / (right_h - left_h)
            return round(left_v + ratio * (right_v - left_v), 1)
    return float(points[-1][1])


def _previous_motion(payload: dict[str, Any], current: tuple[float, float]) -> tuple[float, float]:
    previous_lat = _number(payload, "previous_lat")
    previous_lon = _number(payload, "previous_lon")
    interval = _number(payload, "previous_interval_hours", 6)
    if previous_lat is not None and previous_lon is not None:
        _validate_lat_lon(previous_lat, previous_lon, "前一位置")
        if interval is None or interval <= 0:
            raise ValueError("previous_interval_hours 必須大於 0。")
        east, north = _east_north_km((previous_lat, previous_lon), current)
        return east / interval, north / interval

    direction = str(payload.get("initial_direction", "")).strip().upper()
    speed_kt = _number(payload, "initial_speed_kt", 0) or 0
    direction_angles = {
        "N": 0,
        "NNE": 22.5,
        "NE": 45,
        "ENE": 67.5,
        "E": 90,
        "ESE": 112.5,
        "SE": 135,
        "SSE": 157.5,
        "S": 180,
        "SSW": 202.5,
        "SW": 225,
        "WSW": 247.5,
        "W": 270,
        "WNW": 292.5,
        "NW": 315,
        "NNW": 337.5,
    }
    if direction not in direction_angles or speed_kt <= 0:
        return 0.0, 0.0
    angle = math.radians(direction_angles[direction])
    speed_kmh = speed_kt * KT_TO_KMH
    return math.sin(angle) * speed_kmh, math.cos(angle) * speed_kmh


def _steering_from_highs(
    position: tuple[float, float], highs: list[dict[str, Any]],
) -> tuple[float, float]:
    east_total = north_total = 0.0
    for high in highs:
        lat = _number(high, "lat")
        lon = _number(high, "lon")
        radius = _number(high, "radius_km", 700)
        speed = _number(high, "steering_speed_kt", 12)
        if None in (lat, lon, radius, speed) or radius <= 0:
            continue
        target = (float(lat), float(lon))
        east, north = _east_north_km(target, position)
        distance = math.hypot(east, north)
        if distance == 0 or distance > radius:
            continue
        # Northern-hemisphere clockwise tangent around a high pressure center.
        weight = max(0.0, 1.0 - distance / radius)
        magnitude = float(speed) * KT_TO_KMH * weight
        east_total += (north / distance) * magnitude
        north_total += (-east / distance) * magnitude
    return east_total, north_total


def _steering_from_nearby_systems(
    position: tuple[float, float], systems: list[dict[str, Any]],
) -> tuple[float, float]:
    east_total = north_total = 0.0
    for system in systems:
        lat = _number(system, "lat")
        lon = _number(system, "lon")
        strength = _number(system, "interaction_speed_kt", 8)
        radius = _number(system, "interaction_radius_km", 800)
        if None in (lat, lon, strength, radius) or radius <= 0:
            continue
        east, north = _east_north_km(position, (float(lat), float(lon)))
        distance = math.hypot(east, north)
        if distance == 0 or distance > radius:
            continue
        # A weak tangential interaction keeps the effect bounded and visible.
        weight = (1.0 - distance / radius) ** 2
        magnitude = float(strength) * KT_TO_KMH * weight
        east_total += (-north / distance) * magnitude
        north_total += (east / distance) * magnitude
    return east_total, north_total


def forecast_track(payload: dict[str, Any]) -> dict[str, Any]:
    current = (_required(payload, "current_lat"), _required(payload, "current_lon"))
    _validate_lat_lon(*current, "目前位置")
    inertia = _number(payload, "inertia", 0.65)
    step_hours = int(_number(payload, "step_hours", 6) or 6)
    horizon_hours = int(_number(payload, "horizon_hours", 240) or 240)
    westerly_south_lat = _number(payload, "westerly_south_lat", 20)
    westerly_speed_kt = _number(payload, "westerly_speed_kt", 12)
    if inertia is None or not 0 <= inertia <= 1:
        raise ValueError("inertia 必須介於 0 到 1。")
    if step_hours <= 0 or horizon_hours <= 0 or horizon_hours > 240 * 7:
        raise ValueError("step_hours 與 horizon_hours 必須為合理的正數。")

    highs = payload.get("highs") or []
    nearby_systems = payload.get("nearby_systems") or []
    motion_east, motion_north = _previous_motion(payload, current)
    points: list[dict[str, Any]] = [{
        "hour": 0,
        "lat": round(current[0], 3),
        "lon": round(current[1], 3),
        "uncertainty_km": 0,
        "kind": "initial",
    }]

    position = current
    for hour in range(step_hours, horizon_hours + 1, step_hours):
        high_east, high_north = _steering_from_highs(position, highs)
        nearby_east, nearby_north = _steering_from_nearby_systems(position, nearby_systems)
        env_east = high_east + nearby_east
        env_north = high_north + nearby_north
        if westerly_south_lat is not None and position[0] >= westerly_south_lat:
            env_east += (westerly_speed_kt or 0) * KT_TO_KMH

        if env_east == 0 and env_north == 0 and motion_east == 0 and motion_north == 0:
            # No manually supplied motion or steering field: remain stationary
            # rather than silently inventing a direction.
            pass
        else:
            motion_east = inertia * motion_east + (1 - inertia) * env_east
            motion_north = inertia * motion_north + (1 - inertia) * env_north
            position = _destination(position, motion_east * step_hours, motion_north * step_hours)
        points.append({
            "hour": hour,
            "lat": round(position[0], 3),
            "lon": round(position[1], 3),
            "uncertainty_km": _uncertainty_km(hour),
            "kind": "forecast",
        })

    return {
        "model": "manual_steering_heuristic_v1",
        "note": "僅供使用者研究與繪圖，不是官方預報，也不會自動讀取或修改報文。",
        "inputs": payload,
        "points": points,
    }
