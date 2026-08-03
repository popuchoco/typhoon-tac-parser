from __future__ import annotations

import re
from typing import Any

from ..models import Field, ParseResult
from ..icao_locations import lookup_icao_location
from ..normalization import normalize_tac
from .base import BaseParser


class MetarParser(BaseParser):
    """METAR/SPECI aviation routine weather report parser."""

    def supports(self, normalized: str) -> bool:
        return bool(re.match(r"^(METAR|SPECI)\s+[A-Z]{4}\s+\d{6}Z?\b", normalized.strip(), re.I))

    def parse(self, raw: str) -> dict[str, Any]:
        normalized = normalize_tac(raw).rstrip("=")
        tokens = normalized.split()
        kind = tokens[0].upper() if tokens else "METAR"
        result = ParseResult(family="metar", raw=raw, normalized=normalized, heading=None)
        result.fields["report_type"] = Field(kind, kind, meaning="aviation weather report type").to_dict()
        station_code = tokens[1].upper()
        location = lookup_icao_location(station_code)
        result.fields["station"] = Field(
            station_code,
            {
                "code": station_code,
                "name_zh": location.get("name_zh", "") if location else "",
                "name_en": location.get("name_en", "") if location else "",
                "state": location.get("state", "") if location else "",
            },
            meaning="ICAO station location indicator",
            confidence="high" if location else "medium",
        ).to_dict()
        result.fields["issue_time"] = self._time(tokens[2])
        fields, remarks = self._parse_tokens(tokens[3:])
        result.fields.update(fields)
        if remarks:
            result.remarks.append(remarks)
            result.fields["remarks"] = Field(remarks, remarks, meaning="remarks").to_dict()
        result.fields["human_summary"] = self._summary(result.fields)
        return result.to_dict()

    def _parse_tokens(self, tokens: list[str]) -> tuple[dict[str, Any], str]:
        fields: dict[str, Any] = {}
        clouds: list[dict[str, Any]] = []
        remarks: list[str] = []
        in_remarks = False
        for token in tokens:
            upper = token.upper().rstrip("=")
            if upper == "RMK":
                in_remarks = True
                continue
            if in_remarks:
                remarks.append(upper)
                continue
            wind = re.match(r"(?P<dir>\d{3}|VRB)(?P<speed>\d{2,3})(G(?P<gust>\d{2,3}))?(?P<unit>KT|MPS|KMH)$", upper)
            if wind:
                value: dict[str, Any] = {
                    "direction": wind.group("dir"),
                    "speed": int(wind.group("speed")),
                }
                if wind.group("gust"):
                    value["gust"] = int(wind.group("gust"))
                fields["wind"] = Field(upper, value, self._wind_unit(wind.group("unit")), "surface wind").to_dict()
                continue
            if re.match(r"^\d{4}$", upper) or upper in {"CAVOK"}:
                fields["visibility"] = Field(upper, self._visibility_value(upper), "m", "prevailing visibility").to_dict()
                continue
            cloud = re.match(r"(?P<amount>FEW|SCT|BKN|OVC|NSC|NCD)(?P<height>\d{3})?(?P<type>CB|TCU)?$", upper)
            if cloud:
                clouds.append(Field(upper, {
                    "amount": cloud.group("amount"),
                    "height_ft": int(cloud.group("height")) * 100 if cloud.group("height") else None,
                    "type": cloud.group("type") or "",
                }, meaning="cloud layer").to_dict())
                continue
            temp = re.match(r"(?P<t>M?\d{2})/(?P<td>M?\d{2})$", upper)
            if temp:
                fields["temperature_dewpoint"] = Field(
                    upper,
                    {"temperature_c": self._signed_temp(temp.group("t")), "dewpoint_c": self._signed_temp(temp.group("td"))},
                    "degC",
                    "air temperature and dew point",
                ).to_dict()
                continue
            qnh = re.match(r"Q(?P<value>\d{4})$", upper)
            if qnh:
                fields["qnh"] = Field(upper, int(qnh.group("value")), "hpa", "QNH altimeter setting").to_dict()
                continue
            if upper == "NOSIG":
                fields["trend"] = Field(upper, "NOSIG", meaning="no significant change expected").to_dict()
                continue
        if clouds:
            fields["clouds"] = clouds
        return fields, " ".join(remarks)

    def _summary(self, fields: dict[str, Any]) -> str:
        parts = [
            f"{self._station_text(fields['station'])} 於 {fields['issue_time']['raw']} 發布 METAR 例行航空天氣報告。"
        ]
        if fields.get("wind"):
            wind = fields["wind"]
            value = wind["value"]
            direction = "不定向" if value["direction"] == "VRB" else f"{value['direction']} 度"
            gust = f"，陣風 {value['gust']} {wind['unit']}" if value.get("gust") else ""
            parts.append(f"地面風向 {direction}，風速 {value['speed']} {wind['unit']}{gust}。")
        if fields.get("visibility"):
            visibility = fields["visibility"]["value"]
            parts.append("能見度 10 公里以上。" if visibility == 9999 else f"能見度 {visibility} 公尺。")
        if fields.get("clouds"):
            parts.append("雲況：" + "；".join(self._cloud_text(item) for item in fields["clouds"]) + "。")
        if fields.get("temperature_dewpoint"):
            value = fields["temperature_dewpoint"]["value"]
            parts.append(f"氣溫 {value['temperature_c']} 度，露點 {value['dewpoint_c']} 度。")
        if fields.get("qnh"):
            parts.append(f"QNH {fields['qnh']['value']} hPa。")
        if fields.get("trend"):
            parts.append("趨勢預報：無顯著變化。")
        if fields.get("remarks"):
            parts.append(f"備註：{self._remarks_text(fields['remarks']['value'])}")
        return "\n".join(parts)

    def _time(self, token: str) -> dict[str, Any]:
        match = re.match(r"(?P<day>\d{2})(?P<hour>\d{2})(?P<minute>\d{2})Z?", token)
        value = {
            "day": int(match.group("day")),
            "hour": int(match.group("hour")),
            "minute": int(match.group("minute")),
            "timezone": "UTC",
        } if match else token
        return Field(token, value, meaning="observation time").to_dict()

    def _visibility_value(self, token: str) -> int:
        return 9999 if token == "CAVOK" else int(token)

    def _signed_temp(self, token: str) -> int:
        return -int(token[1:]) if token.startswith("M") else int(token)

    def _wind_unit(self, unit: str) -> str:
        return {"KT": "kt", "MPS": "m/s", "KMH": "km/h"}.get(unit.upper(), unit.lower())

    def _cloud_text(self, field: dict[str, Any]) -> str:
        amount = {
            "FEW": "少雲",
            "SCT": "疏雲",
            "BKN": "裂雲",
            "OVC": "陰天",
            "NSC": "無重要雲",
            "NCD": "未偵測到雲",
        }.get(field["value"]["amount"], field["value"]["amount"])
        height = field["value"].get("height_ft")
        kind = f" {field['value']['type']}" if field["value"].get("type") else ""
        return f"{amount}{kind}，雲底 {height} ft" if height else amount

    def _station_text(self, field: dict[str, Any]) -> str:
        value = field.get("value", {})
        if isinstance(value, dict) and value.get("name_zh"):
            return f"{value['name_zh']}({value['code']})"
        if isinstance(value, dict):
            return value.get("code", field.get("raw", ""))
        return str(value or field.get("raw", ""))

    def _remarks_text(self, text: str) -> str:
        translated = text
        translated = re.sub(r"\bA(?P<value>\d{4})\b", lambda m: f"美制高度表撥定 {int(m.group('value')) / 100:.2f} inHg", translated)
        return translated + "。"
