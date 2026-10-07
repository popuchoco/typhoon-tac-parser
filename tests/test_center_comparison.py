from pathlib import Path

from typhoon_tac_parser.center_comparison import compare_center_reports, MAX_COMPARISON_REPORTS


PGTW = """WTPN33 PGTW 081500
MSGID/GENADMIN/JOINT TYPHOON WRNCEN PEARL HARBOR HI//
SUBJ/TROPICAL STORM 14W (CHAN-HOM) WARNING NR 007//
WARNING POSITION:
081200Z --- NEAR 33.1N 153.2E
MOVEMENT PAST SIX HOURS - 275 DEGREES AT 14 KTS
POSITION ACCURATE TO WITHIN 040 NM
MAX SUSTAINED WINDS - 040 KT, GUSTS 050 KT
FORECASTS:
12 HRS, VALID AT:
090000Z --- 33.0N 151.4E
MAX SUSTAINED WINDS - 040 KT, GUSTS 050 KT
"""

RJTD = """WTPQ50 RJTD 080000
RSMC TROPICAL CYCLONE ADVISORY
NAME  TY 2613 DOLPHIN (2613)
ANALYSIS
PSTN  080000UTC 27.0N 126.1E GOOD
MOVE  NW 06KT
PRES  945HPA
MXWD  085KT
FORECAST
12HF  081200UTC 27.0N 124.9E 25NM 70%
MOVE  W SLOWLY
PRES  950HPA
MXWD  080KT
"""


def test_compare_centers_aligns_positions_wind_pressure_and_forecasts():
    result = compare_center_reports([
        {"label": "JTWC", "raw": PGTW},
        {"label": "JMA", "raw": RJTD},
    ])

    assert result["format"] == "multi_center_tac_comparison"
    assert result["supported_report_count"] == 2
    assert [row["center"] for row in result["current_comparison"]] == ["PGTW", "RJTD"]
    assert result["current_comparison"][0]["position"] == {"lat": 33.1, "lon": 153.2}
    assert result["current_comparison"][0]["max_wind_kt"] == 40
    assert result["current_comparison"][1]["pressure_hpa"] == 945
    assert result["forecast_comparison"][0]["lead_time_hours"] == 12
    assert len(result["forecast_comparison"][0]["entries"]) == 2
    assert len(result["map_tracks"]) == 2


def test_compare_centers_keeps_unsupported_report_out_of_overlay():
    result = compare_center_reports([
        {"label": "JTWC", "raw": PGTW},
        {"label": "unsupported", "raw": "ABCD99 TEST 010000\nnot a supported bulletin"},
    ])

    assert result["supported_report_count"] == 1
    assert result["reports"][1]["supported"] is False
    assert len(result["map_tracks"]) == 1
    assert any("不在支援白名單" in warning for warning in result["warnings"])


def test_compare_centers_validates_report_count_and_raw_text():
    try:
        compare_center_reports([{"label": "one", "raw": PGTW}])
    except ValueError as exc:
        assert "至少要提供兩份" in str(exc)
    else:
        raise AssertionError("expected validation error for one report")

    try:
        compare_center_reports([{"raw": PGTW}] * (MAX_COMPARISON_REPORTS + 1))
    except ValueError as exc:
        assert "最多比較" in str(exc)
    else:
        raise AssertionError("expected validation error for too many reports")

    try:
        compare_center_reports([{"raw": PGTW}, {"raw": "  "}])
    except ValueError as exc:
        assert "非空 raw" in str(exc)
    else:
        raise AssertionError("expected validation error for empty raw")


def test_compare_centers_normalizes_meters_per_second_to_knots():
    babj = """WTPQ20 BABJ 040000
SUBJECTIVE FORECAST
STY DOLPHIN 2613 (2613) INITIAL TIME 040000 UTC
00HR 25.2N 143.2E 945HPA 48M/S
P+12HR 25.3N 140.7E 945HPA 48M/S
"""
    result = compare_center_reports([
        {"label": "BABJ", "raw": babj},
        {"label": "RJTD", "raw": RJTD},
    ])
    babj_row = next(row for row in result["current_comparison"] if row["center"] == "BABJ")

    assert babj_row["max_wind_value"] == 48
    assert babj_row["max_wind_unit"] == "m/s"
    assert babj_row["max_wind_kt"] == 93.3


def test_wmocodebook_is_complete_table_and_contains_representative_entries():
    table_path = Path(__file__).resolve().parents[1] / "typhoon_tac_parser" / "resources" / "wsci40-code-table.json"
    import json

    table = json.loads(table_path.read_text(encoding="utf-8"))
    assert len(table) == 7077
    assert table["0227"] == "倒"
    assert all(len(code) == 4 and code.isdigit() for code in table)
