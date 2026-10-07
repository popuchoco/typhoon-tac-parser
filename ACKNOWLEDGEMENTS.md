# 感謝名單

本專案是在公開報文、既有工具經驗與使用者回饋的基礎上整理而成，特別感謝：

- DoraBoy／PTT 大氣版 `TY_RESEARCH`：提供早期颱風路徑研究工具與文件參考。本專案沒有重新發布原始執行檔，也不宣稱擁有 DoraBoy 的原始碼或完整原始公式。
- krichard2011／台灣颱風論壇 `TWTYBBS`：提供颱風路徑填寫與多機構比較工作流程的參考。本專案沒有重新發布 `TTC.exe` 或論壇表單資料流。
- 中央氣象署、香港天文台、日本氣象廳、韓國氣象廳、中國氣象局、聯合颱風警報中心及其他報文發布機構：公開報文格式、機構代碼與熱帶氣旋資訊是本工具解讀介面的參考來源。
- Natural Earth：本地東亞底圖使用 Natural Earth 1:50m land 資料轉製，資料來源與下載頁面列於 [Natural Earth 50m Land](https://www.naturalearthdata.com/downloads/50m-physical-vectors/50m-land/)。
- 使用者測試與回報者：協助發現圖例機構代碼、地圖比例、警報參考區、風圈沿路徑移動及介面文字等問題。

## 外部資料與授權

- `typhoon_tac_parser/resources/wsci40-code-table.json` 的完整 WSCI40 外部電碼表，沿用 [RicoloveFeng/typhoon_parser](https://github.com/RicoloveFeng/typhoon_parser) 的 [`telecode/code.json`](https://github.com/RicoloveFeng/typhoon_parser/blob/main/telecode/code.json)。本專案所含檔案與該來源檔案一致；該專案以 MIT License 發布，著作權聲明為 Copyright (c) 2025 RicoloveFeng。此資料檔依該授權使用與再散布；其 MIT 授權聲明如下：

  ```text
  MIT License

  Copyright (c) 2025 RicoloveFeng

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in all
  copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
  SOFTWARE.
  ```

  This notice applies to the WSCI40 code-table data above, not automatically to other third-party datasets, bulletin text, maps, or services.

本專案的程式碼以根目錄 [LICENSE](LICENSE) 的 MIT License 發布。各機構的報文、網站、商標、原始資料與外部服務仍受其各自條款或權利限制；使用前請遵守來源網站與資料發布機構的規範。
