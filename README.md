# 颱風路徑研究工作台

本專案是供個人研究與繪圖使用的本機工具，整合熱帶氣旋報文解讀、多機構路徑比較、手動座標預測與路徑圖製作。

它不是中央氣象署、日本氣象廳、JTWC 或其他官方機構的預報系統，所有結果都必須由使用者自行判讀與確認。

## 專案定位

工作台分成兩個獨立頁面：

- `plot.html`：報文解讀、多機構路徑比較、手動路徑繪圖。
- `predict.html`：使用者自行填入座標與環境條件的研究用路徑預測。

報文解讀不會自動覆寫座標預測頁面的手動資料，也不會將 ASAS、AUAS、WWJP 等資料自動拆成初始場。

## 主要功能

- 純文字貼上或 `.txt` 上傳報文。
- 只解讀指定白名單，其他報文保留原文並提示不支援。
- 解讀後自動把目前位置與預報位置帶入路徑圖。
- 圖例只顯示機構代碼，例如 `WTCI RCTP` 顯示 `RCTP`。
- 顯示 BABJ、RJTD、PGTW、RCTP 報文中的風圈資料。
- 後續點位沒有新半徑時，沿用上一筆半徑繪製；有新資料時從該點更新。
- 多機構路徑依機構數量自動分色，不限制機構數量。
- 每個區段都可展開、收合、清除與重新載入。
- 路徑可使用調色盤選色，並可下載 PNG／JSON。
- 使用本地 Canvas 與地理資料繪製東亞地圖，不載入 NCDR 圖片。

## 報文白名單

判斷依據為 `TTAA` 類型與機構代碼；`W` 後面的分類編號不影響判斷。

| 報文 | 機構代碼 | 解讀內容 |
| --- | --- | --- |
| `WTPH RPMM` | PAGASA | 海上熱帶氣旋警報 |
| `WTKO RKSL` | KMA | 韓國氣象廳熱帶氣旋報文 |
| `WTCI RCTP` | CWA | 中央氣象署熱帶氣旋警報 |
| `WTSS VHHH` | HKO | 香港天文台熱帶氣旋警報 |
| `WHCI BABJ` | CMA／NMC | 中國氣象局熱帶氣旋登陸資訊 |
| `WTPQ BABJ` | CMA／NMC | 中國氣象局主觀預報 |
| `WTPQ RJTD` | JMA RSMC Tokyo | 日本氣象廳熱帶氣旋預報 |
| `WTPN PGTW` | JTWC／WRNCEN | 聯合颱風警報中心警報 |

RJTD 應使用 `WTPQ RJTD`；`WTPD RJTD` 不在支援範圍。

## 啟動方式

需求：Python 3.10 以上。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m typhoon_tac_parser.dashboard_server 8766
```

啟動後開啟：<http://127.0.0.1:8766/>

停止伺服器請在終端機按 `Ctrl+C`。前端不需要 npm 或其他 JavaScript 套件。

## 操作方式

### 報文解讀／路徑繪圖

開啟 `plot.html` 後，可以：

1. 貼上或上傳指定報文。
2. 按「解讀報文」，查看唯讀解析結果。
3. 在右側路徑圖查看報文目前位置與預報位置。
4. 使用「多機構路徑比較」載入同一颱風的多機構路徑。
5. 使用「手動加入繪圖路徑」增加自行輸入的座標。

多機構純文字可參考 [TYPHOON2000 Multi](https://www.typhoon2000.ph/multi/) 與 [HKWW](https://www.hkww.org/weather/storminfo/index.php) 的資料形式。這類資料不是 WMO TAC，不會改變上方報文白名單。

手動路徑格式：

```text
時效小時, 緯度, 經度
0, 14.5, 126.5
12, 14.8, 125.3
24, 15.2, 124.3
```

### 座標預測

開啟 `predict.html` 後，由使用者自行填入：

- 目前位置與前一位置。
- 初始移動方向／速度或前一時次座標。
- 慣性係數。
- 西風帶最南緯度與引導速度。
- 高壓中心位置、作用半徑與引導速度。
- 鄰近熱帶系統位置、作用半徑與簡化相互作用速度。

產生的路徑是研究用 heuristic，不是官方預報，也不是 DoraBoy V4.01 原始程式的逐行重製。

## 地圖與風圈

- 底圖經度範圍：`101°E–155°E`。
- 底圖緯度範圍：`8°N–38°N`。
- 標示北回歸線：`23.5°N`。
- 包含中央氣象署颱風警報發布區的參考範圍。
- 中國陸地側不另外套用遮罩；實際警戒範圍以報文為準。
- 底圖陸地資料由 Natural Earth 50m land 資料轉製，樣式由本工作台自行繪製。

風圈資料依報文內容繪製：

- BABJ：30KT、50KT、64KT 象限半徑。
- RJTD：例如 30KT／50KT 的南北向半徑。
- PGTW：34KT、50KT 等象限半徑。
- RCTP：`RADIUS OF OVER 15M/S WINDS` 全向半徑。

如果報文只在初始場提供半徑，後續路徑點會沿用該資料以便觀察移動；這不代表官方已發布未來風圈預報。

## HTTP API

本機伺服器提供下列 `POST` 端點，資料格式為 JSON：

| 端點 | 功能 |
| --- | --- |
| `/api/interpret-allowed-report` | 解讀指定白名單報文 |
| `/api/interpret-multi-track` | 解讀多機構純文字路徑 |
| `/api/manual-forecast` | 產生手動研究用路徑 |
| `/api/translate-tac` | 舊介面相容入口，仍套用白名單 |
| `/api/decode-bufr` | 解析 BUFR envelope（上傳上限 10 MiB） |

API 要求使用 `Content-Length`；請求本文上限為 10 MiB。無效 JSON、格式錯誤或超過上限時，伺服器會回傳 JSON 錯誤與對應 HTTP 狀態碼。

## 專案結構

- `dashboard/`：工作台頁面、樣式、前端程式與地圖資產。
- `typhoon_tac_parser/`：Python parser、API server、路徑模型與資料處理。
- `tools/`：地理資料轉換等開發工具。
- `MANUAL_WORKBENCH.md`：工作台操作補充說明。
- `ACKNOWLEDGEMENTS.md`：感謝名單與第三方資料來源。
- `LICENSE`：專案程式碼授權。

## 授權與資料來源

本專案程式碼採用 [MIT License](LICENSE)。

地圖使用的 Natural Earth 資料來源：[Natural Earth 50m Land](https://www.naturalearthdata.com/downloads/50m-physical-vectors/50m-land/)。報文、網站、機構名稱、商標與原始工具的權利不因本專案而轉移，詳見 [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md)。

## 使用限制

- 所有路徑、風圈與強度結果只供研究、比較與繪圖。
- 不可將本工具輸出視為官方警報、官方預報或安全決策依據。
- 報文解析盡量保留原文，但不保證涵蓋所有機構版本與非標準排版。
- 不會自動擷取外部分析報文作為初始場。
