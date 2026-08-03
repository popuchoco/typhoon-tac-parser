from __future__ import annotations

import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from .bufr import parse_bufr_envelope
from .centers import issuing_agency
from .manager import MessageParserManager


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"


def title_from_parsed(parsed: dict) -> str:
    heading = parsed.get("heading") or {}
    if heading.get("ttaa"):
        return f"{heading.get('ttaa', '')}{heading.get('ii', '')} {heading.get('center', '')}".strip()
    return parsed.get("family", "TAC")


def agency_from_parsed(parsed: dict) -> str:
    heading = parsed.get("heading") or {}
    center = parsed.get("issuing_center") or heading.get("center")
    return parsed.get("issuing_agency") or issuing_agency(center)


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD), **kwargs)

    def guess_type(self, path: str) -> str:
        content_type = super().guess_type(path)
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            return f"{content_type}; charset=utf-8"
        return content_type

    def do_POST(self) -> None:
        if self.path == "/api/translate-tac":
            self.translate_tac()
            return
        if self.path == "/api/decode-bufr":
            self.decode_bufr()
            return
        self.send_error(404)

    def translate_tac(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        raw = payload.get("raw", "")
        parsed = MessageParserManager().parse(raw)
        heading = parsed.get("heading") or {}
        issue_time = heading.get("issue_time") or {}
        response = {
            "title": title_from_parsed(parsed),
            "agency": agency_from_parsed(parsed),
            "center": heading.get("center"),
            "time": f"{issue_time.get('raw')}Z" if issue_time.get("raw") else "",
            "parsed": parsed,
        }
        self.write_json(response)

    def decode_bufr(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length)
        parsed = parse_bufr_envelope(data)
        filename = unquote(self.headers.get("X-Filename", "uploaded.bufr"))
        self.write_json({"filename": filename, "parsed": parsed})

    def write_json(self, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
    server = ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler)
    print(f"Serving TAC / BUFR workbench at http://127.0.0.1:{port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
