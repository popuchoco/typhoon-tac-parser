from __future__ import annotations

from typing import Any

from .bufr import decode_record_bytes, parse_bufr_envelope
from .normalization import normalize_tac
from .parsers.babj import BabjForecastParser, BabjLandfallParser, BabjWsciParser
from .parsers.base import BaseParser
from .parsers.cwa import CwaWarningParser
from .parsers.dvts import DvtsAutoDvorakParser
from .parsers.dropsonde import DropsondeParser
from .parsers.jtwc import JtwcParser
from .parsers.knes import KnesDvorakParser, PhfoSatelliteFixParser
from .parsers.metar import MetarParser
from .parsers.pgtw import PgtwWarningParser
from .parsers.rpmm import RpmmShippingWarningParser
from .parsers.rksl import RkslKmaAdvisoryParser
from .parsers.rjtd import RjtdGuidanceParser, RjtdTropicalCycloneParser
from .parsers.rjtd_tc_advisory import RjtdTcAdvisoryParser
from .parsers.phfo import PhfoIcaoAdvisoryParser, PhfoTcmcpAdvisoryParser
from .parsers.tropical import TropicalCycloneParser
from .parsers.tppn import TppnSubtropicalParser
from .parsers.tcpod import NhcTcpodParser
from .parsers.vhhh import VhhhTropicalCycloneWarningParser
from .parsers.vmmc import VmmcSignalParser


class MessageParserManager:
    def __init__(self, parsers: list[BaseParser] | None = None):
        self.parsers = parsers or [
            MetarParser(),
            DropsondeParser(),
            NhcTcpodParser(),
            DvtsAutoDvorakParser(),
            CwaWarningParser(),
            BabjWsciParser(),
            BabjLandfallParser(),
            BabjForecastParser(),
            TppnSubtropicalParser(),
            KnesDvorakParser(),
            PhfoSatelliteFixParser(),
            PgtwWarningParser(),
            JtwcParser(),
            RjtdGuidanceParser(),
            RjtdTcAdvisoryParser(),
            RjtdTropicalCycloneParser(),
            PhfoIcaoAdvisoryParser(),
            PhfoTcmcpAdvisoryParser(),
            RpmmShippingWarningParser(),
            RkslKmaAdvisoryParser(),
            VhhhTropicalCycloneWarningParser(),
            VmmcSignalParser(),
            TropicalCycloneParser(),
        ]

    def get_parser(self, code: str) -> BaseParser:
        normalized = normalize_tac(code)
        for parser in self.parsers:
            if parser.supports(normalized):
                return parser
        return self.parsers[-1]

    def parse(self, code: str) -> dict[str, Any]:
        return self.get_parser(code).parse(code)

    def parse_raw_record(self, record: dict[str, Any]) -> dict[str, Any]:
        if record.get("format") == "BUFR" or record.get("raw_base64"):
            parsed = parse_bufr_envelope(decode_record_bytes(record["raw_base64"]))
            parsed["source"] = record.get("source")
            parsed["fetched_at"] = record.get("fetched_at")
            parsed["url"] = record.get("url")
            parsed["content_type"] = record.get("content_type")
            if record.get("issuing_center"):
                parsed["issuing_center"] = record.get("issuing_center")
                parsed["issuing_agency"] = record.get("issuing_agency")
            return parsed
        parsed = self.parse(record["raw"])
        parsed["source"] = record.get("source")
        parsed["fetched_at"] = record.get("fetched_at")
        parsed["url"] = record.get("url")
        return parsed
