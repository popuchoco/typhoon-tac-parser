from __future__ import annotations

import argparse
import json
from pathlib import Path

from .bufr import parse_bufr_envelope
from .manager import MessageParserManager


def parse_file(path: Path) -> dict:
    manager = MessageParserManager()
    return manager.parse(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse typhoon/tropical cyclone TAC messages.")
    parser.add_argument("--code", help="Path to a TAC text file.")
    parser.add_argument("--bufr", help="Path to a BUFR binary file.")
    parser.add_argument("--jsonl", help="Path to crawler JSONL records.")
    parser.add_argument("--output", help="Output file. Defaults to stdout.")
    args = parser.parse_args()

    manager = MessageParserManager()
    if args.code:
        payload = parse_file(Path(args.code))
    elif args.bufr:
        payload = parse_bufr_envelope(Path(args.bufr).read_bytes())
    elif args.jsonl:
        payload = []
        for line in Path(args.jsonl).read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record.get("raw") or record.get("raw_base64"):
                payload.append(manager.parse_raw_record(record))
            else:
                payload.append(record)
    else:
        parser.error("Provide --code, --bufr, or --jsonl")

    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
