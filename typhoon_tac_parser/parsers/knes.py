from __future__ import annotations

import re
from typing import Any

from ..models import Field, ParseResult
from ..normalization import normalize_tac, parse_heading
from .base import BaseParser


FIELD_RE = re.compile(r"^([A-I])\.\s*(.*)$")


class KnesDvorakParser(BaseParser):
    """NOAA/NESDIS SSD Dvorak tropical cyclone satellite bulletin parser."""

    def supports(self, normalized: str) -> bool:
        heading = parse_heading(normalized)
        return bool(heading and heading["center"] == "KNES" and heading["ttaa"] in {"TXPQ", "TXPN"})

    def parse(self, raw: str) -> dict[str, Any]:
        normalized = normalize_tac(raw)
        heading = parse_heading(normalized)
        result = ParseResult(
            family="knes_dvorak_satellite_analysis",
            raw=raw,
            normalized=normalized,
            heading=heading,
        )
        fields = self._letter_fields(normalized)
        bulletin = "TCSCNP" if heading and heading.get("ttaa") == "TXPN" else "TCSWNP"
        basin = "Central Pacific" if bulletin == "TCSCNP" else "Western North Pacific"
        result.fields["bulletin_type"] = Field(
            bulletin,
            f"Tropical Cyclone Satellite Analysis - {basin}",
            meaning="NOAA/NESDIS SSD satellite analysis basin header",
        ).to_dict()
        result.fields["source_profile"] = {
            "value": "KNES",
            "meaning": "NOAA/NESDIS Satellite Services Division Dvorak bulletin",
            "confidence": "high",
        }
        result.systems = [self._system(fields)] if fields else []
        result.remarks = self._remarks(fields)
        result.fields["human_summary"] = self._summary(heading, fields)
        return result.to_dict()

    def _letter_fields(self, text: str) -> dict[str, str]:
        fields: dict[str, str] = {}
        current: str | None = None
        chunks: list[str] = []
        for line in text.splitlines():
            match = FIELD_RE.match(line.strip())
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

    def _system(self, fields: dict[str, str]) -> dict[str, Any]:
        identity = fields.get("A", "")
        code_name_match = re.match(r"(?P<id>\d{2}[A-Z])\s*\((?P<name>[^)]+)\)", identity)
        name_match = re.match(r"(?P<name>.+?)\s*\((?P<id>[^)]+)\)", identity)
        if code_name_match:
            system_identity = code_name_match.group("id")
            system_name = code_name_match.group("name")
        elif name_match:
            system_identity = name_match.group("id")
            system_name = name_match.group("name")
        else:
            system_identity = identity
            system_name = identity
        system = {
            "identity": system_identity,
            "name": system_name,
            "raw": identity,
            "fields": {},
            "discussion": [],
        }
        if fields.get("B"):
            system["fields"]["analysis_time"] = Field(fields["B"], fields["B"], meaning="Dvorak analysis time").to_dict()
        if identity:
            system["fields"]["subject"] = Field(identity, self._subject_info(identity), meaning="analysis subject classification").to_dict()
        if fields.get("C") and fields.get("D"):
            system["fields"]["position"] = self._position(fields["C"], fields["D"])
        if fields.get("E"):
            system["fields"]["satellite_fix"] = Field(fields["E"], fields["E"], meaning="satellite and fix method").to_dict()
        if fields.get("F"):
            system["fields"]["dvorak_classification"] = Field(fields["F"], fields["F"], meaning=self._classification_meaning(fields["F"])).to_dict()
        if fields.get("G"):
            system["fields"]["imagery"] = Field(fields["G"], fields["G"].split("/"), meaning="imagery channels used").to_dict()
        if fields.get("H"):
            system["discussion"].append(fields["H"].removeprefix("REMARKS...").strip())
        if fields.get("I"):
            system["fields"]["additional_positions"] = Field(fields["I"], fields["I"], meaning="additional positions").to_dict()
        return system

    def _subject_info(self, text: str) -> dict[str, Any]:
        id_name_match = re.match(r"(?P<id>\d{2}[A-Z])\s*\((?P<name>[^)]+)\)", text, re.I)
        if id_name_match:
            return {
                "classification": "",
                "id": id_name_match.group("id").upper(),
                "code": "",
                "name": id_name_match.group("name"),
            }
        class_id_match = re.match(
            r"(?P<classification>TROPICAL DISTURBANCE|TROPICAL DEPRESSION|TROPICAL STORM|SUBTROPICAL DEPRESSION|SUBTROPICAL DISTURBANCE|HURRICANE|TYPHOON)\s*\((?P<id>[^)]+)\)",
            text,
            re.I,
        )
        if class_id_match:
            return {
                "classification": class_id_match.group("classification").upper(),
                "id": class_id_match.group("id"),
                "code": "",
            }
        match = re.match(
            r"(?P<classification>TROPICAL DISTURBANCE|TROPICAL DEPRESSION|TROPICAL STORM|SUBTROPICAL DEPRESSION|SUBTROPICAL DISTURBANCE|HURRICANE|TYPHOON)(?:\s+(?P<id>\d{2}[A-Z]|[A-Z]+(?:-[A-Z]+)?))?(?:\s+(?P<code>[A-Z]{2}\d{2}\d{4}))?",
            text,
            re.I,
        )
        if not match:
            return {"raw": text}
        return {
            "classification": match.group("classification").upper(),
            "id": match.group("id"),
            "code": match.group("code") or "",
        }

    def _position(self, lat_raw: str, lon_raw: str) -> dict[str, Any]:
        lat_match = re.match(r"(?P<value>\d+(?:\.\d+)?)(?P<hemi>[NS])", lat_raw)
        lon_match = re.match(r"(?P<value>\d+(?:\.\d+)?)(?P<hemi>[EW])", lon_raw)
        lat = float(lat_match.group("value")) if lat_match else None
        lon = float(lon_match.group("value")) if lon_match else None
        if lat_match and lat_match.group("hemi") == "S":
            lat *= -1
        if lon_match and lon_match.group("hemi") == "W":
            lon *= -1
        return Field(
            f"{lat_raw} {lon_raw}",
            {"lat": lat, "lon": lon},
            "degree",
            "analyzed satellite position",
        ).to_dict()

    def _classification_meaning(self, value: str) -> str:
        if value.upper() == "TOO WEAK":
            return "system is too weak for Dvorak classification"
        return "Dvorak classification"

    def _remarks(self, fields: dict[str, str]) -> list[str]:
        return [fields["H"]] if fields.get("H") else []

    def _summary(self, heading: dict[str, Any] | None, fields: dict[str, str]) -> str:
        center = heading["center"] if heading else "KNES"
        ttaa = heading["ttaa"] if heading else "TXPQ"
        issue = heading.get("issue_time", {}).get("raw", "") if heading else ""
        subject = fields.get("A", "unknown system")
        analysis_time = fields.get("B", "")
        lat = fields.get("C", "")
        lon = fields.get("D", "")
        classification = fields.get("F", "")
        remarks = fields.get("H", "").removeprefix("REMARKS...").strip()
        parts = [
            f"NOAA/NESDIS 衛星服務部({center})於 {issue}Z 發布 {ttaa} 熱帶氣旋衛星分析報文。",
            f"分析對象：{self._translate_subject(subject)}。",
        ]
        if analysis_time:
            parts.append(f"觀測時間：{analysis_time}。")
        if lat and lon:
            parts.append(f"定位位置：{lat}, {lon}。")
        if classification:
            parts.append(f"分類：{self._translate_classification(classification)}。")
        if remarks:
            parts.append(f"備註：{self._translate_remark(remarks)}")
        return "\n".join(parts)

    def _translate_subject(self, text: str) -> str:
        info = self._subject_info(text)
        level_map = {
            "TROPICAL DISTURBANCE": "熱帶擾動",
            "TROPICAL DEPRESSION": "熱帶低壓",
            "TROPICAL STORM": "熱帶風暴",
            "SUBTROPICAL DISTURBANCE": "亞熱帶擾動",
            "SUBTROPICAL DEPRESSION": "亞熱帶低壓",
            "HURRICANE": "颶風",
            "TYPHOON": "颱風",
        }
        classification = level_map.get(info.get("classification", ""), "")
        identity = " ".join(part for part in (info.get("id"), info.get("code") or info.get("name")) if part)
        return " ".join(part for part in (classification, identity) if part) or text

    def _translate_classification(self, text: str) -> str:
        raw = text.strip().rstrip(".")
        if raw.upper() in {"TOO WEAK", "TOO WEAK TO CLASSIFY"}:
            return "系統過弱，無法分類"
        match = re.match(r"^T?(\d+(?:\.\d+)?)\/(\d+(?:\.\d+)?)(?:\/([DSW])(\d+(?:\.\d+)?)\/(\d+)\s*H(?:OU)?RS?)?$", raw, re.I)
        if not match:
            return text
        trend_map = {"D": "增強", "S": "維持", "W": "減弱"}
        parts = [f"T {match.group(1)}", f"CI {match.group(2)}"]
        if match.group(3):
            code = match.group(3).upper()
            parts.append(f"{match.group(5)} 小時趨勢{trend_map.get(code, code)} ({code}{match.group(4)}/{match.group(5)}HRS)")
        return "，".join(parts)

    def _translate_remark(self, text: str) -> str:
        translated = re.sub(r"([<>]?\d+)\/10\s+BANDING\s+YIELDS\s+A\s+DT\s+OF\s+(\d+(?:\.\d+)?)\.", r"\1/10 雲帶型態得出數據 T 數為 \2。", text, flags=re.I)
        translated = re.sub(r"([<>]?\d+)\/10\s+BANDING\s+RESULTS\s+IN\s+A\s+DT\s+OF\s+(\d+(?:\.\d+)?)\.", r"\1/10 雲帶型態得出數據 T 數為 \2。", translated, flags=re.I)
        translated = re.sub(r"THE\s+MET\s+IS\s+(\d+(?:\.\d+)?)\s+DUE\s+TO\s+A\s+SLOW\s+DEVELOPMENT\s+OVER\s+24\s+HOURS\.", r"因 24 小時內緩慢發展，模型預估 T 數為 \1。", translated, flags=re.I)
        translated = re.sub(r"THE\s+MET\s+AND\s+PT\s+ARE\s+(\d+(?:\.\d+)?)\s+BASED\s+ON\s+THE\s+INITIAL\s+DEVELOPMENT\s+TREND\s+WITHIN\s+THE\s+FIRST\s+24\s+HOURS\.", r"依據最初 24 小時內的初始發展趨勢，模型預估 T 數與型態 T 數均為 \1。", translated, flags=re.I)
        translated = re.sub(r"THE\s+MET\s+AND\s+PT\s+ARE\s+(\d+(?:\.\d+)?)\.", r"模型預估 T 數與型態 T 數均為 \1。", translated, flags=re.I)
        translated = re.sub(r"THE\s+MET\s+IS\s+(\d+(?:\.\d+)?)\.", r"模型預估 T 數為 \1。", translated, flags=re.I)
        return (
            translated
            .replace("THE PT AGREES.", "型態 T 數與其一致。")
            .replace("THE FT IS BASED ON THE MET DUE TO THE FLUCTUATING CONVECTION.", "因對流起伏，最終 T 數依模型預估 T 數決定。")
            .replace("THE FT IS BASED ON THE MET SINCE THE BANDING FEATURE WAS NOT CLEAR CUT.", "由於雲帶特徵不夠明確，最終 T 數依模型預估 T 數決定。")
            .replace("THE FT IS BASED ON THE DT.", "最終 T 數依數據 T 數決定。")
        )


class PhfoSatelliteFixParser(KnesDvorakParser):
    """Central Pacific Hurricane Center A-I tropical cyclone satellite fix parser."""

    def supports(self, normalized: str) -> bool:
        heading = parse_heading(normalized)
        return bool(heading and heading["center"] == "PHFO" and heading["ttaa"] == "TXPN")

    def parse(self, raw: str) -> dict[str, Any]:
        parsed = super().parse(raw)
        parsed["family"] = "phfo_satellite_fix"
        parsed["fields"]["bulletin_type"] = Field(
            "TCSNP",
            "Central Pacific Tropical Cyclone Summary - Fixes",
            meaning="CPHC satellite fix basin header",
        ).to_dict()
        parsed["fields"]["source_profile"] = {
            "value": "PHFO/CPHC",
            "meaning": "Central Pacific Hurricane Center satellite fix bulletin",
            "confidence": "high",
        }
        parsed["fields"]["human_summary"] = self._summary(parsed.get("heading"), self._letter_fields(parsed.get("normalized", "")))
        return parsed

    def _summary(self, heading: dict[str, Any] | None, fields: dict[str, str]) -> str:
        issue = heading.get("issue_time", {}).get("raw", "") if heading else ""
        subject = fields.get("A", "unknown system")
        analysis_time = fields.get("B", "")
        lat = fields.get("C", "")
        lon = fields.get("D", "")
        classification = fields.get("F", "")
        remarks = fields.get("H", "").removeprefix("REMARKS...").strip()
        parts = [
            f"中太平洋颶風中心(PHFO/CPHC)於 {issue}Z 發布中太平洋熱帶氣旋衛星定位摘要。",
            f"分析對象：{self._translate_subject(subject)}。",
        ]
        if analysis_time:
            parts.append(f"觀測時間：{analysis_time}。")
        if lat and lon:
            parts.append(f"定位位置：{lat}, {lon}。")
        if classification:
            parts.append(f"分類：{self._translate_classification(classification)}。")
        if remarks:
            parts.append(f"備註：{self._translate_remark(remarks)}")
        return "\n".join(parts)

    def _translate_subject(self, text: str) -> str:
        info = self._subject_info(text)
        level_map = {
            "TROPICAL DISTURBANCE": "熱帶擾動",
            "TROPICAL DEPRESSION": "熱帶低壓",
            "TROPICAL STORM": "熱帶風暴",
            "SUBTROPICAL DISTURBANCE": "亞熱帶擾動",
            "SUBTROPICAL DEPRESSION": "亞熱帶低壓",
            "HURRICANE": "颶風",
            "TYPHOON": "颱風",
        }
        classification = level_map.get(info.get("classification", ""), "")
        identity = " ".join(part for part in (info.get("id"), info.get("code")) if part)
        return " ".join(part for part in (classification, identity) if part) or text

    def _translate_classification(self, text: str) -> str:
        raw = text.strip().rstrip(".")
        if raw.upper() == "TOO WEAK TO CLASSIFY":
            return "系統過弱，無法分類"
        match = re.match(
            r"^T?(\d+(?:\.\d+)?)\/(\d+(?:\.\d+)?)(?:\/([DSW])(\d+(?:\.\d+)?)\/(\d+)\s*H(?:OU)?RS?)?$",
            raw,
            re.I,
        )
        if not match:
            return text
        trend_map = {"D": "增強", "S": "維持", "W": "減弱"}
        parts = [f"T {match.group(1)}", f"CI {match.group(2)}"]
        if match.group(3):
            code = match.group(3).upper()
            parts.append(f"{match.group(5)} 小時趨勢{trend_map.get(code, code)} ({code}{match.group(4)}/{match.group(5)}HRS)")
        return "，".join(parts)

    def _translate_remark(self, text: str) -> str:
        translated = re.sub(
            r"CURVED\s+BAND\s+WRAPS\s+(\d+(?:\.\d+)?)\s+ON\s+LOG\s*10\s+SPIRAL\s+YIELDING\s+A\s+DT\s+OF\s+(\d+(?:\.\d+)?)\.",
            r"曲線雲帶沿 log10 螺旋包捲 \1，得出數據 T 數為 \2。",
            text,
            flags=re.I,
        )
        translated = re.sub(
            r"(\d+(?:\.\d+)?)\s+WRAP\s+ON\s+LOG\s*10\s+SPIRAL\s+YIELDS?\s+A\s+DT\s+OF\s+(\d+(?:\.\d+)?)\.",
            r"對流繞對數螺旋 \1 圈，得出數據 T 數為 \2。",
            translated,
            flags=re.I,
        )
        translated = re.sub(r"MET\s+OF\s+(\d+(?:\.\d+)?)\.", r"模型預估 T 數為 \1。", translated, flags=re.I)
        translated = re.sub(r"PT\s+OF\s+(\d+(?:\.\d+)?)\.", r"型態 T 數為 \1。", translated, flags=re.I)
        return (
            translated
            .replace("PT AGREES.", "型態 T 數一致。")
            .replace("MET UNAVAILABLE.", "模型預估 T 數不可用。")
            .replace("FT BASED ON PT AS CLOUD FEATURES ARE NOT CLEAR CUT.", "由於雲系特徵不明確，最終 T 數依型態 T 數決定。")
            .replace("FT BASED ON MET.", "最終 T 數依模型預估 T 數決定。")
            .replace("FT BASED ON PT.", "最終 T 數依型態 T 數決定。")
            .replace("FT BASED ON DT.", "最終 T 數依數據 T 數決定。")
            .replace("TOO WEAK TO CLASSIFY.", "系統過弱，無法分類。")
            .replace("THIS WILL BE FINAL FIX UNLESS CONVECTION REDEVELOPS.", "除非對流重新發展，否則這將是最後一次定位。")
        )
