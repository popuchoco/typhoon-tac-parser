const state = { activeTab: "tac" };
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => document.querySelectorAll(selector);

const elements = {
  tabs: $$(".main-tabs button"),
  tacPanel: $("#tacPanel"),
  reconPanel: $("#reconPanel"),
  bufrPanel: $("#bufrPanel"),
  tacInput: $("#tacInput"),
  reconInput: $("#reconInput"),
  tacOutput: $("#tacOutput"),
  reconOutput: $("#reconOutput"),
  translateTac: $("#translateTac"),
  translateRecon: $("#translateRecon"),
  sampleCwa: $("#sampleCwa"),
  bufrInput: $("#bufrInput"),
  bufrOutput: $("#bufrOutput"),
  dropZone: $("#dropZone"),
  copyResult: $("#copyResult"),
  clearAll: $("#clearAll"),
};

const samples = {
  cwa: `07fW40201
WTCI RCTP 202100 =
WARNING VALID 212100Z =
WARNING IS UPDATED EVERY 3 HOURS =
TROPICAL DEPRESSION DOWNGRADED FROM TROPICAL STORM TALIM 201205 WARNING =
POSITION 202100Z AT  TWO SEVEN POINT ONE NORTH ( 27.1N )  ONE TWO THREE POINT TWO EAST ( 123.2E ) =
MOVEMENT NEXT 12HRS NE 43KM/HR
MIN SURFACE PRESSURE 1000 HPA =
MAX SUSTAINED WINDS NEAR CENTER 15 METER PER SECOND GUST 23 METER PER SECOND =
RADIUS OF OVER 15M/S WINDS - KM =
FORECAST POSITION =
12HRS VALID AT 210900Z AT THREE ZERO POINT FOUR NORTH ( 30.4N ) ONE TWO SIX POINT NINE EAST ( 126.9E )=`,
};

function switchTab(tab) {
  state.activeTab = tab;
  elements.tabs.forEach((button) => button.classList.toggle("active", button.dataset.tab === tab));
  elements.tacPanel.classList.toggle("active", tab === "tac");
  elements.reconPanel.classList.toggle("active", tab === "recon");
  elements.bufrPanel.classList.toggle("active", tab === "bufr");
}

async function translateTac() {
  return translateText(elements.tacInput, elements.tacOutput, "請先貼上 TAC 報文。");
}

async function translateRecon() {
  return translateText(elements.reconInput, elements.reconOutput, "請先貼上偵察或投落送資料。");
}

async function translateText(input, output, emptyText) {
  const raw = input.value.trim();
  if (!raw) return renderEmpty(output, emptyText);
  renderEmpty(output, "解析中...");
  try {
    const response = await fetch("/api/translate-tac", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ raw }),
    });
    if (!response.ok) throw new Error(await response.text());
    renderTacResult(await response.json(), output);
  } catch (error) {
    renderEmpty(output, `解析失敗：${error.message}`);
  }
}

async function decodeBufrFile(file) {
  if (!file) return;
  renderEmpty(elements.bufrOutput, "解析中...");
  try {
    const response = await fetch("/api/decode-bufr", {
      method: "POST",
      headers: {
        "Content-Type": "application/octet-stream",
        "X-Filename": encodeURIComponent(file.name),
      },
      body: await file.arrayBuffer(),
    });
    if (!response.ok) throw new Error(await response.text());
    renderBufrResult(await response.json());
  } catch (error) {
    renderEmpty(elements.bufrOutput, `解析失敗：${error.message}`);
  }
}

function renderTacResult(payload, target = elements.tacOutput) {
  const parsed = payload.parsed || {};
  const root = div("analysis-content");
  root.appendChild(renderBadges(["TAC", payload.center, payload.agency].filter(Boolean)));
  root.appendChild(renderKeyValues("基本資訊", [
    ["報文", payload.title],
    ["機構", payload.agency],
    ["中心", payload.center],
    ["時間", formatTacTime(payload.time)],
    ["類型", translateFamily(parsed.family)],
  ]));

  if (parsed.fields?.human_summary) {
    root.appendChild(renderTextBlock("報文翻譯", translateSummary(parsed.fields.human_summary)));
  }

  if (parsed.family === "metar") renderMetar(root, parsed);
  else if (parsed.family === "agency_auto_dvorak_analysis") renderDvts(root, parsed);
  else if (parsed.family === "dropsonde_temp_drop") renderDropsonde(root, parsed);
  else if (parsed.family === "nhc_tcpod_recon_plan") renderTcpod(root, parsed);
  else renderGenericParsed(root, parsed);

  target.replaceChildren(root);
  target.classList.remove("empty");
}

function renderBufrResult(payload) {
  const parsed = payload.parsed || {};
  const bufr = parsed.bufr || {};
  const validation = parsed.validation || {};
  const root = div("analysis-content");
  root.appendChild(renderBadges(["BUFR", parsed.issuing_center, parsed.issuing_agency, validation.provider].filter(Boolean)));
  root.appendChild(renderKeyValues("基本資訊", [
    ["檔名", payload.filename],
    ["機構", parsed.issuing_agency],
    ["中心", parsed.issuing_center],
    ["報文標頭", parsed.heading?.raw],
    ["時間", formatTacTime(parsed.heading?.issue_time)],
  ]));
  root.appendChild(renderKeyValues("BUFR 結構", [
    ["版本", bufr.edition],
    ["宣告長度", formatValue(bufr.declared_length, "bytes")],
    ["可讀長度", formatValue(bufr.available_length, "bytes")],
    ["Section 2", bufr.section2_present ? "有" : "無"],
    ["7777 結尾", bufr.has_7777_trailer ? "有" : "無"],
    ["解碼狀態", parsed.decoded?.status || validation.status],
    ["ECMWF Validator", validation.eligible_for_upload ? "可上傳驗證" : "不適合上傳"],
  ]));
  if (bufr.sections?.length) {
    root.appendChild(renderTable("BUFR Sections", ["Section", "Offset", "Length"], bufr.sections.map((section) => [
      section.number,
      section.offset,
      section.length,
    ])));
  }
  if (parsed.decoded?.values?.fields?.length) {
    const decoded = parsed.decoded.values;
    root.appendChild(renderTable(decoded.label || "BUFR 解碼欄位", ["欄位", "值"], decoded.fields.map((field) => [
      field.label || field.key,
      formatAny(field.value),
    ])));
  } else if (parsed.decoded?.error) {
    root.appendChild(renderNotice(`BUFR 展開失敗：${parsed.decoded.error}`));
  }
  if (parsed.warnings?.length) root.appendChild(renderNotice(parsed.warnings.join("\n")));
  elements.bufrOutput.replaceChildren(root);
  elements.bufrOutput.classList.remove("empty");
}

function renderMetar(root, parsed) {
  const fields = parsed.fields || {};
  root.appendChild(renderKeyValues("航空天氣資訊", [
    ["測站", formatStation(fields.station)],
    ["觀測時間", formatTacTime(fields.issue_time?.value)],
    ["地面風", formatField(fields.wind)],
    ["能見度", formatVisibility(fields.visibility)],
    ["溫度/露點", formatField(fields.temperature_dewpoint)],
    ["QNH", formatField(fields.qnh)],
    ["趨勢", fields.trend?.value === "NOSIG" ? "無顯著變化" : formatField(fields.trend)],
    ["備註", formatField(fields.remarks)],
  ]));
  if (fields.clouds?.length) {
    root.appendChild(renderTable("雲況", ["雲量", "高度", "型態"], fields.clouds.map((cloud) => [
      translateCloudAmount(cloud.value?.amount),
      cloud.value?.height_ft ? `${cloud.value.height_ft} ft` : "-",
      cloud.value?.type || "-",
    ])));
  }
}

function renderDvts(root, parsed) {
  root.appendChild(renderKeyValues("批次資訊", [
    ["資料類型", "機構自動 Dvorak 分析"],
    ["筆數", parsed.fields?.record_count?.value],
  ]));
  root.appendChild(renderTable("分析列表", ["洋域", "編號", "時間", "位置", "風速", "T/CI", "趨勢", "機構"], (parsed.systems || []).map((system) => {
    const fields = system.fields || {};
    return [
      formatField(fields.basin),
      formatField(fields.storm_number),
      formatField(fields.analysis_time),
      formatPosition(fields.position),
      formatField(fields.wind),
      formatDvorakPair(fields.dvorak),
      formatTrend(fields.trend),
      formatField(fields.issuing_agency) || formatField(fields.issuing_center),
    ];
  })));
}

function renderDropsonde(root, parsed) {
  renderGenericParsed(root, parsed);
  root.appendChild(renderTextBlock("解讀說明", "此區用於 TEMP DROP / XXAA / XXBB 類投落送資料。高度觀測與計算欄位仍需依完整 TEMP 規則逐步補強。"));
}

function renderTcpod(root, parsed) {
  renderGenericParsed(root, parsed);
}

function renderGenericParsed(root, parsed) {
  if (parsed.fields && Object.keys(parsed.fields).length) {
    root.appendChild(renderFieldObject("解析欄位", parsed.fields));
  }
  (parsed.systems || []).forEach((system, index) => {
    const title = index === 0 ? "系統資訊" : `系統資訊 ${index + 1}`;
    root.appendChild(renderKeyValues(title, [
      ["名稱/編號", system.identity],
      ["名稱", system.name],
    ]));
    if (system.fields) root.appendChild(renderFieldObject(`${title}欄位`, system.fields));
    if (system.discussion?.length) root.appendChild(renderTextBlock("備註翻譯", system.discussion.map(translateSummary).join("\n")));
  });
  if (parsed.forecasts?.length) {
    root.appendChild(renderTable("預報位置", ["時距", "有效時間", "位置/狀態", "氣壓", "最大風"], parsed.forecasts.map((forecast) => [
      forecast.tau || forecast.hour || "-",
      formatAny(forecast.valid_time),
      forecast.position ? formatPosition(forecast.position) : formatAny(forecast.status),
      formatField(forecast.pressure),
      formatField(forecast.max_wind),
    ])));
  }
  if (!parsed.fields && !parsed.systems?.length && !parsed.forecasts?.length) {
    root.appendChild(renderNotice("這份報文尚未抽取到可結構化欄位。"));
  }
}

function renderFieldObject(title, fields) {
  return renderKeyValues(title, Object.entries(fields).map(([key, field]) => [translateKey(key), formatAnyField(field)]));
}

function renderBadges(values) {
  const node = div("badges");
  values.forEach((value) => {
    const span = document.createElement("span");
    span.textContent = value;
    node.appendChild(span);
  });
  return node;
}

function renderKeyValues(title, rows) {
  const section = document.createElement("section");
  section.className = "kv-section";
  section.innerHTML = `<h3>${escapeHtml(title)}</h3>`;
  const dl = document.createElement("dl");
  rows.filter(([, value]) => value !== undefined && value !== null && value !== "").forEach(([key, value]) => {
    const dt = document.createElement("dt");
    dt.textContent = key;
    const dd = document.createElement("dd");
    dd.textContent = String(value);
    dl.append(dt, dd);
  });
  section.appendChild(dl);
  return section;
}

function renderTextBlock(title, text) {
  const section = document.createElement("section");
  section.className = "text-section";
  const h3 = document.createElement("h3");
  h3.textContent = title;
  const p = document.createElement("p");
  p.textContent = text || "";
  section.append(h3, p);
  return section;
}

function renderTable(title, headers, rows) {
  const section = document.createElement("section");
  section.className = "table-section";
  const tableRows = rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell ?? "-")}</td>`).join("")}</tr>`).join("");
  section.innerHTML = `<h3>${escapeHtml(title)}</h3><table><thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead><tbody>${tableRows}</tbody></table>`;
  return section;
}

function renderNotice(text) {
  const node = div("notice");
  node.textContent = text;
  return node;
}

function renderEmpty(target, text) {
  target.textContent = text;
  target.classList.add("empty");
}

function currentOutputText() {
  if (state.activeTab === "tac") return elements.tacOutput.innerText;
  if (state.activeTab === "recon") return elements.reconOutput.innerText;
  return elements.bufrOutput.innerText;
}

function formatAnyField(field) {
  if (!field || typeof field !== "object" || !("value" in field)) return formatAny(field);
  return formatValue(field.value, field.unit);
}

function formatField(field) {
  if (!field) return "";
  return formatValue(field.value, field.unit);
}

function formatValue(value, unit) {
  const text = formatAny(value);
  return text && unit ? `${text} ${unit}` : text;
}

function formatAny(value) {
  if (value === undefined || value === null) return "";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(formatAny).filter(Boolean).join(" / ");
  if (typeof value === "object") {
    if ("lat" in value && "lon" in value) return `${value.lat}, ${value.lon} degree`;
    if ("from" in value && "to" in value) return `${value.from}-${value.to}`;
    return Object.entries(value).map(([key, item]) => `${translateKey(key)}: ${formatAny(item)}`).join(", ");
  }
  return String(value);
}

function formatPosition(field) {
  const value = field?.value || field;
  if (!value) return "";
  if (typeof value === "object" && "lat" in value && "lon" in value) return `${value.lat}, ${value.lon} degree`;
  return formatAny(value);
}

function formatTacTime(value) {
  if (!value) return "";
  const time = value.value || value;
  if (typeof time === "string") return time.endsWith("Z") ? time : `${time}Z`;
  if (typeof time === "object") {
    const day = time.day !== undefined ? `${time.day} 日 ` : "";
    const hour = time.hour !== undefined ? String(time.hour).padStart(2, "0") : "";
    const minute = time.minute !== undefined ? String(time.minute).padStart(2, "0") : "";
    if (hour || minute) return `協調世界時 ${day}${hour} 時 ${minute || "00"} 分`;
    if (time.raw) return `${time.raw}Z`;
  }
  return formatAny(time);
}

function formatStation(field) {
  const value = field?.value;
  if (!value || typeof value !== "object") return formatField(field);
  return value.name_zh ? `${value.name_zh} (${value.code})` : value.code;
}

function formatVisibility(field) {
  if (!field) return "";
  if (field.value === 9999) return "10 公里以上";
  return formatField(field);
}

function formatDvorakPair(field) {
  const value = field?.value;
  if (!value) return "";
  if (value.available === false) return "不可用";
  return `T${Number(value.t_number).toFixed(1)} / CI${Number(value.ci_number).toFixed(1)}`;
}

function formatTrend(field) {
  const value = field?.value;
  if (!value) return "";
  if (value.available === false) return "不可用";
  const direction = { developing: "增強", steady: "維持", weakening: "減弱" }[value.direction] || value.direction;
  return `${value.hours} 小時${direction} ${Number(value.change).toFixed(1)}`;
}

function translateFamily(family) {
  const map = {
    dvorak_tropical_satellite_analysis: "熱帶氣旋 Dvorak 衛星分析",
    hebert_poteat_subtropical_analysis: "副熱帶氣旋 Hebert-Poteat 分析",
    knes_dvorak_satellite_analysis: "KNES Dvorak 衛星分析",
    phfo_satellite_fix: "PHFO/CPHC 衛星定位分析",
    metar: "METAR 航空天氣報告",
    dropsonde_temp_drop: "TEMP DROP / XXAA-XXBB 投落送資料",
    nhc_tcpod_recon_plan: "NHC TCPOD 偵察飛行計畫",
    agency_auto_dvorak_analysis: "氣象機構自動 Dvorak 分析",
    babj_numbered_telecode_bulletin: "BABJ 數字電碼報文",
    babj_compact_tropical_cyclone: "BABJ 熱帶氣旋發展報",
    babj_tropical_cyclone: "BABJ 熱帶氣旋報文",
    cwa_tropical_cyclone_warning: "中央氣象署熱帶氣旋警報",
    vhhh_tropical_cyclone_warning: "香港天文台熱帶氣旋警報",
    vmmc_tropical_cyclone_signal: "澳門熱帶氣旋信號",
    tropical_cyclone: "熱帶氣旋報文",
    jtwc_tropical_cyclone: "JTWC 熱帶氣旋報文",
  };
  return map[family] || family || "";
}

function translateKey(key) {
  const map = {
    name: "名稱",
    storm_name: "系統名稱",
    storm_number: "系統編號",
    international_number: "國際編號",
    tc_identifier: "熱帶氣旋識別碼",
    classification: "分類",
    position: "位置",
    pressure: "氣壓",
    max_wind: "最大風",
    gust: "陣風",
    movement: "移動",
    wind_radii: "風圈",
    forecast_positions: "預報位置",
    analysis_time: "分析時間",
    issue_time: "發報時間",
    dvorak_classification: "Dvorak 分類",
    ci_number: "CI number",
    dt_number: "DT number",
    met_number: "MET number",
    pt_number: "PT number",
    final_t_number: "Final T",
    trend_24h: "24h 趨勢",
    imagery: "影像通道",
    remarks: "備註",
  };
  return map[key] || key.replaceAll("_", " ");
}

function translateCloudAmount(value) {
  const map = { FEW: "少雲", SCT: "疏雲", BKN: "裂雲", OVC: "密雲", NSC: "無顯著雲", NCD: "未偵測雲" };
  return map[value] || value || "";
}

function translateSummary(text) {
  if (!text) return "";
  return String(text)
    .replaceAll("CWA/RCTP issued", "中央氣象署/RCTP 發布")
    .replaceAll("Warning valid until", "警報有效至")
    .replaceAll("System:", "系統：")
    .replaceAll("TROPICAL DEPRESSION", "熱帶低壓")
    .replaceAll("TROPICAL STORM", "熱帶風暴")
    .replaceAll("SEVERE TROPICAL STORM", "強烈熱帶風暴")
    .replaceAll("TYPHOON", "颱風")
    .replaceAll("SUPER TYPHOON", "超級颱風")
    .replaceAll("TOO WEAK TO CLASSIFY", "系統過弱，無法分類")
    .replaceAll("FT BASED ON DT", "Final T 依 DT 決定")
    .replaceAll("FT BASED ON PT", "Final T 依 PT 決定")
    .replaceAll("FT BASED ON MET", "Final T 依 MET 決定");
}

function div(className = "") {
  const node = document.createElement("div");
  if (className) node.className = className;
  return node;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[char]));
}

elements.tabs.forEach((button) => button.addEventListener("click", () => switchTab(button.dataset.tab)));
elements.translateTac.addEventListener("click", translateTac);
elements.translateRecon.addEventListener("click", translateRecon);
elements.sampleCwa.addEventListener("click", () => {
  elements.tacInput.value = samples.cwa;
  elements.tacInput.focus();
});
elements.bufrInput.addEventListener("change", (event) => decodeBufrFile(event.target.files[0]));
elements.copyResult.addEventListener("click", () => navigator.clipboard.writeText(currentOutputText()));
elements.clearAll.addEventListener("click", () => {
  elements.tacInput.value = "";
  elements.reconInput.value = "";
  elements.bufrInput.value = "";
  renderEmpty(elements.tacOutput, "等待 TAC 報文輸入。");
  renderEmpty(elements.reconOutput, "等待偵察或投落送資料輸入。");
  renderEmpty(elements.bufrOutput, "等待 BUFR 檔案。");
});

["dragenter", "dragover"].forEach((eventName) => {
  elements.dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropZone.classList.add("active");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  elements.dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropZone.classList.remove("active");
  });
});

elements.dropZone.addEventListener("drop", (event) => decodeBufrFile(event.dataTransfer.files[0]));
