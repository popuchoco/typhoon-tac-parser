# Typhoon TAC Parser

Typhoon TAC Parser 是一個本機用的氣象報文工作台，目標是把常見熱帶氣旋 TAC、部分航空天氣報、偵察/投落送資料，以及熱帶氣旋 BUFR 轉成較容易閱讀的中文解析結果。

這個專案目前偏向「案例驅動」的解析器：已建立規則的機構與資料類型可以結構化解讀；未列入支援範圍的報文，可能只能讀出 WMO 標頭，或需要人工翻譯與補規則。

## 快速開始

安裝依賴：

```bash
python -m pip install -r requirements.txt
```

啟動本機工作台：

```bash
python -m typhoon_tac_parser.dashboard_server
```

預設服務會顯示在：

```text
http://127.0.0.1:8766/
```

如果該 port 已被使用，可以指定其他 port：

```bash
python -m typhoon_tac_parser.dashboard_server 8820
```

## 工作台功能

### 報文翻譯器

用於貼上 TAC 文字報文並產生中文解析結果。適合已支援的熱帶氣旋警報、Dvorak 衛星分析、BABJ 數字電碼、METAR 等。

注意：`WDPN`、`WTPQ`、`WTPN`、`ABPW` 這類文字產品目前不列為結構化解析支援。它們可由人工翻譯或摘要處理，但不應期待解析器完整拆欄位。

### 偵察 / 投落送

用於 NHC TCPOD 偵察飛行計畫、`XXAA` / `XXBB` TEMP DROP、`UZPQ` / `UZNT` / `UZPA` 類投落送資料。

這一區不與一般熱帶氣旋警報混用，避免把探空資料誤判成颱風警報。

### BUFR 解讀器

用於上傳 `.bufr` 檔。解析器會先讀取：

- WMO binary heading
- BUFR edition
- BUFR declared length
- Section 1 / 3 / 4 基本結構
- `7777` 結尾
- ECMWF BUFR Validator 上傳適用性

若本機有 `pybufrkit` 或 ecCodes 類工具，才有機會進一步展開 BUFR descriptor。沒有 BUFR table 展開工具時，解析器只能保守顯示 envelope 與少量固定欄位。

## 目前可解析的資料範圍

| 資料類型 | 支援機構 / 中心 | 可解析內容 | 限制 |
| --- | --- | --- | --- |
| 熱帶氣旋 TAC 警報 | `RCTP`、`VHHH`、`VMMC`、`RKSL`、`RPMM`、`BABJ` | 基本標頭、機構、中心、時間、系統名稱/編號、定位、氣壓、最大風、移動、風圈與預報位置。 | 目前以西北太平洋與中北太平洋為主；不同機構的特殊欄位仍需逐例補強。 |
| Dvorak / 衛星定位 TAC | `PGTW`、`KNES`、`PHFO` | T/CI、DT/MET/PT、24h 趨勢、短期趨勢、影像通道、定位方式、備註翻譯與分析對象分級。 | 自由文字備註依已建立詞彙翻譯；新句型可能仍會保留英文片段。 |
| 機構自動 Dvorak 一行式 | `PGTW`、`KNES`、`DEMS`、`RCTP`、`RJTD` 等行尾機構碼 | 洋域、氣旋編號、時間、位置、風速、T/CI、D/S/W 趨勢與發報單位；支援多行批次轉換。 | 只支援已知欄位順序的 `DVTS` 類型。 |
| BABJ 數字電碼 / TC 發展報 | `BABJ` | `WSCI40` 中文電碼、`TCPQ40` 位置、CI 強度、過去移動、雲型/發展碼與多系統列表。 | 未知四位碼會列為未解析；完整語義依電碼表覆蓋度而定。 |
| METAR | ICAO 機場代碼 | 測站、ICAO 機場對照、觀測時間、風、能見度、雲、溫度/露點、QNH、趨勢與備註。 | 目前不是完整航空氣象電碼總解碼器；特殊天氣組仍需補規則。 |
| 偵察 / 投落送 | `KNHC`、`RJTD`、`RCTP` 等已見格式 | NHC TCPOD 飛行計畫、`UZPQ` / `UZNT` / `UZPA` 類 `XXAA` / `XXBB` TEMP DROP、`61616` / `62626` 附加資訊、基本垂直層資料。 | 高度觀測/計算欄位尚非完整 TEMP 解碼；不應與一般颱風警報混用。 |
| 熱帶氣旋 BUFR | `VHHH`、`RJTD` 及已辨識熱帶氣旋 BUFR 標頭 | BUFR envelope、WMO binary heading、中心/機構、時間、部分熱帶氣旋與 Dvorak 欄位。 | 只宣稱熱帶氣旋相關 BUFR 基本解讀；不支援所有 BUFR 模板。 |
| 不支援的文字產品 | `WDPN`、`WTPQ`、`WTPN`、`ABPW` | 可協助人工翻譯或摘要。 | 不列為結構化解析支援；預報理由與展望報文格式變化大。 |

## 常用熱帶氣旋機構代碼

| 代碼 | 機構 |
| --- | --- |
| `PHFO` | 中太平洋颶風中心 |
| `PGTW` | 聯合颱風警報中心 |
| `RPMM` | 菲律賓大氣地球物理與天文服務管理局 |
| `BABJ` | 中國氣象局 |
| `RCTP` | 交通部中央氣象署 |
| `VHHH` | 香港天文台 |
| `VMMC` | 澳門地球物理氣象局 |
| `RKSL` | 韓國氣象廳 |
| `RJTD` | 日本氣象廳 |
| `KNES` | NOAA 衛星服務部 |
| `VTBB` | 泰國氣象局 |
| `DEMS` | 印度氣象局 |
| `KNHC` | 美國國家氣象局 / 國家颶風中心相關報文中心 |

## CLI 用法

解析單一 TAC 檔：

```bash
python -m typhoon_tac_parser.cli --code examples/VHHH_TROPICAL_CYCLONE_WARNING.txt
```

解析 BUFR 檔：

```bash
python -m typhoon_tac_parser.cli --bufr path/to/message.bufr
```

爬取資料並輸出 JSONL：

```bash
python -m typhoon_tac_parser.crawler --output data/raw_bulletins.jsonl
```

解析 JSONL 並輸出 JSON：

```bash
python -m typhoon_tac_parser.cli --jsonl data/raw_bulletins.jsonl --output data/parsed_bulletins.json
```

指定單一 URL：

```bash
python -m typhoon_tac_parser.crawler --url https://www.metoc.navy.mil/jtwc/products/abpwweb.txt
```

產生 dashboard 靜態資料：

```bash
python -m typhoon_tac_parser.dashboard_export --jsonl data/raw_bulletins.jsonl --output dashboard/messages.json
```

## 專案結構

| 路徑 | 用途 |
| --- | --- |
| `typhoon_tac_parser/dashboard_server.py` | 本機工作台 HTTP server 與 API。 |
| `dashboard/` | 前端頁面、樣式與互動邏輯。 |
| `typhoon_tac_parser/manager.py` | 根據標頭與內容選擇合適 parser。 |
| `typhoon_tac_parser/parsers/` | 各資料類型與機構的 TAC parser。 |
| `typhoon_tac_parser/bufr.py` | BUFR envelope 與熱帶氣旋 BUFR 基本解讀。 |
| `typhoon_tac_parser/centers.py` | 熱帶氣旋機構代碼對照。 |
| `typhoon_tac_parser/icao_locations.py` | ICAO 機場代碼對照，用於 METAR。 |
| `typhoon_tac_parser/resources/wsci40-code-table.json` | BABJ WSCI40 數字電碼表。 |
| `examples/` | 範例報文。 |
| `tests/` | 自動測試。 |

## 驗證與測試

執行測試：

```bash
python -m pytest
```

GitHub Actions 會在 push 與 pull request 時執行同一組測試。舊版每小時自動爬取報文的 workflow 已移除，避免 repository 自動產生資料變更。

如果本機沒有 `pytest`，可以先做語法檢查：

```bash
python -m py_compile typhoon_tac_parser/dashboard_server.py
```

## 解析原則

- TAC 中的 `/` 代表缺測或無法觀測，不應當成解析失敗。
- 報文時間一律視為 UTC，除非原文另有明確說明。
- 對未支援格式不硬猜；應顯示基本標頭、警告或未解析欄位。
- BUFR 若缺少 table 展開工具，應只宣稱 envelope 與已知固定欄位解讀。
- 新機構或新報文樣式應以範例驅動新增 parser 與測試。

## 授權

本專案採用 MIT License。詳見 [LICENSE](LICENSE)。
