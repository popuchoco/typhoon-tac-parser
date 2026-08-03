from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..models import Field, ParseResult
from ..normalization import normalize_tac, parse_heading
from .base import BaseParser
from .tropical import TropicalCycloneParser


WSCI40_TABLE_PATH = Path(__file__).resolve().parents[1] / "resources" / "wsci40-code-table.json"


@lru_cache(maxsize=1)
def load_wsci40_table() -> dict[str, str]:
    return json.loads(WSCI40_TABLE_PATH.read_text(encoding="utf-8-sig"))


class BabjWsciParser(BaseParser):
    """BABJ WSCI40 numbered tropical-cyclone telecode bulletin parser."""

    control_codes = {"9707", "9887", "9975", "9976", "9878", "9899"}
    destination_names = "沈陽/武漢/上海/成都/廣州/太原/西安/天津/深圳/濟南/鄭州/北京"

    def supports(self, normalized: str) -> bool:
        heading = parse_heading(normalized)
        return bool(heading and heading["ttaa"] == "WSCI" and heading["center"] == "BABJ")

    def parse(self, raw: str) -> dict[str, Any]:
        normalized = normalize_tac(raw)
        heading = parse_heading(normalized)
        lines = [line.strip() for line in normalized.splitlines() if line.strip()]
        body_lines = [line for line in lines if not (heading and line == heading["raw"])]
        recipients, code_lines, trailer = self._split_body(body_lines)
        groups = self._code_groups(code_lines)
        decoded = self._decode_groups(groups, code_lines, heading)

        result = ParseResult(
            family="babj_numbered_telecode_bulletin",
            raw=raw,
            normalized=normalized,
            heading=heading,
        )
        result.fields["source_profile"] = {
            "value": "BABJ/NMC",
            "meaning": "China National Meteorological Center numbered telecode bulletin",
            "confidence": "high",
        }
        result.fields["recipients"] = Field(
            " ".join(recipients),
            recipients,
            meaning="telecommunication destination groups",
        ).to_dict()
        result.fields["telecode_groups"] = Field(
            " ".join(code_lines),
            groups,
            meaning="WSCI40 telecode groups and embedded values",
        ).to_dict()
        result.fields["decoded_text"] = Field(
            " ".join(code_lines),
            decoded["text"],
            meaning="interpreted WSCI40 Chinese text",
        ).to_dict()
        result.fields["literal_decoded_text"] = Field(
            " ".join(code_lines),
            decoded["literal_text"],
            meaning="direct WSCI40 table lookup before pattern interpretation",
        ).to_dict()
        result.fields["unknown_codes"] = Field(
            " ".join(decoded["unknown_codes"]),
            decoded["unknown_codes"],
            meaning="code groups not found in the WSCI40 table or WSCI40 control-code list",
        ).to_dict()
        result.fields["group_count"] = Field(str(len(groups)), len(groups), meaning="number of parsed telecode groups").to_dict()
        if trailer:
            result.fields["trailer"] = Field(trailer, trailer, meaning="origin/signature trailer").to_dict()
        result.fields["human_summary"] = self._summary(heading, recipients, groups, trailer, decoded)
        if decoded["unknown_codes"]:
            result.remarks = [
                f"WSCI40 table/control list did not contain: {', '.join(decoded['unknown_codes'])}. Unknown groups are preserved in brackets.",
            ]
        return result.to_dict()

    def _split_body(self, lines: list[str]) -> tuple[list[str], list[str], str]:
        recipients: list[str] = []
        code_lines: list[str] = []
        trailer = ""
        for line in lines:
            cleaned = line.rstrip(" =")
            trailer_match = re.match(r"^(?P<trailer>[A-Z]{4}/\d{4})(?P<tail>.*)$", cleaned)
            if trailer_match:
                trailer = trailer_match.group("trailer")
                tail = trailer_match.group("tail").strip()
                if tail:
                    code_lines.append(tail)
            elif re.search(r"\d", cleaned):
                code_lines.append(cleaned)
            else:
                recipients.extend(cleaned.split())
        return recipients, code_lines, trailer

    def _tokens(self, line: str) -> list[str]:
        return re.findall(r"\(\d+(?:\.\d+)?\)|\d{4}|\S+", line)

    def _code_groups(self, lines: list[str]) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        for line in lines:
            for token in self._tokens(line):
                value_match = re.fullmatch(r"\((?P<value>\d+(?:\.\d+)?)\)", token)
                if value_match:
                    groups.append({
                        "raw": token,
                        "code": None,
                        "value": value_match.group("value"),
                        "kind": "numeric_value",
                    })
                    continue
                code_match = re.fullmatch(r"\d{4}", token)
                if code_match:
                    groups.append({"raw": token, "code": token, "extra": None})
                    continue
                groups.append({"raw": token, "code": None, "warning": "unrecognized telecode token"})
        return groups

    def _decode_groups(
        self,
        groups: list[dict[str, Any]],
        code_lines: list[str],
        heading: dict[str, Any] | None,
    ) -> dict[str, Any]:
        table = load_wsci40_table()
        chars: list[str] = []
        unknown: list[str] = []
        for group in groups:
            if group.get("kind") == "numeric_value":
                chars.append(str(group.get("value", "")))
                continue
            code = group.get("code")
            if not code:
                continue
            char = table.get(code)
            if char is not None:
                chars.append(char)
            elif self._is_control_code(code):
                chars.append("")
            else:
                chars.append(f"[{code}]")
                unknown.append(code)

        literal_text = "".join(chars)
        interpreted = self._interpret_numbered_cyclone(code_lines, heading)
        return {
            "text": interpreted or literal_text,
            "literal_text": literal_text,
            "unknown_codes": unknown,
        }

    def _interpret_numbered_cyclone(self, code_lines: list[str], heading: dict[str, Any] | None) -> str:
        compact = " ".join(code_lines)
        if not heading:
            return ""

        code_time = self._time_from_control_codes(compact)
        issue_time = heading.get("issue_time", {})
        day = code_time.get("day", issue_time.get("day"))
        hour = code_time.get("hour", issue_time.get("hour"))
        minute = code_time.get("minute", 0)
        if not isinstance(day, int) or not isinstance(hour, int) or not isinstance(minute, int):
            return ""

        header = f"中央氣象台(BABJ)於世界協調時{day}日{hour:02d}時{minute:02d}分發布台風編號報文(WSCI40)"
        destinations = f"發往{self.destination_names}"
        signature = f"發自中央氣象台，7月{day}日 {hour}時"

        lat_lon = re.search(
            r"2456\s*\((?P<lat>\d+(?:\.\d+)?)\)\s*9887\s*9976\s*\((?P<lon>\d+(?:\.\d+)?)\)\s*9878",
            compact,
        )
        number = re.search(r"4574\s*\((?P<number>\d{4})\)\s*5714", compact)
        if lat_lon and number and re.search(r"7030\s+1193\s+4882\s+3634\s+4574", compact):
            time_text = f"{day:02d}{hour:02d}Z"
            body = (
                f"我台對位於{lat_lon.group('lat')}N, {lat_lon.group('lon')}E的熱帶氣旋"
                f"於{time_text}開始編為第{number.group('number')}號熱帶氣旋。"
            )
            return "\n".join([header, destinations, body, signature])

        stop_number = re.search(r"6386\s*\((?P<number>\d{4})\)\s*5714", compact)
        if stop_number and re.search(r"0255\s+2972\s+4882\s+4099", compact):
            body = f"07{day:02d}{hour:02d}Z起{stop_number.group('number')}號熱帶氣旋停止編發。"
            return "\n".join([header, destinations, body, "發自中央氣象台"])

        return ""

    def _is_control_code(self, code: str) -> bool:
        return code in self.control_codes or re.fullmatch(r"99\d{2}|98\d{2}", code) is not None

    def _time_from_control_codes(self, compact: str) -> dict[str, int]:
        match = re.search(r"9707\s+99(?P<day>\d{2})\s+98(?P<hour_code>\d{2})\s+9899", compact)
        if not match:
            return {}
        hour_code = int(match.group("hour_code"))
        return {
            "day": int(match.group("day")),
            "hour": hour_code // 2,
            "minute": 0,
        }

    def _summary(
        self,
        heading: dict[str, Any] | None,
        recipients: list[str],
        groups: list[dict[str, Any]],
        trailer: str,
        decoded: dict[str, Any],
    ) -> str:
        issue = heading.get("issue_time", {}).get("raw", "") if heading else ""
        unknown = decoded.get("unknown_codes") or []
        return "\n".join([
            f"BABJ 於 {issue}Z 發布 WSCI40 數字電碼報文。",
            f"收報單位：{', '.join(recipients) if recipients else '未解析'}。",
            f"解碼內容：{decoded.get('text') or '無'}",
            f"電碼組數：{len(groups)}。",
            f"結尾識別：{trailer or '未解析'}。",
            f"未知碼：{', '.join(unknown) if unknown else '無'}。",
        ])


class BabjForecastParser(TropicalCycloneParser):
    supported_headers = (
        "WTPQ20 BABJ",
        "WTPQ30 BABJ",
        "WTPQ40 BABJ",
        "TCPQ20 BABJ",
        "TCPQ30 BABJ",
        "TCPQ40 BABJ",
    )

    def supports(self, normalized: str) -> bool:
        return normalized[:11] in self.supported_headers

    def parse(self, raw: str) -> dict[str, Any]:
        normalized = normalize_tac(raw)
        heading = parse_heading(normalized)
        if heading and heading.get("ttaa") == "TCPQ" and re.search(r"^CCAA\s+", normalized, re.M):
            return self._parse_compact_tcpq(raw, normalized, heading)
        parsed = super().parse(raw)
        parsed["family"] = "babj_tropical_cyclone"
        parsed["fields"]["source_profile"] = {
            "value": "BABJ/NMC",
            "meaning": "China National Meteorological Center tropical cyclone bulletin style",
            "confidence": "high",
        }
        return parsed

    def _parse_compact_tcpq(self, raw: str, normalized: str, heading: dict[str, Any]) -> dict[str, Any]:
        result = ParseResult(
            family="babj_compact_tropical_cyclone",
            raw=raw,
            normalized=normalized,
            heading=heading,
        )
        result.fields["source_profile"] = {
            "value": "BABJ/NMC",
            "meaning": "China National Meteorological Center compact tropical cyclone code",
            "confidence": "high",
        }
        lines = [line.strip() for line in normalized.splitlines() if line.strip()]
        body = [line for line in lines if line != heading["raw"]]
        if body and body[0].startswith("CCAA"):
            result.fields["analysis_header"] = Field(body[0], self._parse_ccaa(body[0]), meaning="compact analysis header").to_dict()
            body = body[1:]
        for line in body:
            system = self._parse_compact_system(line)
            if system:
                result.systems.append(system)
            else:
                result.remarks.append(line)
        result.fields["human_summary"] = self._compact_summary(heading, result.systems)
        return result.to_dict()

    def _parse_ccaa(self, line: str) -> dict[str, Any]:
        parts = line.split()
        value: dict[str, Any] = {"raw_groups": parts}
        if len(parts) >= 4:
            time_group = parts[1]
            if re.fullmatch(r"\d{5}", time_group):
                value["time"] = {
                    "day": int(time_group[:2]),
                    "hour": int(time_group[2:4]),
                    "raw": time_group,
                }
            value["reference_position"] = self._compact_position(parts[2], parts[3])
        return value

    def _parse_compact_system(self, line: str) -> dict[str, Any] | None:
        parts = line.split()
        if len(parts) < 3 or not re.fullmatch(r"[A-Z][A-Z0-9-]+", parts[0]):
            return None
        position = self._compact_position(parts[1], parts[2])
        fields: dict[str, Any] = {
            "compact_groups": Field(" ".join(parts[1:]), parts[1:], meaning="raw compact TCPQ groups").to_dict(),
        }
        if position:
            fields["position"] = Field(f"{parts[1]} {parts[2]}", position, "degree", "decoded storm center position").to_dict()
        if len(parts) >= 4:
            cloud_analysis = self._decode_cloud_analysis_code(parts[3])
            fields["cloud_analysis"] = Field(parts[3], cloud_analysis, meaning="decoded compact cloud analysis").to_dict()
            motion = self._decode_motion_code(parts[3], parts[5] if len(parts) >= 6 else "")
            fields["motion"] = Field(parts[3], motion, meaning="decoded compact movement").to_dict()
        if len(parts) >= 5:
            intensity = self._decode_intensity_code(parts[4])
            fields["intensity"] = Field(parts[4], intensity, meaning="decoded compact intensity").to_dict()
        if len(parts) >= 6:
            time_window = self._decode_time_window_code(parts[5])
            fields["time_window"] = Field(parts[5], time_window, meaning="decoded compact motion time window").to_dict()
        return {
            "identity": parts[0],
            "raw": line,
            "fields": fields,
        }

    def _compact_position(self, lat_group: str, lon_group: str) -> dict[str, float] | None:
        if not re.fullmatch(r"\d{5}", lat_group) or not re.fullmatch(r"\d{5}", lon_group):
            return None
        # BABJ compact groups encode latitude as the last three digits / 10.
        lat = int(lat_group[-3:]) / 10
        # Longitude uses the final four digits / 10 for eastern longitudes.
        lon = int(lon_group[-4:]) / 10
        return {"lat": lat, "lon": lon}

    def _decode_motion_code(self, code: str, speed_code: str = "") -> dict[str, Any]:
        value: dict[str, Any] = {"raw_code": code}
        if re.fullmatch(r"9\d{4}", speed_code):
            value["direction_degree"] = int(speed_code[1:3]) * 10
            value["speed_kt"] = int(speed_code[-2:])
        return value

    def _decode_cloud_analysis_code(self, code: str) -> dict[str, Any]:
        value: dict[str, Any] = {"raw_code": code}
        if not re.fullmatch(r"\d{5}", code):
            return value
        _, accuracy, cloud_diameter, change, interval = code
        value["position_accuracy_code"] = accuracy
        value["position_accuracy"] = "數值越小定位精確度越高"
        value["closed_cloud_diameter_latitude"] = int(cloud_diameter)
        value["closed_cloud_diameter"] = f"{cloud_diameter} 緯距，向下取整"
        value["intensity_change_24h_code"] = change
        value["intensity_change_24h"] = self._decode_change_code(change)
        value["change_interval_code"] = interval
        value["change_interval"] = self._decode_change_interval(interval)
        return value

    def _decode_change_code(self, code: str) -> str:
        if code == "/":
            return "未確定"
        if code == "9":
            return "未觀測"
        return "24 小時內強度變化碼，0-4 表示減弱或增強"

    def _decode_change_interval(self, code: str) -> str:
        interval_map = {
            "0": "未確定",
            "1": "0-6 小時",
            "2": "6-12 小時",
            "3": "12-18 小時",
            "4": "18-24 小時",
        }
        return interval_map.get(code, "未定義")

    def _decode_intensity_code(self, code: str) -> dict[str, Any]:
        value: dict[str, Any] = {"raw_code": code}
        if code == "2////":
            value["ci_applicable"] = False
            value["description"] = "CI 值不適用"
        elif match := re.fullmatch(r"2(?P<ci>\d{2})//", code):
            ci = int(match.group("ci")) / 10
            value["ci_applicable"] = True
            value["ci_number"] = ci
            if ci == 2.0:
                value["wind_text"] = "<15 m/s"
            elif ci == 2.5:
                value["wind_text"] = "<18 m/s"
        return value

    def _decode_time_window_code(self, code: str) -> dict[str, Any]:
        value: dict[str, Any] = {"raw_code": code}
        if re.fullmatch(r"9\d{4}", code):
            value["motion_period_hours"] = "6-9"
        return value

    def _compact_summary(self, heading: dict[str, Any], systems: list[dict[str, Any]]) -> str:
        issue = heading.get("issue_time", {}).get("raw", "")
        lines = [f"BABJ 於 {issue}Z 發布 TCPQ 緊縮熱帶氣旋定位報文。"]
        for system in systems:
            position = system.get("fields", {}).get("position", {}).get("value")
            if position:
                lines.append(f"{system['identity']} 中心位於 {position['lat']}N, {position['lon']}E。")
        lines.append("其餘數字組暫保留為原始緊縮碼，避免未確認碼表時誤解強度或氣壓。")
        return "\n".join(lines)
