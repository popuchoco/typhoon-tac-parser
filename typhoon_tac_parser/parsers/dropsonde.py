from __future__ import annotations

import re
from typing import Any

from ..centers import issuing_agency
from ..models import Field, ParseResult
from ..normalization import normalize_tac, parse_heading
from .base import BaseParser


GROUP_RE = re.compile(r"^[\d/]{5}$")


class DropsondeParser(BaseParser):
    """TEMP DROP / XXAA + XXBB upper-air dropsonde TAC parser."""

    LEVEL_PRESSURES = {
        "99": "surface/sea level",
        "00": "1000 hPa",
        "92": "925 hPa",
        "85": "850 hPa",
        "70": "700 hPa",
        "50": "500 hPa",
        "40": "400 hPa",
        "30": "300 hPa",
        "25": "250 hPa",
        "20": "200 hPa",
        "15": "150 hPa",
        "10": "100 hPa",
    }

    MARKERS = {
        "88999": "mandatory-level section end marker",
        "77999": "mandatory-level section end marker",
        "31313": "regional/additional data marker",
        "41414": "cloud data marker",
        "51515": "national data marker",
        "21212": "significant wind section marker",
        "61616": "supplemental data marker",
        "62626": "mission supplemental data marker",
    }

    def supports(self, normalized: str) -> bool:
        heading = parse_heading(normalized)
        has_temp_drop_section = bool(re.search(r"\bXX(?:AA|BB)\b", normalized))
        has_drop_heading = bool(heading and heading["ttaa"].startswith("UZ") and has_temp_drop_section)
        starts_with_temp = bool(re.match(r"^\s*XX(?:AA|BB)\b", normalized))
        return has_drop_heading or starts_with_temp

    def parse(self, raw: str) -> dict[str, Any]:
        normalized = normalize_tac(raw).rstrip("=")
        heading = parse_heading(normalized)
        result = ParseResult(family="dropsonde_temp_drop", raw=raw, normalized=normalized, heading=heading)
        center = heading.get("center") if heading else ""
        body = self._body_without_heading(normalized, heading)
        sections = self._sections(body.split())
        fields = self._fields(sections)
        result.fields.update(fields)
        if center:
            result.fields["source_profile"] = {
                "value": center,
                "meaning": issuing_agency(center) or center,
                "confidence": "high" if issuing_agency(center) else "medium",
            }
        result.fields["human_summary"] = self._summary(heading, fields)
        result.systems = [{"identity": "TEMP DROP XXAA/XXBB", "raw": normalized, "fields": fields}]
        return result.to_dict()

    def _body_without_heading(self, normalized: str, heading: dict[str, Any] | None) -> str:
        if heading and normalized.startswith(heading["raw"]):
            return normalized[len(heading["raw"]) :].strip()
        return normalized

    def _sections(self, tokens: list[str]) -> dict[str, list[str]]:
        sections: dict[str, list[str]] = {}
        current = ""
        for token in tokens:
            token = token.rstrip("=")
            if token in {"XXAA", "XXBB"}:
                current = token
                sections[current] = []
                continue
            if current:
                sections[current].append(token)
        return sections

    def _fields(self, sections: dict[str, list[str]]) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        xxaa = sections.get("XXAA", [])
        xxbb = sections.get("XXBB", [])
        header_tokens = xxaa or xxbb
        if header_tokens:
            fields["xxaa_header"] = Field(header_tokens[0], self._part_header(header_tokens[0]), meaning="TEMP DROP section header").to_dict()
        if len(header_tokens) >= 3:
            lat = self._coord_lat(header_tokens[1])
            lon = self._coord_lon(header_tokens[2])
            fields["position"] = Field(f"{header_tokens[1]} {header_tokens[2]}", {"lat": lat, "lon": lon}, "degree", "dropsonde position").to_dict()
        if len(header_tokens) >= 4:
            fields["marsden_square"] = Field(header_tokens[3], header_tokens[3], meaning="Marsden square or region identifier").to_dict()
        if xxaa:
            fields["mandatory_levels"] = self._mandatory_levels(xxaa[4:])
        if xxbb:
            fields.update(self._xxbb_fields(xxbb[4:]))
        supplemental = self._unique([*self._supplemental_text(xxaa[4:]), *self._supplemental_text(xxbb[4:])])
        if supplemental:
            fields["supplemental"] = Field(" ".join(supplemental), supplemental, meaning="dropsonde supplemental text groups").to_dict()
            reports = self._supplemental_reports(supplemental)
            if reports:
                fields["supplemental_reports"] = Field(" ".join(item["raw"] for item in reports), reports, meaning="decoded dropsonde supplemental groups").to_dict()
        return fields

    def _mandatory_levels(self, tokens: list[str]) -> list[dict[str, Any]]:
        rows = []
        index = 0
        while index < len(tokens):
            group = tokens[index]
            if group in self.MARKERS:
                rows.append(Field(group, {"marker": self.MARKERS[group]}, meaning="TEMP marker group").to_dict())
                index += 1
                continue
            if not GROUP_RE.match(group) or group[:2] not in self.LEVEL_PRESSURES:
                index += 1
                continue
            temp_group = tokens[index + 1] if index + 1 < len(tokens) and GROUP_RE.match(tokens[index + 1]) else ""
            wind_group = tokens[index + 2] if index + 2 < len(tokens) and GROUP_RE.match(tokens[index + 2]) else ""
            rows.append(Field(" ".join(part for part in (group, temp_group, wind_group) if part), {
                "pressure": self.LEVEL_PRESSURES[group[:2]],
                "height_group": group,
                "temperature_group": temp_group,
                "temperature_c": self._temperature(temp_group),
                "dewpoint_depression_c": self._dewpoint_depression(temp_group),
                "wind_group": wind_group,
                **self._wind(wind_group),
            }, meaning="mandatory pressure level").to_dict())
            index += 3 if temp_group and wind_group else 1
        return rows

    def _xxbb_fields(self, tokens: list[str]) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        temp_tokens = []
        wind_tokens = []
        extra_tokens = []
        current = "temperature"
        for token in tokens:
            if token == "21212":
                current = "wind"
                continue
            if token == "61616":
                current = "extra"
                extra_tokens.append(token)
                continue
            if token == "62626":
                current = "mission_extra"
                continue
            if token in self.MARKERS:
                continue
            if current == "temperature":
                temp_tokens.append(token)
            elif current == "wind":
                wind_tokens.append(token)
            elif current == "extra":
                extra_tokens.append(token)
        fields["significant_temperature_levels"] = self._significant_temperature_levels(temp_tokens)
        fields["significant_wind_levels"] = self._wind_levels(wind_tokens)
        fields["additional_wind_levels"] = self._wind_levels([token for token in extra_tokens if GROUP_RE.match(token) and token not in self.MARKERS])
        return fields

    def _significant_temperature_levels(self, tokens: list[str]) -> list[dict[str, Any]]:
        rows = []
        index = 0
        while index + 1 < len(tokens):
            p_group, t_group = tokens[index], tokens[index + 1]
            if GROUP_RE.match(p_group) and GROUP_RE.match(t_group):
                rows.append(Field(f"{p_group} {t_group}", {
                    "pressure_hpa": self._pressure_from_xxbb(p_group),
                    "temperature_group": t_group,
                    "temperature_c": self._temperature(t_group),
                    "dewpoint_depression_c": self._dewpoint_depression(t_group),
                }, meaning="significant temperature/humidity level").to_dict())
            index += 2
        return rows

    def _wind_levels(self, tokens: list[str]) -> list[dict[str, Any]]:
        rows = []
        index = 0
        while index + 1 < len(tokens):
            p_group, w_group = tokens[index], tokens[index + 1]
            if GROUP_RE.match(p_group) and GROUP_RE.match(w_group):
                rows.append(Field(f"{p_group} {w_group}", {
                    "pressure_hpa": self._pressure_from_xxbb(p_group),
                    "wind_group": w_group,
                    **self._wind(w_group),
                }, meaning="significant wind level").to_dict())
            index += 2
        return rows

    def _part_header(self, group: str) -> dict[str, Any]:
        return {
            "day": int(group[:2]) if group[:2].isdigit() else None,
            "hour_code": group[2:4],
            "wind_unit_indicator": group[4:] if len(group) > 4 else "",
        }

    def _coord_lat(self, group: str) -> float | None:
        return int(group[2:]) / 10 if re.match(r"^99\d{3}$", group) else None

    def _coord_lon(self, group: str) -> float | None:
        if re.match(r"^1\d{4}$", group):
            return int(group[1:]) / 10
        if re.match(r"^7\d{4}$", group):
            return -int(group[1:]) / 10
        return None

    def _pressure_from_xxbb(self, group: str) -> int | None:
        if not GROUP_RE.match(group) or "/" in group:
            return None
        value = int(group[2:])
        return value + 1000 if value < 100 else value

    def _temperature(self, group: str) -> float | None:
        if not GROUP_RE.match(group) or "/" in group[:3]:
            return None
        value = int(group[:3]) / 10
        return -value if int(group[2]) % 2 else value

    def _dewpoint_depression(self, group: str) -> float | None:
        if not GROUP_RE.match(group) or "/" in group[3:]:
            return None
        return int(group[3:]) / 10

    def _wind(self, group: str) -> dict[str, Any]:
        if not GROUP_RE.match(group) or "/" in group:
            return {"wind_direction_degree": None, "wind_speed_kt": None}
        return {"wind_direction_degree": int(group[:3]), "wind_speed_kt": int(group[3:])}

    def _supplemental_text(self, tokens: list[str]) -> list[str]:
        chunks = []
        current: list[str] = []
        capture = False
        for token in tokens:
            if token in {"61616", "62626"}:
                if current:
                    chunks.append(" ".join(current))
                current = [token]
                capture = True
                continue
            if token in {"XXAA", "XXBB", "21212", "31313"}:
                if current:
                    chunks.append(" ".join(current))
                    current = []
                capture = False
                continue
            if capture:
                current.append(token)
        if current:
            chunks.append(" ".join(current))
        return chunks

    def _unique(self, values: list[str]) -> list[str]:
        seen = set()
        unique = []
        for value in values:
            value = value.strip()
            if value in seen:
                continue
            seen.add(value)
            unique.append(value)
        return unique

    def _supplemental_reports(self, chunks: list[str]) -> list[dict[str, Any]]:
        reports: list[dict[str, Any]] = []
        mission: dict[str, Any] = {}
        for chunk in chunks:
            if chunk.startswith("61616"):
                mission = self._mission_supplement(chunk)
            elif chunk.startswith("62626"):
                reports.append({**mission, **self._detail_supplement(chunk), "raw": chunk})
        return reports

    def _mission_supplement(self, chunk: str) -> dict[str, Any]:
        match = re.search(r"61616\s+(?P<aircraft>\S+)\s+(?P<mission_id>\S+)\s+(?P<mission_type>[A-Z]+)(?:\s+OB\s+(?P<ob>\d+))?", chunk)
        if not match:
            return {"mission_raw": chunk}
        return {
            "aircraft": match.group("aircraft"),
            "mission_id": match.group("mission_id"),
            "mission_type": match.group("mission_type"),
            "observation": match.group("ob"),
            "mission_raw": chunk,
        }

    def _detail_supplement(self, chunk: str) -> dict[str, Any]:
        detail: dict[str, Any] = {"is_center": bool(re.search(r"\bCENTER\b", chunk)), "detail_raw": chunk}
        mbl = re.search(r"\bMBL\s+WND\s+(\d{5})\b", chunk)
        dlm = re.search(r"\bDLM\s+WND\s+(\d{5})\b", chunk)
        aev = re.search(r"\bAEV\s+(\S+)", chunk)
        wl = re.search(r"\b(WL\d{3})\s+(.+?)(?=\s+REL\b|\s+SPG\b|$)", chunk)
        rel = re.search(r"\bREL\s+(\d{4}[NS]\d{5}[EW])\s+(\d{6})", chunk)
        spg = re.search(r"\bSPG\s+(\d{4}[NS]\d{5}[EW])\s+(\d{6})", chunk)
        if mbl:
            detail["mean_boundary_layer_wind"] = self._compact_wind(mbl.group(1))
        if dlm:
            detail["deep_layer_mean_wind"] = self._compact_wind(dlm.group(1))
        if aev:
            detail["aev"] = aev.group(1)
        if wl:
            detail["wind_level"] = {"code": wl.group(1), "groups": wl.group(2).split()}
        if rel:
            detail["release"] = self._compact_fix(rel.group(1), rel.group(2))
        if spg:
            detail["splash"] = self._compact_fix(spg.group(1), spg.group(2))
        return detail

    def _compact_wind(self, group: str) -> dict[str, Any]:
        return {"raw": group, "direction_degree": int(group[:3]), "speed_kt": int(group[3:])}

    def _compact_fix(self, coord: str, time: str) -> dict[str, Any]:
        match = re.match(r"(\d{4})([NS])(\d{5})([EW])", coord)
        if not match:
            return {"raw": coord, "time": time}
        lat = int(match.group(1)) / 100
        lon = int(match.group(3)) / 100
        if match.group(2) == "S":
            lat = -lat
        if match.group(4) == "W":
            lon = -lon
        return {"raw": coord, "time": time, "lat": lat, "lon": lon}

    def _summary(self, heading: dict[str, Any] | None, fields: dict[str, Any]) -> str:
        center = heading.get("center", "") if heading else ""
        issue = heading.get("issue_time", {}).get("raw", "") if heading else ""
        agency = issuing_agency(center) or center or "未知機構"
        prefix = f"{agency}({center}) 於 {issue}Z 發布" if center else "WMO 發布"
        lines = [f"{prefix} TEMP DROP / XXAA-XXBB 投落送上空探測資料。"]
        if fields.get("position", {}).get("value"):
            pos = fields["position"]["value"]
            lines.append(f"投落送位置約為 {self._coord_text(pos['lat'], 'lat')}、{self._coord_text(pos['lon'], 'lon')}。")
        mandatory = [item for item in fields.get("mandatory_levels", []) if item.get("value", {}).get("pressure")]
        temp = fields.get("significant_temperature_levels", [])
        wind = fields.get("significant_wind_levels", [])
        extra = fields.get("additional_wind_levels", [])
        lines.append(f"已解析標準層 {len(mandatory)} 筆、溫濕特性層 {len(temp)} 筆、風特性層 {len(wind)} 筆、附加風層 {len(extra)} 筆。")
        reports = fields.get("supplemental_reports", {}).get("value", [])
        if reports:
            lines.append("附加資訊：" + "；".join(self._supplemental_report_text(item) for item in reports) + "。")
        else:
            supplemental = fields.get("supplemental", {}).get("value", [])
            if supplemental:
                lines.append("附加資訊：" + "；".join(supplemental) + "。")
        return "\n".join(lines)

    def _supplemental_report_text(self, item: dict[str, Any]) -> str:
        parts = []
        mission = " ".join(part for part in (item.get("aircraft"), item.get("mission_id"), item.get("mission_type")) if part)
        if mission:
            parts.append(mission)
        if item.get("observation"):
            parts.append(f"OB {item['observation']}")
        if item.get("is_center"):
            parts.append("中心定位")
        if item.get("mean_boundary_layer_wind"):
            wind = item["mean_boundary_layer_wind"]
            parts.append(f"MBL 風 {wind['direction_degree']} deg/{wind['speed_kt']} kt")
        if item.get("deep_layer_mean_wind"):
            wind = item["deep_layer_mean_wind"]
            parts.append(f"DLM 風 {wind['direction_degree']} deg/{wind['speed_kt']} kt")
        if item.get("release"):
            parts.append(f"投放 {self._fix_text(item['release'])}")
        if item.get("splash"):
            parts.append(f"落海 {self._fix_text(item['splash'])}")
        return "，".join(parts) if parts else item.get("raw", "")

    def _fix_text(self, item: dict[str, Any]) -> str:
        if item.get("lat") is None or item.get("lon") is None:
            return f"{item.get('raw', '')} {item.get('time', '')}".strip()
        return f"{self._coord_text(item['lat'], 'lat')} {self._coord_text(item['lon'], 'lon')} {item.get('time', '')}".strip()

    def _coord_text(self, value: float | None, axis: str) -> str:
        if value is None:
            return "未知"
        hemi = "N" if axis == "lat" and value >= 0 else "S" if axis == "lat" else "E" if value >= 0 else "W"
        number = f"{abs(value):.2f}".rstrip("0").rstrip(".")
        return f"{number}{hemi}"
