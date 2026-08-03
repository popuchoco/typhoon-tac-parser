from __future__ import annotations

import re
from typing import Any

from ..models import Field
from ..normalization import normalize_tac
from .tropical import TropicalCycloneParser


class JtwcParser(TropicalCycloneParser):
    supported_headers = (
        "ABPW10 PGTW",
        "WTPN31 PGTW",
        "WTPN32 PGTW",
        "WTPN33 PGTW",
        "WDPN31 PGTW",
        "WDPN32 PGTW",
        "TPPN10 PGTW",
        "TPPN11 PGTW",
        "TPPN12 PGTW",
    )

    def supports(self, normalized: str) -> bool:
        return normalized[:11] in self.supported_headers or "JOINT TYPHOON WRNCEN" in normalized

    def parse(self, raw: str) -> dict[str, Any]:
        parsed = super().parse(raw)
        parsed["family"] = "jtwc_tropical_cyclone"
        parsed["fields"]["source_profile"] = {
            "value": "JTWC",
            "meaning": "Joint Typhoon Warning Center tropical cyclone bulletin style",
            "confidence": "high",
        }
        if parsed.get("heading", {}).get("ttaa") == "ABPW":
            self._enrich_abpw(parsed, raw)
        return parsed

    def _enrich_abpw(self, parsed: dict[str, Any], raw: str) -> None:
        text = re.sub(r"\s+", " ", normalize_tac(raw))
        parsed.setdefault("fields", {})["advisory_type"] = {
            "value": "Significant Tropical Weather Advisory",
            "meaning": "JTWC significant tropical weather advisory",
            "confidence": "high",
        }
        parsed["fields"]["area_summaries"] = {
            "western_north_pacific": self._area_status(text, "WESTERN NORTH PACIFIC AREA"),
            "south_pacific": self._area_status(text, "SOUTH PACIFIC AREA"),
        }

        systems = []
        for match in re.finditer(r"INVEST\s+(?P<id>\d{2}[A-Z]).*?(?=(?:\(\d+\)\s+NO OTHER)|(?:C\. SUBTROPICAL)|//|NNNN|$)", text, re.I):
            paragraph = match.group(0)
            system = {
                "identity": match.group("id").upper(),
                "raw": paragraph,
                "fields": {},
                "discussion": self._abpw_discussion(paragraph),
            }
            extracted = self._extract_line_fields(paragraph)
            if extracted:
                system["fields"].update(extracted)
            self._extract_current_position(system, paragraph)
            self._extract_abpw_wind(system, paragraph)
            self._extract_abpw_pressure(system, paragraph)
            self._extract_development_potential(system, paragraph)
            systems.append(system)

        if systems:
            parsed["systems"] = systems
            parsed["fields"]["human_summary"] = self._abpw_summary(parsed, systems)

    def _extract_current_position(self, system: dict[str, Any], paragraph: str) -> None:
        match = re.search(r"IS NOW LOCATED NEAR\s+(?P<lat>\d{1,2}(?:\.\d+)?)(?P<lat_h>[NS])\s+(?P<lon>\d{1,3}(?:\.\d+)?)(?P<lon_h>[EW])", paragraph, re.I)
        if not match:
            return
        lat = float(match.group("lat"))
        lon = float(match.group("lon"))
        if match.group("lat_h").upper() == "S":
            lat *= -1
        if match.group("lon_h").upper() == "W":
            lon *= -1
        system["fields"]["position"] = Field(
            match.group(0),
            {"lat": lat, "lon": lon},
            "degree",
            "current invest position",
        ).to_dict()

    def _extract_abpw_wind(self, system: dict[str, Any], paragraph: str) -> None:
        match = re.search(r"MAXIMUM SUSTAINED SURFACE WINDS ARE ESTIMATED AT\s+(?P<from>\d{1,3})(?:\s+TO\s+(?P<to>\d{1,3}))?\s*(?P<unit>KNOTS|KT|KTS)", paragraph, re.I)
        if not match:
            return
        value: Any = int(match.group("from"))
        if match.group("to"):
            value = {"from": value, "to": int(match.group("to"))}
        system["fields"]["max_wind"] = Field(
            match.group(0),
            value,
            "kt",
            "maximum sustained surface wind",
        ).to_dict()

    def _extract_abpw_pressure(self, system: dict[str, Any], paragraph: str) -> None:
        match = re.search(r"PRESSURE IS ESTIMATED TO BE NEAR (?P<value>\d{3,4})\s*(?P<unit>MB|HPA)", paragraph, re.I)
        if not match:
            return
        system["fields"]["pressure"] = Field(
            match.group(0),
            int(match.group("value")),
            match.group("unit").lower(),
            "minimum sea-level pressure",
        ).to_dict()

    def _extract_development_potential(self, system: dict[str, Any], paragraph: str) -> None:
        match = re.search(r"WITHIN THE NEXT 24 HOURS REMAINS (?P<value>LOW|MEDIUM|HIGH)", paragraph, re.I)
        if not match:
            return
        system["fields"]["development_potential_24h"] = Field(
            match.group(0),
            match.group("value").upper(),
            meaning="potential for significant tropical cyclone development within 24 hours",
        ).to_dict()

    def _area_status(self, text: str, area_name: str) -> dict[str, str]:
        pattern = rf"{area_name}.*?A\. TROPICAL CYCLONE SUMMARY:\s*(?P<tc>.*?)(?:B\. TROPICAL DISTURBANCE SUMMARY:\s*(?P<dist>.*?))?(?:C\. SUBTROPICAL SYSTEM SUMMARY:\s*(?P<sub>.*?))?(?=\d+\. [A-Z ]+ AREA|//|NNNN|$)"
        match = re.search(pattern, text, re.I)
        if not match:
            return {}
        return {
            "tropical_cyclone": self._clean_status(match.group("tc")),
            "tropical_disturbance": self._clean_status(match.group("dist")),
            "subtropical_system": self._clean_status(match.group("sub")),
        }

    def _clean_status(self, value: str | None) -> str:
        if not value:
            return ""
        value = re.split(r"\(\d+\)\s+THE AREA OF CONVECTION", value, maxsplit=1)[0]
        return value.strip(" .")

    def _abpw_discussion(self, paragraph: str) -> list[str]:
        sentences = [s.strip() for s in re.split(r"(?<=[.])\s+", paragraph) if s.strip()]
        keywords = ("LOCATED", "SATELLITE", "WINDS", "PRESSURE", "POTENTIAL", "ENVIRONMENTAL", "MODELS", "DEVELOPMENT")
        return [sentence for sentence in sentences if any(keyword in sentence.upper() for keyword in keywords)]

    def _abpw_summary(self, parsed: dict[str, Any], systems: list[dict[str, Any]]) -> str:
        heading = parsed.get("heading") or {}
        time = heading.get("issue_time", {}).get("raw", "")
        lines = [f"JTWC issued ABPW10 Significant Tropical Weather Advisory at {time}Z."]
        for system in systems:
            fields = system.get("fields", {})
            position = fields.get("position", {}).get("value")
            wind = fields.get("max_wind", {}).get("value")
            pressure = fields.get("pressure", {}).get("value")
            potential = fields.get("development_potential_24h", {}).get("value")
            parts = [system["identity"]]
            if position:
                parts.append(f"located near {position['lat']} {position['lon']}")
            if wind:
                if isinstance(wind, dict):
                    parts.append(f"maximum sustained wind {wind.get('from')}-{wind.get('to')} kt")
                else:
                    parts.append(f"maximum sustained wind {wind} kt")
            if pressure:
                parts.append(f"minimum sea-level pressure near {pressure} mb")
            if potential:
                parts.append(f"24-hour development potential {potential}")
            lines.append("; ".join(parts) + ".")
        return "\n".join(lines)
