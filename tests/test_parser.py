from pathlib import Path

from typhoon_tac_parser.bufr import parse_bufr_envelope
from typhoon_tac_parser import MessageParserManager


ROOT = Path(__file__).resolve().parents[1]


def test_babj_forecast_positions_and_intensity():
    parsed = MessageParserManager().parse((ROOT / "examples" / "WTPQ_BABJ.txt").read_text())
    assert parsed["family"] == "babj_tropical_cyclone"
    assert parsed["heading"]["center"] == "BABJ"
    assert len(parsed["forecasts"]) == 2
    assert parsed["forecasts"][0]["position"]["value"] == {"lat": 18.4, "lon": 119.7}
    assert parsed["forecasts"][0]["pressure"]["value"] == 950


def test_jtwc_summary_extracts_system():
    parsed = MessageParserManager().parse((ROOT / "examples" / "ABPW10_PGTW.txt").read_text())
    assert parsed["family"] == "jtwc_tropical_cyclone"
    assert parsed["systems"][0]["identity"] == "31W"
    assert parsed["systems"][0]["fields"]["position"]["value"] == {"lat": 9.8, "lon": 138.9}


def test_vhhh_tropical_cyclone_warning_profile():
    parsed = MessageParserManager().parse((ROOT / "examples" / "VHHH_TROPICAL_CYCLONE_WARNING.txt").read_text())
    assert parsed["family"] == "vhhh_tropical_cyclone_warning"
    assert parsed["heading"]["center"] == "VHHH"
    assert parsed["systems"][0]["identity"] == "SAMPLE"
    assert parsed["systems"][0]["fields"]["position"]["value"] == {"lat": 20.5, "lon": 115.2}


def test_bufr_envelope_classifies_rjtd():
    data = (
        b"IUCC10 RJTD 170000\r\r\n\n"
        b"BUFR\x00\x00\x18\x04"
        b"\x00\x00\x10\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        b"7777"
    )
    parsed = parse_bufr_envelope(data)
    assert parsed["family"] == "bufr"
    assert parsed["heading"]["center"] == "RJTD"
    assert parsed["issuing_agency"] == "日本氣象廳"
    assert parsed["validation"]["provider"] == "ECMWF BUFR Validator"
