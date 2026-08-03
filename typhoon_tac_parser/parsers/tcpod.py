from __future__ import annotations

import re
from typing import Any

from ..centers import issuing_agency
from ..models import Field, ParseResult
from ..normalization import normalize_tac, parse_heading
from .base import BaseParser


class NhcTcpodParser(BaseParser):
    """NHC Tropical Cyclone Plan of the Day reconnaissance requirements."""

    FLIGHT_RE = re.compile(r"FLIGHT\s+(?P<label>ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN)\s+-\s+(?P<aircraft>[A-Z0-9 ]+?)(?=\s+FLIGHT\s+(?:ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN)\s+-|$)")
    FIELD_RE = re.compile(r"([A-H])\.\s+(.+?)(?=\s+[A-H]\.\s+|$)")

    def supports(self, normalized: str) -> bool:
        heading = parse_heading(normalized)
        return bool(heading and heading["center"] == "KNHC" and "TROPICAL CYCLONE PLAN OF THE DAY" in normalized)

    def parse(self, raw: str) -> dict[str, Any]:
        normalized = normalize_tac(raw)
        heading = parse_heading(normalized)
        result = ParseResult(family="nhc_tcpod_recon_plan", raw=raw, normalized=normalized, heading=heading)
        result.fields["bulletin_type"] = Field("TCPOD", "熱帶氣旋每日偵察飛行計畫", meaning="Tropical Cyclone Plan of the Day").to_dict()
        result.fields["source_profile"] = {
            "value": "KNHC",
            "meaning": issuing_agency("KNHC") or "National Hurricane Center",
            "confidence": "high",
        }
        result.fields.update(self._header_fields(normalized))
        sections = self._requirement_sections(normalized)
        result.systems = sections
        result.fields["human_summary"] = self._summary(heading, result.fields, sections)
        return result.to_dict()

    def _header_fields(self, text: str) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        valid = re.search(r"VALID\s+(?P<from>\d{2}/\d{4}Z)\s+TO\s+(?P<to>\d{2}/\d{4}Z)\s+(?P<month>[A-Z]+)\s+(?P<year>\d{4})", text, re.I)
        if valid:
            fields["valid_period"] = Field(valid.group(0), {
                "from": valid.group("from"),
                "to": valid.group("to"),
                "month": valid.group("month").upper(),
                "year": int(valid.group("year")),
            }, meaning="TCPOD valid period").to_dict()
        number = re.search(r"TCPOD NUMBER\.*(?P<number>\d{2}-\d{3})", text, re.I)
        if number:
            fields["tcpod_number"] = Field(number.group("number"), number.group("number"), meaning="TCPOD number").to_dict()
        issued = re.search(r"(\d{3,4}\s+[AP]M\s+[A-Z]{3}\s+[A-Z]{3}\s+\d{1,2}\s+[A-Z]+\s+\d{4})", text, re.I)
        if issued:
            fields["issued_local"] = Field(issued.group(1), issued.group(1), meaning="local issue time text").to_dict()
        return fields

    def _requirement_sections(self, text: str) -> list[dict[str, Any]]:
        sections = []
        section_matches = list(re.finditer(r"^(?P<roman>I{1,3}|IV|V)\.\s+(?P<basin>[A-Z ]+?)\s+REQUIREMENTS\s*$", text, re.M))
        for index, match in enumerate(section_matches):
            start = match.end()
            end = section_matches[index + 1].start() if index + 1 < len(section_matches) else len(text)
            body = text[start:end]
            sections.append({
                "identity": match.group("basin").strip(),
                "raw": body.strip(),
                "fields": {
                    "basin": Field(match.group("basin").strip(), self._translate_basin(match.group("basin").strip()), meaning="recon basin").to_dict(),
                    "requirements": Field("requirements", self._systems(body), meaning="reconnaissance requirements").to_dict(),
                    "outlook": Field("outlook", self._outlook(body), meaning="outlook for succeeding day").to_dict(),
                },
            })
        return sections

    def _systems(self, body: str) -> list[dict[str, Any]]:
        systems = []
        matches = list(re.finditer(r"^\s*(?P<num>\d+)\.\s+(?P<name>(?!OUTLOOK|NEGATIVE).+?)\s*$", body, re.M))
        for index, match in enumerate(matches):
            name = match.group("name").strip()
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
            block = body[start:end]
            flights = self._flights(block)
            negative = "NEGATIVE RECONNAISSANCE REQUIREMENTS" in name.upper()
            systems.append({"name": name, "negative": negative, "flights": flights})
        if not systems and "NEGATIVE RECONNAISSANCE REQUIREMENTS" in body.upper():
            systems.append({"name": "NEGATIVE RECONNAISSANCE REQUIREMENTS", "negative": True, "flights": []})
        return systems

    def _flights(self, block: str) -> list[dict[str, Any]]:
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        flights: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []
        for line in lines:
            matches = list(self.FLIGHT_RE.finditer(line))
            if matches:
                pending = []
                for match in matches:
                    flight = {"label": match.group("label"), "aircraft": " ".join(match.group("aircraft").split()), "fields": {}}
                    flights.append(flight)
                    pending.append(flight)
                continue
            if not pending:
                continue
            field_matches = list(self.FIELD_RE.finditer(line))
            for i, field_match in enumerate(field_matches):
                if i < len(pending):
                    pending[i]["fields"][field_match.group(1)] = field_match.group(2).strip()
        return flights

    def _outlook(self, body: str) -> list[str]:
        outlook = re.search(r"OUTLOOK FOR SUCCEEDING DAY[:.]+(?P<body>.*?)(?=^\s*(?:II|III|IV|V)\.|^\$\$|$)", body, re.I | re.S | re.M)
        if not outlook:
            return []
        return [re.sub(r"^\s*[A-Z]\.\s+", "", line).strip() for line in outlook.group("body").splitlines() if line.strip()]

    def _summary(self, heading: dict[str, Any] | None, fields: dict[str, Any], sections: list[dict[str, Any]]) -> str:
        issue = heading.get("issue_time", {}).get("raw", "") if heading else ""
        valid = fields.get("valid_period", {}).get("value", {})
        lines = [f"美國國家氣象局/國家颶風中心(KNHC)於 {issue}Z 發布 TCPOD 熱帶氣旋偵察飛行計畫。"]
        if valid:
            lines.append(f"有效期間：{valid['from']} 至 {valid['to']}，{valid['month']} {valid['year']}。")
        for section in sections:
            basin = section["fields"]["basin"]["value"]
            requirements = section["fields"]["requirements"]["value"]
            if not requirements:
                continue
            for req in requirements:
                if req.get("negative"):
                    lines.append(f"{basin}：無偵察需求。")
                    continue
                lines.append(f"{basin}：{req['name']}，規劃 {len(req.get('flights', []))} 架次偵察任務。")
        return "\n".join(lines)

    def _translate_basin(self, basin: str) -> str:
        return {"ATLANTIC": "大西洋", "PACIFIC": "太平洋"}.get(basin.strip().upper(), basin)
