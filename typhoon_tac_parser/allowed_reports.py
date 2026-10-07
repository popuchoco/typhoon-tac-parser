"""Strict allow-list handling for the user-facing tropical-cyclone workbench.

The workbench intentionally accepts only the report families in the user-facing
allow-list. Unsupported bulletins are never passed to the general parser and
their original text is returned unchanged for display.
"""

from __future__ import annotations

from typing import Any

from .manager import MessageParserManager
from .normalization import normalize_tac, parse_heading


ALLOWED_REPORTS: tuple[dict[str, str], ...] = (
    {"ttaa": "WTPH", "center": "RPMM", "label": "WTPH RPMM／PAGASA 海上熱帶氣旋警報"},
    {"ttaa": "WTKO", "center": "RKSL", "label": "WTKO RKSL／韓國氣象廳熱帶氣旋報文"},
    {"ttaa": "WTCI", "center": "RCTP", "label": "WTCI RCTP／中央氣象署熱帶氣旋警報"},
    {"ttaa": "WTSS", "center": "VHHH", "label": "WTSS VHHH／香港天文台熱帶氣旋警報"},
    {"ttaa": "WTPQ", "center": "BABJ", "label": "WTPQ BABJ／中國氣象局熱帶氣旋預報"},
    {"ttaa": "WTPQ", "center": "RJTD", "label": "WTPQ RJTD／日本氣象廳 RSMC 熱帶氣旋預報"},
    {"ttaa": "WTPN", "center": "PGTW", "label": "WTPN PGTW／聯合颱風警報中心熱帶氣旋警報"},
    {"ttaa": "WHCI", "center": "BABJ", "label": "WHCI BABJ／中國氣象局熱帶氣旋登陸資訊"},
)

RECEIVE_REMINDER = (
    "請接收以下指定報文：WTPH RPMM、WTKO RKSL、WTCI RCTP、"
    "WTSS VHHH、WTPQ BABJ、WTPQ RJTD、WTPN PGTW。W 後面的兩位數 WMO 分類編號不影響判斷。"
    "支援 WHCI BABJ 熱帶氣旋登陸資訊。"
)


def allowed_report_catalog() -> list[dict[str, str]]:
    return [dict(item) for item in ALLOWED_REPORTS]


def classify_report(raw: str) -> dict[str, Any]:
    """Classify a bulletin without changing the caller's original text."""

    heading = parse_heading(normalize_tac(raw))
    if not heading:
        return {
            "supported": False,
            "reason": "找不到 WMO abbreviated heading。",
            "original_raw": raw,
            "heading": None,
            "receive_reminder": RECEIVE_REMINDER,
            "allowed_reports": allowed_report_catalog(),
        }

    for profile in ALLOWED_REPORTS:
        if heading.get("ttaa") == profile["ttaa"] and heading.get("center") == profile["center"]:
            return {
                "supported": True,
                "profile": dict(profile),
                "heading": heading,
                "original_raw": raw,
                "receive_reminder": RECEIVE_REMINDER,
                "allowed_reports": allowed_report_catalog(),
            }

    return {
        "supported": False,
        "reason": f"不在支援白名單：{heading.get('ttaa', '')}{heading.get('ii', '')} {heading.get('center', '')}",
        "original_raw": raw,
        "heading": heading,
        "receive_reminder": RECEIVE_REMINDER,
        "allowed_reports": allowed_report_catalog(),
    }


def interpret_allowed_report(raw: str) -> dict[str, Any]:
    """Interpret only allow-listed tropical-cyclone bulletins.

    The parsed result is informational.  It is deliberately not converted
    into the manual prediction form, so the user remains responsible for
    reading the report and entering coordinates on the separate page.
    """

    classified = classify_report(raw)
    if not classified["supported"]:
        return classified

    parsed = MessageParserManager().parse(raw)
    classified["parsed"] = parsed
    classified["manual_entry_note"] = (
        "此解讀只供參考，不會自動覆寫座標預測頁面的手動輸入。"
    )
    return classified
