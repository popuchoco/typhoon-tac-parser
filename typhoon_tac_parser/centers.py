from __future__ import annotations


TROPICAL_CYCLONE_CENTERS = {
    "PHFO": "中太平洋颶風中心",
    "PGTW": "聯合颱風警報中心",
    "RPMM": "菲律賓大氣地球物理與天文服務管理局",
    "BABJ": "中國氣象局",
    "RCTP": "交通部中央氣象署",
    "VHHH": "香港天文台",
    "VMCC": "澳門地球物理氣象局",
    "RKSL": "韓國氣象廳",
    "RJTD": "日本氣象廳",
    "KNES": "NOAA衛星服務部",
    "KNHC": "美國國家氣象局",
    "VTBB": "泰國氣象局",
    "DEMS": "印度氣象局",
    "VVNB": "越南國家水文氣象預報中心",
}


def issuing_agency(center: str | None) -> str:
    if not center:
        return ""
    return TROPICAL_CYCLONE_CENTERS.get(center.upper(), "")
