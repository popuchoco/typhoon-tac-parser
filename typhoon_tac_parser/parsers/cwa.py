from __future__ import annotations

import re
from typing import Any

from ..models import Field, ParseResult
from ..normalization import normalize_tac, parse_heading
from .base import BaseParser


class CwaWarningParser(BaseParser):
    """Taiwan CWA/RCTP tropical cyclone warning parser."""

    def supports(self, normalized: str) -> bool:
        heading = parse_heading(normalized)
        return bool(heading and heading["ttaa"] == "WTCI" and heading["center"] == "RCTP")

    def parse(self, raw: str) -> dict[str, Any]:
        normalized = normalize_tac(raw)
        heading = parse_heading(normalized)
        text = re.sub(r"\s*=\s*", "\n", normalized)
        compact = re.sub(r"\s+", " ", text)
        result = ParseResult(
            family="cwa_tropical_cyclone_warning",
            raw=raw,
            normalized=normalized,
            heading=heading,
        )
        result.fields["source_profile"] = {
            "value": "CWA",
            "meaning": "Taiwan Central Weather Administration tropical cyclone warning",
            "confidence": "high",
        }
        result.fields["human_summary"] = self._summary(compact, heading)
        system = self._system(compact)
        if system:
            result.systems.append(system)
        result.forecasts = self._forecasts(compact)
        return result.to_dict()

    def _system(self, text: str) -> dict[str, Any] | None:
        identity_info = self._identity_info(text)
        identity = " / ".join(part for part in (identity_info.get("name"), identity_info.get("number")) if part)
        system = {"identity": identity or "UNKNOWN", "raw": text, "fields": {}}
        if identity_info.get("name"):
            system["fields"]["name"] = Field(identity_info["name"], identity_info["name"], meaning="storm name").to_dict()
        if identity_info.get("number"):
            system["fields"]["storm_number"] = Field(identity_info["number"], identity_info["number"], meaning="CWA tropical cyclone number").to_dict()
        if identity_info.get("classification"):
            system["fields"]["classification"] = Field(
                identity_info["classification"],
                self._translate_classification(identity_info["classification"]),
                meaning="current tropical cyclone classification",
            ).to_dict()
        position = self._position(text, r"POSITION\s+(?P<time>\d{6}Z).*?\(\s*(?P<lat>\d+(?:\.\d+)?)(?P<lat_h>[NS])\s*\).*?\(\s*(?P<lon>\d+(?:\.\d+)?)(?P<lon_h>[EW])\s*\)")
        if position:
            system["fields"]["position"] = position
        pressure = re.search(r"MIN SURFACE PRESSURE\s+(?P<value>\d{3,4})\s*HPA", text, re.I)
        if pressure:
            system["fields"]["pressure"] = Field(pressure.group(0), int(pressure.group("value")), "hpa", "minimum surface pressure").to_dict()
        wind = re.search(r"MAX SUSTAINED WINDS NEAR CENTER\s+(?P<wind>\d+)\s*METER PER SECOND\s+GUST\s+(?P<gust>\d+)\s*METER PER SECOND", text, re.I)
        if wind:
            system["fields"]["max_wind"] = Field(wind.group(0), int(wind.group("wind")), "m/s", "maximum sustained wind near center").to_dict()
            system["fields"]["gust"] = Field(wind.group(0), int(wind.group("gust")), "m/s", "gust near center").to_dict()
        radius = re.search(r"RADIUS OF OVER 15M/S WINDS\s+(?P<radius>\d+|-)\s*KM", text, re.I)
        if radius:
            value: Any = None if radius.group("radius") == "-" else int(radius.group("radius"))
            system["fields"]["radius_over_15ms"] = Field(radius.group(0), value, "km", "radius of winds over 15 m/s").to_dict()
        movement = re.search(r"MOVEMENT NEXT (?P<hours>\d+)HRS\s+(?P<body>.*?)(?=\s+MIN SURFACE PRESSURE|\s+MAX SUSTAINED|\s+RADIUS|\s+FORECAST POSITION|$)", text, re.I)
        if movement:
            value = self._movement_value(int(movement.group("hours")), movement.group("body"))
            system["fields"]["movement"] = Field(
                movement.group(0),
                value,
                "km/h",
                "forecast movement",
            ).to_dict()
        return system

    def _movement_value(self, hours: int, body: str) -> dict[str, Any]:
        tokens = re.findall(r"[A-Z]+|\d+\s*KM/HR", body.upper())
        value: dict[str, Any] = {"period_hours": hours}
        index = 0
        if index < len(tokens) and tokens[index] != "BECOMING":
            value["direction"] = tokens[index]
            index += 1
        if index < len(tokens) and tokens[index] == "BECOMING":
            index += 1
            if index < len(tokens) and re.match(r"^[A-Z]+$", tokens[index]):
                value["becoming_direction"] = tokens[index]
                index += 1
        if index < len(tokens) and re.match(r"\d+\s*KM/HR", tokens[index]):
            value["speed"] = int(re.match(r"\d+", tokens[index]).group(0))
            index += 1
        if index < len(tokens) and tokens[index] == "BECOMING":
            index += 1
            if index < len(tokens) and re.match(r"^[A-Z]+$", tokens[index]):
                value["becoming_direction"] = tokens[index]
                index += 1
            if index < len(tokens) and re.match(r"\d+\s*KM/HR", tokens[index]):
                value["becoming_speed"] = int(re.match(r"\d+", tokens[index]).group(0))
        return value

    def _forecasts(self, text: str) -> list[dict[str, Any]]:
        forecasts = []
        for match in re.finditer(r"(?P<hour>\d+)HRS VALID AT\s+(?P<time>\d{6}Z).*?\(\s*(?P<lat>\d+(?:\.\d+)?)(?P<lat_h>[NS])\s*\).*?\(\s*(?P<lon>\d+(?:\.\d+)?)(?P<lon_h>[EW])\s*\)", text, re.I):
            forecasts.append({
                "lead_time": Field(match.group("hour") + "HRS", int(match.group("hour")), "hour", "forecast lead time").to_dict(),
                "valid_time": Field(match.group("time"), match.group("time"), meaning="forecast valid time").to_dict(),
                "position": self._coord_field(match),
                "raw": match.group(0),
            })
        for match in re.finditer(r"(?P<hour>\d+)HRS VALID AT\s+(?P<time>\d{6}Z)\s+(?P<status>Extratropical Low|Tropical Depression|Tropical Storm|Typhoon)", text, re.I):
            forecasts.append({
                "lead_time": Field(match.group("hour") + "HRS", int(match.group("hour")), "hour", "forecast lead time").to_dict(),
                "valid_time": Field(match.group("time"), match.group("time"), meaning="forecast valid time").to_dict(),
                "status": Field(match.group("status"), match.group("status"), meaning="forecast system type").to_dict(),
                "raw": match.group(0),
            })
        forecasts.sort(key=lambda item: item["lead_time"]["value"])
        return forecasts

    def _position(self, text: str, pattern: str) -> dict[str, Any] | None:
        match = re.search(pattern, text, re.I)
        if not match:
            return None
        return self._coord_field(match)

    def _coord_field(self, match: re.Match[str]) -> dict[str, Any]:
        lat = float(match.group("lat"))
        lon = float(match.group("lon"))
        if match.group("lat_h").upper() == "S":
            lat *= -1
        if match.group("lon_h").upper() == "W":
            lon *= -1
        return Field(match.group(0), {"lat": lat, "lon": lon}, "degree", "storm center position").to_dict()

    def _identity(self, text: str) -> str:
        return self._identity_info(text).get("name", "")

    def _identity_info(self, text: str) -> dict[str, str]:
        paren = re.search(
            r"(?P<classification>TYPHOON|TROPICAL\s+STORM|TROPICAL\s+DEPRESSION)\s+(?P<number>\d{6})\s+\(\s*(?P<name>[A-Z][A-Z0-9-]+)\s+(?P<paren_number>\d{6})\s*\)\s+WARNING",
            text,
            re.I,
        )
        if paren:
            return {
                "name": paren.group("name").upper(),
                "number": paren.group("paren_number") or paren.group("number"),
                "classification": re.sub(r"\s+", " ", paren.group("classification").upper()),
            }
        named = re.search(
            r"(?P<classification>TYPHOON|TROPICAL\s+STORM|TROPICAL\s+DEPRESSION).*?\b(?P<name>[A-Z][A-Z0-9-]+)\s+(?P<number>\d{6})\s+WARNING",
            text,
            re.I,
        )
        if named:
            return {
                "name": named.group("name").upper(),
                "number": named.group("number"),
                "classification": re.sub(r"\s+", " ", named.group("classification").upper()),
            }
        number_only = re.search(r"\b(?P<classification>TYPHOON|TROPICAL\s+STORM|TROPICAL\s+DEPRESSION)\s+(?P<number>\d{6})\s+WARNING", text, re.I)
        if number_only:
            return {
                "name": "",
                "number": number_only.group("number"),
                "classification": re.sub(r"\s+", " ", number_only.group("classification").upper()),
            }
        return {}

    def _translate_classification(self, text: str) -> str:
        mapping = {
            "TYPHOON": "颱風",
            "TROPICAL STORM": "熱帶風暴",
            "TROPICAL DEPRESSION": "熱帶低壓",
        }
        return mapping.get(re.sub(r"\s+", " ", text.upper()), text)

    def _summary(self, text: str, heading: dict[str, Any] | None) -> str:
        issue = heading.get("issue_time", {}).get("raw", "") if heading else ""
        valid = re.search(r"WARNING VALID\s+(\d{6}Z)", text, re.I)
        identity_info = self._identity_info(text)
        identity = " / ".join(part for part in (identity_info.get("name"), identity_info.get("number")) if part) or "the system"
        classification = self._translate_classification(identity_info.get("classification", ""))
        system = self._system(text)
        fields = system.get("fields", {}) if system else {}
        details = []
        if fields.get("position", {}).get("value"):
            pos = fields["position"]["value"]
            details.append(f"中心位於北緯 {pos['lat']} 度、東經 {pos['lon']} 度")
        if fields.get("pressure", {}).get("value") is not None:
            details.append(f"中心最低氣壓 {fields['pressure']['value']} hPa")
        if fields.get("max_wind", {}).get("value") is not None:
            wind = f"近中心最大持續風 {fields['max_wind']['value']} m/s"
            if fields.get("gust", {}).get("value") is not None:
                wind += f"，陣風 {fields['gust']['value']} m/s"
            details.append(wind)
        if fields.get("movement", {}).get("value"):
            details.append(f"移動：{self._movement_text(fields['movement'])}")
        if fields.get("radius_over_15ms", {}).get("value") is not None:
            details.append(f"15 m/s 以上風半徑 {fields['radius_over_15ms']['value']} km")
        forecasts = self._forecasts(text)
        forecast_parts = []
        for item in forecasts[:4]:
            lead = item["lead_time"]["value"]
            valid_time = item["valid_time"]["value"]
            if item.get("position", {}).get("value"):
                pos = item["position"]["value"]
                forecast_parts.append(f"{lead} 小時後({valid_time})位於北緯 {pos['lat']} 度、東經 {pos['lon']} 度")
            elif item.get("status", {}).get("value"):
                forecast_parts.append(f"{lead} 小時後({valid_time})為{self._translate_classification(item['status']['value'])}")
        return "\n".join(filter(None, [
            f"中央氣象署/RCTP 於 {issue}Z 發布 WTCI 熱帶氣旋警報。",
            f"警報有效至 {valid.group(1)}。" if valid else "",
            f"系統：{identity}。" if not classification else f"系統：{classification} {identity}。",
            "；".join(details) + "。" if details else "",
            "預報：" + "；".join(forecast_parts) + "。" if forecast_parts else "",
        ]))

    def _movement_text(self, field: dict[str, Any]) -> str:
        value = field.get("value", {})
        direction = self._translate_direction(value.get("direction", ""))
        text = f"未來 {value.get('period_hours')} 小時向{direction}移動，速度 {value.get('speed')} km/h"
        if value.get("becoming_direction"):
            text += f"，之後轉向{self._translate_direction(value['becoming_direction'])}"
        if value.get("becoming_speed"):
            text += f"，之後速度 {value['becoming_speed']} km/h"
        return text

    def _translate_direction(self, text: str) -> str:
        mapping = {
            "N": "北",
            "NNE": "北北東",
            "NE": "東北",
            "ENE": "東北東",
            "E": "東",
            "ESE": "東南東",
            "SE": "東南",
            "SSE": "南南東",
            "S": "南",
            "SSW": "南南西",
            "SW": "西南",
            "WSW": "西南西",
            "W": "西",
            "WNW": "西北西",
            "NW": "西北",
            "NNW": "北北西",
        }
        return mapping.get(str(text).upper(), text)
