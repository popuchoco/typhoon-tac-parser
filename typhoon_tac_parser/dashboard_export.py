from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .centers import TROPICAL_CYCLONE_CENTERS, issuing_agency
from .manager import MessageParserManager


AGENCY_ORDER = [
    *TROPICAL_CYCLONE_CENTERS.values(),
    "Unknown",
]


def message_title(parsed: dict[str, Any], record: dict[str, Any]) -> str:
    heading = parsed.get("heading") or {}
    if heading.get("ttaa"):
        return f"{heading.get('ttaa', '')}{heading.get('ii', '')} {heading.get('center', '')}".strip()
    if parsed.get("format") == "BUFR":
        center = parsed.get("issuing_center") or record.get("issuing_center") or "UNKNOWN"
        return f"BUFR {center}"
    return record.get("url") or "Untitled"


def message_time(parsed: dict[str, Any]) -> str:
    heading = parsed.get("heading") or {}
    issue_time = heading.get("issue_time") or {}
    raw = issue_time.get("raw")
    if raw:
        return f"{raw}Z"
    return ""


def parse_records(input_path: Path) -> list[dict[str, Any]]:
    manager = MessageParserManager()
    messages = []
    for index, line in enumerate(input_path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        record = json.loads(line)
        if not record.get("raw") and not record.get("raw_base64"):
            continue
        parsed = manager.parse_raw_record(record)
        heading = parsed.get("heading") or {}
        center = parsed.get("issuing_center") or record.get("issuing_center") or heading.get("center")
        agency = parsed.get("issuing_agency") or record.get("issuing_agency") or issuing_agency(center) or "Unknown"
        raw_text = record.get("raw") or ""
        messages.append({
            "id": f"msg-{index + 1}",
            "title": message_title(parsed, record),
            "agency": agency,
            "center": center,
            "family": parsed.get("family"),
            "format": parsed.get("format") or "TAC",
            "time": message_time(parsed),
            "url": record.get("url"),
            "source": record.get("source"),
            "fetched_at": record.get("fetched_at"),
            "raw": raw_text,
            "raw_base64": record.get("raw_base64"),
            "parsed": parsed,
        })
    return messages


def build_dashboard_payload(messages: list[dict[str, Any]]) -> dict[str, Any]:
    agencies = sorted(
        {message["agency"] for message in messages},
        key=lambda agency: (AGENCY_ORDER.index(agency) if agency in AGENCY_ORDER else len(AGENCY_ORDER), agency),
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "agencies": agencies,
        "messages": messages,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export parsed crawler data for the static dashboard.")
    parser.add_argument("--jsonl", required=True, help="Crawler JSONL file.")
    parser.add_argument("--output", default="dashboard/messages.json", help="Dashboard JSON output.")
    args = parser.parse_args()

    messages = parse_records(Path(args.jsonl))
    payload = build_dashboard_payload(messages)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
