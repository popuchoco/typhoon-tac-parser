from typhoon_tac_parser.multi_track import interpret_multi_track


def test_multi_agency_track_file_keeps_each_agency_separate():
    raw = """TROPICAL CYCLONE NOUL
(2026-07-24 22:00:43 UTC)
==========================
HKO:
241800Z 20.0N 119.4E 59KT
(+024H) 22.5N 115.3E 78KT
JMA:
241800Z 20.0N 119.3E 55KT
(+048H) 24.8N 113.1E ---KT
"""
    result = interpret_multi_track(raw)

    assert result["supported"] is True
    assert result["storm_name"] == "NOUL"
    assert [track["name"] for track in result["tracks"]] == ["HKO", "JMA"]
    assert result["tracks"][0]["legend"] == "HKO／香港天文台"
    assert result["tracks"][0]["points"][1]["hour"] == 24
    assert result["tracks"][1]["points"][1]["wind_kt"] is None


def test_multi_agency_track_accepts_alias_header_and_inline_mapping():
    raw = """TROPICAL CYCLONE TEST
JMA>日本氣象廳
241800Z 20.0N 119.4E 50KT
CMA/NMC:
241800Z 20.0N 119.4E 50KT
"""
    result = interpret_multi_track(raw)

    assert [track["name"] for track in result["tracks"]] == ["JMA", "CMA/NMC"]
    assert result["tracks"][0]["legend"] == "JMA／日本氣象廳"
    assert result["tracks"][1]["legend"] == "CMA/NMC／中國氣象局"


def test_plain_text_table_track_format_parses_agencies_and_optional_fields():
    raw = """Plain text data for tropical cyclone DOLPHIN (International No.: 2613; JTWC No.: 12W)
File generated at 2026/08/08 15:30:49 UTC

HKO - Hong Kong Observatory

Tau     Date/Time   Latitude  Longitude      Category              Wind speed     Pressure
000  2026/08/08 12Z   27.0N     124.8E   Severe Typhoon         155 km/h  (84 kt)  --- hPa
024  2026/08/09 12Z   28.2N     121.3E   Severe Typhoon         155 km/h  (84 kt)  --- hPa

JMA - Japan Meteorological Agency

Tau     Date/Time   Latitude  Longitude      Category              Wind speed     Pressure
000  2026/08/08 12Z   27.0N     124.8E   Severe Typhoon         157 km/h  (85 kt)  945 hPa
072  2026/08/11 12Z   31.3N     115.1E   ---                     -- km/h  (-- kt)  --- hPa

Notes:
1. This is explanatory text and must not become a route.
"""
    result = interpret_multi_track(raw)

    assert result["supported"] is True
    assert result["storm_name"] == "DOLPHIN"
    assert result["issue_time"] == "2026/08/08 15:30:49 UTC"
    assert result["metadata"] == {
        "international_number": "2613",
        "jtwc_number": "12W",
        "generated_at": "2026/08/08 15:30:49 UTC",
    }
    assert result["warnings"] == []
    assert [track["name"] for track in result["tracks"]] == ["HKO", "JMA"]

    hko_point = result["tracks"][0]["points"][0]
    assert hko_point == {
        "hour": 0,
        "valid_time": "2026/08/08 12Z",
        "lat": 27.0,
        "lon": 124.8,
        "category": "Severe Typhoon",
        "wind_kmh": 155.0,
        "wind_kt": 84.0,
        "pressure_hpa": None,
    }
    assert result["tracks"][1]["points"][1]["wind_kt"] is None
