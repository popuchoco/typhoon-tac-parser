import json
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread

from typhoon_tac_parser import MessageParserManager
from typhoon_tac_parser.centers import issuing_agency
from typhoon_tac_parser.dashboard_server import DashboardHandler, MAX_REQUEST_BODY_BYTES


def test_vmmc_is_the_macao_center_code():
    assert issuing_agency("VMMC") == "澳門地球物理氣象局"
    assert issuing_agency("vmmc") == "澳門地球物理氣象局"
    assert issuing_agency("VMCC") == ""


def test_metar_parses_surface_weather_groups():
    parsed = MessageParserManager().parse(
        "METAR RCTP 071200Z 03010G18KT 9999 FEW020 28/23 Q1012 NOSIG="
    )

    assert parsed["family"] == "metar"
    assert parsed["fields"]["station"]["value"]["code"] == "RCTP"
    assert parsed["fields"]["wind"]["value"] == {
        "direction": "030",
        "speed": 10,
        "gust": 18,
    }
    assert parsed["fields"]["visibility"]["value"] == 9999
    assert parsed["fields"]["temperature_dewpoint"]["value"] == {
        "temperature_c": 28,
        "dewpoint_c": 23,
    }


def test_dropsonde_parses_position_and_mandatory_levels():
    raw = "UZPQ01 KNHC 190000\nXXAA 19124 99123 10123 32350 00123 01234 27015 88999"
    parsed = MessageParserManager().parse(raw)

    assert parsed["family"] == "dropsonde_temp_drop"
    assert parsed["fields"]["position"]["value"] == {"lat": 12.3, "lon": 12.3}
    levels = parsed["fields"]["mandatory_levels"]
    assert any(level["value"]["pressure"] == "1000 hPa" for level in levels)
    assert any(level["value"].get("marker") for level in levels)


def _post_dashboard(path: str, body: bytes | None = None, headers: dict[str, str] | None = None):
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    try:
        connection.request(
            "POST",
            path,
            body=body,
            headers=headers or {"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        return response.status, payload
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_dashboard_returns_json_error_for_malformed_request():
    status, payload = _post_dashboard("/api/translate-tac", b"{")

    assert status == 400
    assert "error" in payload


def test_dashboard_validates_json_object_and_raw_text_types():
    status, payload = _post_dashboard("/api/translate-tac", b"[]")
    assert status == 400
    assert "object" in payload["error"]

    status, payload = _post_dashboard("/api/translate-tac", b'{"raw": 123}')
    assert status == 400
    assert "raw must be a string" in payload["error"]


def test_dashboard_rejects_oversized_bufr_request_before_reading_body():
    status, payload = _post_dashboard(
        "/api/decode-bufr",
        headers={
            "Content-Length": str(MAX_REQUEST_BODY_BYTES + 1),
            "Content-Type": "application/octet-stream",
        },
    )

    assert status == 413
    assert "limit" in payload["error"]
