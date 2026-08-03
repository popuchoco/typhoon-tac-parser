from __future__ import annotations

import re


WMO_HEADING_RE = re.compile(
    r"^(?P<ttaa>[A-Z]{4})(?P<ii>\d{0,2})\s+"
    r"(?P<center>[A-Z]{4})\s+"
    r"(?P<time>\d{6})(?:[ \t]+(?P<bbb>[A-Z]{3}))?",
    re.MULTILINE,
)


def normalize_tac(raw: str) -> str:
    text = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"^\s*ZCZC\s*", "", text)
    text = re.sub(r"\s*NNNN\s*$", "", text).strip()
    if text.endswith("="):
        text = text[:-1].rstrip()
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def parse_heading(text: str) -> dict[str, str] | None:
    match = WMO_HEADING_RE.search(text)
    if not match:
        return None
    data = match.groupdict()
    return {
        "ttaa": data["ttaa"],
        "ii": data.get("ii") or "",
        "center": data["center"],
        "issue_time": {
            "day": int(data["time"][:2]),
            "hour": int(data["time"][2:4]),
            "minute": int(data["time"][4:6]),
            "timezone": "UTC",
            "raw": data["time"],
        },
        "bbb": data.get("bbb"),
        "raw": match.group(0),
    }


def tokenize(text: str) -> list[str]:
    return re.split(r"\s+", text.strip())
