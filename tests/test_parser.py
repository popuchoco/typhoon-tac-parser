import json
from pathlib import Path
from types import SimpleNamespace

from typhoon_tac_parser.bufr import _flat_subset_values, _generic_bufr_values, _json_safe, parse_bufr_envelope
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


def test_cwa_initial_wind_radius_is_preserved():
    raw = """WTCI RCTP 071500 =
WARNING VALID 081500Z =
TYPHOON 202613 (DOLPHIN 202613) WARNING =
POSITION 071500Z AT TWO SIX POINT NINE NORTH ( 26.9N ) ONE TWO SIX POINT SIX EAST ( 126.6E ) =
RADIUS OF OVER 15M/S WINDS 280 KM =
FORECAST POSITION =
12HRS VALID AT 080300Z AT TWO SIX POINT NINE NORTH ( 26.9N ) ONE TWO FIVE POINT FOUR EAST ( 125.4E )="""
    parsed = MessageParserManager().parse(raw)
    assert parsed["systems"][0]["fields"]["radius_over_15ms"]["value"] == 280


def test_babj_forecast_wind_radii_are_preserved():
    raw = """WTPQ20 BABJ 040000
SUBJECTIVE FORECAST
STY DOLPHIN 2613 (2613) INITIAL TIME 040000 UTC
00HR 25.2N 143.2E 945HPA 48M/S
30KTS WINDS 360KM NORTHEAST
            280KM SOUTHEAST
            260KM SOUTHWEST
            340KM NORTHWEST
50KTS WINDS 160KM NORTHEAST
            140KM SOUTHEAST
            120KM SOUTHWEST
            160KM NORTHWEST
64KTS WINDS 80KM NORTHEAST
            60KM SOUTHEAST
            60KM SOUTHWEST
            80KM NORTHWEST
P+12HR 25.3N 140.7E 945HPA 48M/S="""
    parsed = MessageParserManager().parse(raw)
    radii = parsed["systems"][0]["fields"]["wind_radii"]

    assert len(radii) == 12
    assert radii[0]["value"] == {
        "threshold_kt": 30,
        "radius_km": 360,
        "quadrant": "NORTHEAST",
    }


def test_rjtd_advisory_parses_analysis_and_forecasts():
    raw = """WTPQ50 RJTD 080000
RSMC TROPICAL CYCLONE ADVISORY
NAME  TY 2613 DOLPHIN (2613)
ANALYSIS
PSTN  080000UTC 27.0N 126.1E GOOD
MOVE  NW 06KT
PRES  945HPA
MXWD  085KT
GUST  120KT
50KT  120NM NORTH 100NM SOUTH
30KT  325NM NORTH 300NM SOUTH
FORECAST
12HF  081200UTC 27.0N 124.9E 25NM 70%
MOVE  W SLOWLY
PRES  950HPA
MXWD  080KT
GUST  115KT
24HF  090000UTC 27.7N 123.2E 35NM 70%
MOVE  WNW 08KT
PRES  950HPA
MXWD  080KT
GUST  115KT
96HF  120000UTC 32.0N 115.4E 100NM 70% TROPICAL DEPRESSION="""
    parsed = MessageParserManager().parse(raw)

    assert parsed["family"] == "rjtd_tropical_cyclone_advisory"
    assert parsed["systems"][0]["fields"]["position"]["value"] == {"lat": 27.0, "lon": 126.1}
    assert parsed["systems"][0]["fields"]["wind_radii"][0]["value"]["radius_nm"] == 120
    assert len(parsed["forecasts"]) == 3
    assert parsed["forecasts"][0]["position"]["value"] == {"lat": 27.0, "lon": 124.9}
    assert parsed["forecasts"][0]["movement"]["value"]["qualifier"] == "SLOWLY"


def test_pgtw_warning_parses_current_forecasts_and_quadrant_radii():
    raw = """WTPN33 PGTW 081500
MSGID/GENADMIN/JOINT TYPHOON WRNCEN PEARL HARBOR HI//
SUBJ/TROPICAL STORM 14W (CHAN-HOM) WARNING NR 007//
WARNING POSITION:
081200Z --- NEAR 33.1N 153.2E
MOVEMENT PAST SIX HOURS - 275 DEGREES AT 14 KTS
POSITION ACCURATE TO WITHIN 040 NM
MAX SUSTAINED WINDS - 040 KT, GUSTS 050 KT
RADIUS OF 034 KT WINDS - 100 NM NORTHEAST QUADRANT
                         000 NM SOUTHEAST QUADRANT
                         080 NM SOUTHWEST QUADRANT
                         100 NM NORTHWEST QUADRANT
FORECASTS:
12 HRS, VALID AT:
090000Z --- 33.0N 151.4E
MAX SUSTAINED WINDS - 040 KT, GUSTS 050 KT
RADIUS OF 034 KT WINDS - 070 NM NORTHEAST QUADRANT
                         040 NM SOUTHEAST QUADRANT
                         080 NM SOUTHWEST QUADRANT
                         090 NM NORTHWEST QUADRANT
"""
    parsed = MessageParserManager().parse(raw)

    assert parsed["family"] == "pgtw_tropical_cyclone_warning"
    assert parsed["systems"][0]["fields"]["position"]["value"] == {"lat": 33.1, "lon": 153.2}
    assert parsed["systems"][0]["fields"]["wind_radii"][0]["value"]["quadrant"] == "NORTHEAST"
    assert len(parsed["forecasts"]) == 1
    assert parsed["forecasts"][0]["position"]["value"] == {"lat": 33.0, "lon": 151.4}
    assert parsed["forecasts"][0]["wind_radii"][2]["value"]["radius_nm"] == 80


def test_babj_whci40_landfall_information_is_parsed():
    raw = """ZCZC
WHCI40 BABJ 280005
TY 2618 (2618) SAUDEL LANDED ON YUHUAN ZHEJIANG PROVINCE
280005GMT (35m/s)
NNNN"""
    parsed = MessageParserManager().parse(raw)
    system = parsed["systems"][0]
    fields = system["fields"]

    assert parsed["family"] == "babj_tropical_cyclone_landfall"
    assert parsed["heading"] == {
        "ttaa": "WHCI",
        "ii": "40",
        "center": "BABJ",
        "issue_time": {
            "day": 28,
            "hour": 0,
            "minute": 5,
            "timezone": "UTC",
            "raw": "280005",
        },
        "bbb": None,
        "raw": "WHCI40 BABJ 280005",
    }
    assert system["identity"] == "SAUDEL"
    assert fields["storm_number"]["value"] == "2618"
    assert fields["classification"]["value"] == "颱風"
    assert fields["landfall_location"]["value"] == {
        "english": "YUHUAN ZHEJIANG PROVINCE",
        "chinese": "浙江省玉環市",
    }
    assert fields["max_wind"]["value"] == 35
    assert fields["max_wind"]["unit"] == "m/s"
    assert parsed["fields"]["landfall_time"]["value"]["raw"] == "280005GMT"
    assert "協調世界時28日00時05分" in parsed["fields"]["human_summary"]


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


def test_bufr_flat_values_preserve_all_subsets():
    flat = [None, None, [11, "00000000", 2], [339, "00000000", [[1, 2], [3, 4]]]]
    assert _flat_subset_values(flat) == [[1, 2], [3, 4]]


def test_generic_bufr_values_are_json_safe_and_keep_descriptor_labels():
    descriptor = SimpleNamespace(
        id=1125,
        F=0,
        X=1,
        Y=125,
        name="WIGOS identifier series",
        unit="Numeric",
    )
    message = SimpleNamespace(
        _template_data=SimpleNamespace(
            value=SimpleNamespace(decoded_descriptors_all_subsets=[[descriptor, None]])
        ),
        is_compressed=SimpleNamespace(value=False),
    )

    decoded = _generic_bufr_values(message, [[b"45011\x00\x00", 12]], [301150, 307096])

    assert decoded["kind"] == "generic_bufr"
    assert decoded["fields"][0]["descriptor"] == "0-01-125"
    assert decoded["fields"][0]["descriptor_name"] == "WIGOS identifier series"
    assert decoded["fields"][0]["value"] == "45011"
    assert decoded["fields"][1]["value"] == 12
    assert _json_safe(b"TAIPA GRANDE\x00\x00") == "TAIPA GRANDE"
    json.dumps(decoded, ensure_ascii=False)
