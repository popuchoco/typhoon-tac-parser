from __future__ import annotations


# ICAO location indicators are defined in ICAO Doc 7910.  The RC entries here
# mirror Taiwan CAA eAIP GEN 2.4 so METAR station codes can be shown as places.
ICAO_LOCATION_INDICATORS: dict[str, dict[str, str]] = {
    "RCAA": {"name_zh": "臺北飛航情報區", "name_en": "Taipei FIR", "state": "Taiwan"},
    "RCAY": {"name_zh": "岡山", "name_en": "GANGSHAN", "state": "Taiwan"},
    "RCBS": {"name_zh": "金門", "name_en": "KINMEN", "state": "Taiwan"},
    "RCCM": {"name_zh": "七美", "name_en": "QIMEI", "state": "Taiwan"},
    "RCCS": {"name_zh": "佳山", "name_en": "JIASHAN", "state": "Taiwan"},
    "RCDC": {"name_zh": "屏東南", "name_en": "PINGTUNG SOUTH", "state": "Taiwan"},
    "RCDI": {"name_zh": "龍潭", "name_en": "LONGTAN", "state": "Taiwan"},
    "RCDJ": {"name_zh": "東莒", "name_en": "DONGJYU", "state": "Taiwan"},
    "RCDY": {"name_zh": "東引", "name_en": "DONGYIN", "state": "Taiwan"},
    "RCFG": {"name_zh": "馬祖/南竿", "name_en": "MATSU/NANGAN", "state": "Taiwan"},
    "RCFN": {"name_zh": "臺東/豐年", "name_en": "TAITUNG/FONGNIAN", "state": "Taiwan"},
    "RCFS": {"name_zh": "佳冬", "name_en": "JIADONG", "state": "Taiwan"},
    "RCFZ": {"name_zh": "鳳山", "name_en": "FONGSHAN", "state": "Taiwan"},
    "RCGI": {"name_zh": "綠島", "name_en": "LUDAO", "state": "Taiwan"},
    "RCKH": {"name_zh": "高雄國際", "name_en": "KAOHSIUNG INTL", "state": "Taiwan"},
    "RCKU": {"name_zh": "嘉義", "name_en": "CHIAYI", "state": "Taiwan"},
    "RCKW": {"name_zh": "恆春", "name_en": "HENGCHUN", "state": "Taiwan"},
    "RCLG": {"name_zh": "臺中/水湳", "name_en": "TAICHUNG/SHUEINAN", "state": "Taiwan"},
    "RCLM": {"name_zh": "東沙", "name_en": "DONGSHA", "state": "Taiwan"},
    "RCLS": {"name_zh": "梨山", "name_en": "LISHAN", "state": "Taiwan"},
    "RCLU": {"name_zh": "基隆", "name_en": "KEELUNG", "state": "Taiwan"},
    "RCLY": {"name_zh": "蘭嶼", "name_en": "LANYU", "state": "Taiwan"},
    "RCMJ": {"name_zh": "東港", "name_en": "DONGGANG", "state": "Taiwan"},
    "RCMQ": {"name_zh": "臺中/清泉崗", "name_en": "TAICHUNG/CINGCYUANGANG", "state": "Taiwan"},
    "RCMS": {"name_zh": "宜蘭", "name_en": "YILAN", "state": "Taiwan"},
    "RCMT": {"name_zh": "馬祖/北竿", "name_en": "MATSU/BEIGAN", "state": "Taiwan"},
    "RCNN": {"name_zh": "臺南", "name_en": "TAINAN", "state": "Taiwan"},
    "RCNO": {"name_zh": "東石", "name_en": "DONGSHIH", "state": "Taiwan"},
    "RCPO": {"name_zh": "新竹", "name_en": "HSINCHU", "state": "Taiwan"},
    "RCQC": {"name_zh": "澎湖", "name_en": "PENGHU", "state": "Taiwan"},
    "RCQS": {"name_zh": "臺東/志航", "name_en": "TAITUNG/JHIHHANG", "state": "Taiwan"},
    "RCRA": {"name_zh": "左營", "name_en": "ZUOYING", "state": "Taiwan"},
    "RCSC": {"name_zh": "虎尾", "name_en": "HUWEI", "state": "Taiwan"},
    "RCSJ": {"name_zh": "西莒", "name_en": "SIJYU", "state": "Taiwan"},
    "RCSM": {"name_zh": "日月潭", "name_en": "SUN MOON LAKE", "state": "Taiwan"},
    "RCSP": {"name_zh": "太平", "name_en": "TAIPING", "state": "Taiwan"},
    "RCSQ": {"name_zh": "屏東北", "name_en": "PINGTUNG NORTH", "state": "Taiwan"},
    "RCSS": {"name_zh": "臺北/松山", "name_en": "TAIPEI/SONGSHAN", "state": "Taiwan"},
    "RCTP": {"name_zh": "臺灣桃園國際", "name_en": "TAIPEI/TAIWAN TAOYUAN INTL", "state": "Taiwan"},
    "RCUK": {"name_zh": "八塊", "name_en": "BAKUAI", "state": "Taiwan"},
    "RCWA": {"name_zh": "望安", "name_en": "WANG-AN", "state": "Taiwan"},
    "RCWC": {"name_zh": "烏坵", "name_en": "WUCIOU", "state": "Taiwan"},
    "RCWK": {"name_zh": "新社", "name_en": "SINSHE", "state": "Taiwan"},
    "RCXY": {"name_zh": "歸仁", "name_en": "GUEIREN", "state": "Taiwan"},
    "RCYU": {"name_zh": "花蓮", "name_en": "HUALIEN", "state": "Taiwan"},
}


def lookup_icao_location(indicator: str) -> dict[str, str] | None:
    return ICAO_LOCATION_INDICATORS.get(indicator.upper())
