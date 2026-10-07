from typhoon_tac_parser.allowed_reports import classify_report, interpret_allowed_report
from typhoon_tac_parser.prediction import forecast_track


def test_allow_list_ignores_wmo_issue_number():
    raw = "WTPH21 RPMM 011200\nTROPICAL CYCLONE WARNING FOR SHIPPING NR. 01\nTROPICAL DEPRESSION 1004HPA\nAT 1200UTC, PSTN 14.5N 126.5E MOV W 10KT\nMXWD 25KT NEAR CTR="
    result = classify_report(raw)
    assert result["supported"] is True
    assert result["profile"]["ttaa"] == "WTPH"
    assert result["heading"]["ii"] == "21"
    assert result["original_raw"] == raw


def test_unsupported_report_is_not_parsed_or_changed():
    raw = "ASAS RCTP 011200\nTHIS MUST REMAIN RAW"
    result = interpret_allowed_report(raw)
    assert result["supported"] is False
    assert "parsed" not in result
    assert result["original_raw"] == raw
    assert "WTPH RPMM" in result["receive_reminder"]


def test_manual_forecast_has_six_hour_points_and_uncertainty():
    result = forecast_track({
        "current_lat": 15,
        "current_lon": 125,
        "previous_lat": 14.5,
        "previous_lon": 126.5,
        "previous_interval_hours": 6,
        "inertia": 0.65,
        "step_hours": 6,
        "horizon_hours": 24,
        "westerly_south_lat": 20,
        "highs": [],
        "nearby_systems": [],
    })
    assert [point["hour"] for point in result["points"]] == [0, 6, 12, 18, 24]
    assert result["points"][1]["uncertainty_km"] > 0


def test_vhhh_unnamed_low_pressure_form_is_readable():
    raw = """WTSS20 VHHH 041046

TROPICAL CYCLONE WARNING

AN AREA OF LOW PRESSURE HAS INTENSIFIED INTO A TROPICAL DEPRESSION WITH CENTRAL PRESSURE 1000 HECTOPASCALS. AT 040900 UTC, IT WAS CENTRED WITHIN 90 NAUTICAL MILES OF ONE SEVEN POINT FOUR DEGREES NORTH (17.4 N) ONE ONE NINE POINT FOUR DEGREES EAST (119.4 E) AND IS FORECAST TO BE SLOW MOVING FOR THE NEXT 24 HOURS.

MAXIMUM WINDS NEAR THE CENTRE ARE ESTIMATED TO BE 25 KNOTS.
"""
    result = interpret_allowed_report(raw)
    assert result["supported"] is True
    assert result["parsed"]["systems"][0]["fields"]["position"]["value"] == {"lat": 17.4, "lon": 119.4}


def test_vhhh_vicinity_form_supplies_current_position_for_plotting():
    raw = """WTSS20 VHHH 080147

TROPICAL CYCLONE WARNING

AT 080000 UTC, TROPICAL DEPRESSION IN THE VICINITY OF BEIBU
WAN WITH CENTRAL PRESSURE 1000 HECTOPASCALS WAS CENTRED
WITHIN 10 NAUTICAL MILES OF ONE NINE POINT SEVEN DEGREES
NORTH (19.7 N) ONE ZERO EIGHT POINT NINE DEGREES EAST
(108.9 E) AND IS FORECAST TO MOVE EAST-SOUTHEAST AT ABOUT 8
KNOTS FOR THE NEXT 24 HOURS.

MAXIMUM WINDS NEAR THE CENTRE ARE ESTIMATED TO BE 25 KNOTS.

FORECAST POSITION AND INTENSITY AT 090000 UTC

DISSIPATED OVER LAND.
"""
    result = interpret_allowed_report(raw)
    parsed = result["parsed"]

    assert result["supported"] is True
    assert parsed["systems"][0]["fields"]["position"]["value"] == {"lat": 19.7, "lon": 108.9}
    assert parsed["systems"][0]["fields"]["name"]["value"] == "BEIBU WAN"
    assert parsed["forecasts"][0]["status"]["value"] == "陸上消散"
