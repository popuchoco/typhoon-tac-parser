let tracks = [];
let lastReport = null;
let reportTrack = null;
let multiTracks = [];
let centerReports = [];
let centerComparisonTracks = [];
const reportInput = document.querySelector("#reportInput");
const reportFile = document.querySelector("#reportFile");
const reportOutput = document.querySelector("#reportOutput");
const reportStatus = document.querySelector("#reportStatus");
const plotLegend = document.querySelector("#plotLegend");
const multiTrackInput = document.querySelector("#multiTrackInput");
const multiTrackFile = document.querySelector("#multiTrackFile");
const multiTrackStatus = document.querySelector("#multiTrackStatus");
const multiTrackComparison = document.querySelector("#multiTrackComparison");
const trackInput = document.querySelector("#trackInput");
const manualTrackStatus = document.querySelector("#manualTrackStatus");
const centerReportFiles = document.querySelector("#centerReportFiles");
const centerReportLabel = document.querySelector("#centerReportLabel");
const centerReportInput = document.querySelector("#centerReportInput");
const centerReportStatus = document.querySelector("#centerReportStatus");
const centerReportQueue = document.querySelector("#centerReportQueue");
const centerComparisonResult = document.querySelector("#centerComparisonResult");

const MULTI_TRACK_COLORS = ["#2563eb", "#dc2626", "#7c3aed", "#ea580c", "#0891b2", "#16a34a", "#be123c", "#4f46e5"];

function multiTrackColor(index) {
  return MULTI_TRACK_COLORS[index] || `hsl(${(index * 137.508) % 360} 65% 42%)`;
}

function multiTrackCode(track) {
  const rawCode = track?.institution_code || track?.code || track?.name || track?.legend || "多機構";
  return String(rawCode).split("／")[0].trim().toUpperCase();
}

function multiTrackTableLabel(track) {
  const code = multiTrackCode(track);
  const name = String(track?.institution_name || "").trim();
  return name ? `${code}／${name}` : code;
}

function numericValue(field) {
  const value = field?.value ?? field;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function uncertaintyKm(field) {
  const value = numericValue(field);
  if (value === null) return 0;
  const unit = String(field?.unit || "").toLowerCase();
  if (unit === "nm" || unit === "nautical mile" || unit === "nautical miles") return value * 1.852;
  return unit === "km" ? value : 0;
}

function reportWindRadii(fields) {
  const radii = (Array.isArray(fields?.wind_radii) ? fields.wind_radii : [])
    .map((item) => item?.value || item)
    .filter((item) => Number.isFinite(Number(item?.threshold_kt)) && Number.isFinite(Number(item?.radius_km)) && item?.quadrant)
    .map((item) => ({
      threshold_kt: Number(item.threshold_kt),
      threshold_label: `${Number(item.threshold_kt)}KT`,
      radius_km: Number(item.radius_km),
      quadrant: String(item.quadrant).toUpperCase(),
    }));
  const radiusOver15Ms = numericValue(fields?.radius_over_15ms);
  if (radiusOver15Ms !== null && radiusOver15Ms > 0) {
    radii.push({ threshold_label: "15M/S", radius_km: radiusOver15Ms, quadrant: "ALL" });
  }
  return radii;
}

function reportInstitutionCode(result) {
  const profile = result.profile || {};
  const heading = result.heading || result.parsed?.heading || {};
  return String(profile.center || heading.center || "報文機構").trim().toUpperCase();
}

function reportPath(result) {
  const parsed = result.parsed || {};
  const system = (parsed.systems || [])[0] || null;
  const fields = system?.fields || {};
  const points = [];
  let activeWindRadii = reportWindRadii(fields);
  const current = fields.position?.value;
  if (current && Number.isFinite(Number(current.lat)) && Number.isFinite(Number(current.lon))) {
    points.push({
      hour: 0,
      lat: Number(current.lat),
      lon: Number(current.lon),
      uncertainty_km: uncertaintyKm(fields.position_accuracy),
      wind_radii: activeWindRadii,
      kind: "initial",
    });
  }
  (parsed.forecasts || []).forEach((forecast, index) => {
    const position = forecast.position?.value;
    if (!position || !Number.isFinite(Number(position.lat)) || !Number.isFinite(Number(position.lon))) return;
    const lead = numericValue(forecast.lead_time);
    const forecastWindRadii = reportWindRadii(forecast);
    if (forecastWindRadii.length) activeWindRadii = forecastWindRadii;
    points.push({
      hour: lead ?? index + 1,
      lat: Number(position.lat),
      lon: Number(position.lon),
      uncertainty_km: uncertaintyKm(forecast.position_accuracy),
      wind_radii: activeWindRadii,
      kind: "forecast",
    });
  });
  if (!points.length) return null;
  const institution = reportInstitutionCode(result);
  return {
    name: institution || "報文解讀路徑",
    legend: institution || "報文解讀路徑",
    color: "#0f766e",
    source: "report",
    readOnly: true,
    points,
  };
}

function setReportTrack(result) {
  tracks = tracks.filter((track) => track.source !== "report");
  reportTrack = reportPath(result);
  if (reportTrack) tracks.unshift(reportTrack);
  renderTracks();
}

function clearReportTrack() {
  reportTrack = null;
  tracks = tracks.filter((track) => track.source !== "report");
  renderTracks();
}

function clearReportData() {
  clearReportTrack();
  lastReport = null;
  if (reportInput) reportInput.value = "";
  if (reportFile) reportFile.value = "";
  if (reportStatus) reportStatus.textContent = "已清除報文解讀。";
  if (reportOutput) reportOutput.textContent = "解讀結果會顯示在這裡。";
}

function setMultiTracks(result) {
  const decoded = (result.tracks || []).filter((track) => (track.points || []).length);
  multiTracks = decoded.map((track, index) => ({
    ...track,
    legend: multiTrackCode(track),
    color: track.color || multiTrackColor(index),
    source: "multi",
    readOnly: true,
  }));
  tracks = tracks.filter((track) => track.source !== "multi");
  tracks.unshift(...multiTracks);
  renderMultiComparison(multiTracks);
  renderTracks();
}

function clearMultiTracks() {
  multiTracks = [];
  tracks = tracks.filter((track) => track.source !== "multi");
  if (multiTrackInput) multiTrackInput.value = "";
  if (multiTrackFile) multiTrackFile.value = "";
  renderMultiComparison([]);
  renderTracks();
  if (multiTrackStatus) multiTrackStatus.textContent = "已清除多機構路徑。";
}

function renderCenterReportQueue() {
  if (!centerReportQueue) return;
  centerReportQueue.replaceChildren(...centerReports.map((report, index) => {
    const item = document.createElement("div");
    item.className = "track-item";
    const label = document.createElement("span");
    label.textContent = `${report.label}（${report.raw.length.toLocaleString()} 字元）`;
    const button = document.createElement("button");
    button.className = "danger";
    button.type = "button";
    button.textContent = "移除";
    button.addEventListener("click", () => {
      centerReports.splice(index, 1);
      renderCenterReportQueue();
      if (centerReportStatus) centerReportStatus.textContent = `已加入 ${centerReports.length} 份報文。`;
    });
    item.append(label, button);
    return item;
  }));
}

function addCenterReport(label, raw) {
  const cleaned = String(raw || "").trim();
  if (!cleaned) throw new Error("報文內容不可空白。");
  if (centerReports.length >= 20) throw new Error("單次最多加入 20 份報文。");
  centerReports.push({ label: String(label || `第 ${centerReports.length + 1} 份報文`).trim(), raw: cleaned });
  renderCenterReportQueue();
}

function clearCenterComparisonTracks() {
  centerComparisonTracks = [];
  tracks = tracks.filter((track) => track.source !== "center-comparison");
  renderTracks();
}

function comparisonNumber(value, suffix = "") {
  return value === null || value === undefined || !Number.isFinite(Number(value))
    ? "—"
    : `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 })}${suffix}`;
}

function comparisonPosition(position) {
  return position ? formatCoord(position.lat, position.lon) : "—";
}

function comparisonWind(entry) {
  if (entry.max_wind_value === null || entry.max_wind_value === undefined) return "—";
  const source = `${comparisonNumber(entry.max_wind_value)} ${entry.max_wind_unit || ""}`.trim();
  if (entry.max_wind_kt === null || entry.max_wind_kt === undefined) return `${source}（無法換算）`;
  const converted = comparisonNumber(entry.max_wind_kt, " kt");
  const isAlreadyKnots = /^(kt|kts|knot|knots)$/i.test(String(entry.max_wind_unit || "").trim());
  return isAlreadyKnots ? converted : `${converted}（原值 ${source}）`;
}

function comparisonTable(titleText, headers, rows) {
  const wrap = document.createElement("div");
  wrap.className = "table-wrap";
  const title = document.createElement("strong");
  title.textContent = titleText;
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  headers.forEach((header) => {
    const cell = document.createElement("th");
    cell.textContent = header;
    headRow.appendChild(cell);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);
  const body = document.createElement("tbody");
  rows.forEach((values) => {
    const row = document.createElement("tr");
    values.forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value === null || value === undefined || value === "" ? "—" : String(value);
      row.appendChild(cell);
    });
    body.appendChild(row);
  });
  table.appendChild(body);
  wrap.append(title, table);
  return wrap;
}

function renderCenterComparison(result) {
  if (!centerComparisonResult) return;
  const content = [];
  const reports = result.reports || [];
  const currentRows = result.current_comparison || [];
  const columns = [...new Map(currentRows.map((entry) => [entry.column_id, entry])).values()];
  if (columns.length) {
    const metrics = [
      ["報次／發報時間", (entry) => [entry.report_label, entry.issue_time && `${entry.issue_time}Z`].filter(Boolean).join("；")],
      ["目前位置", (entry) => comparisonPosition(entry.position)],
      ["中心氣壓", (entry) => comparisonNumber(entry.pressure_hpa, " hPa")],
      ["最大風速", comparisonWind],
    ];
    content.push(comparisonTable("目前分析並列", ["比較項目", ...columns.map((entry) => entry.column_label)], metrics.map(([label, getter]) => [label, ...columns.map((column) => getter(currentRows.find((entry) => entry.column_id === column.column_id) || {}))])));
  }

  (result.forecast_comparison || []).forEach((group) => {
    const entries = group.entries || [];
    const groupColumns = [...new Map(entries.map((entry) => [entry.column_id, entry])).values()];
    const lead = group.lead_time_hours === null || group.lead_time_hours === undefined ? "時效未辨識" : `${group.lead_time_hours} 小時預報`;
    const rows = [
      ["位置", ...groupColumns.map((column) => comparisonPosition((entries.find((entry) => entry.column_id === column.column_id) || {}).position))],
      ["有效時間", ...groupColumns.map((column) => (entries.find((entry) => entry.column_id === column.column_id) || {}).valid_time || "—")],
      ["中心氣壓", ...groupColumns.map((column) => comparisonNumber((entries.find((entry) => entry.column_id === column.column_id) || {}).pressure_hpa, " hPa"))],
      ["最大風速", ...groupColumns.map((column) => comparisonWind(entries.find((candidate) => candidate.column_id === column.column_id) || {}))],
    ];
    if (groupColumns.length) content.push(comparisonTable(lead, ["預報項目", ...groupColumns.map((entry) => entry.column_label)], rows));
  });

  const status = document.createElement("p");
  status.className = "small";
  const unsupported = reports.filter((report) => !report.supported).map((report) => `${report.label}：${report.reason || "不支援"}`);
  status.textContent = `成功納入 ${result.supported_report_count || 0} 份；收到 ${reports.length} 份報文。${unsupported.length ? ` 未納入：${unsupported.join("；")}` : ""}`;
  content.unshift(status);
  if (result.warnings?.length) {
    const warning = document.createElement("p");
    warning.className = "small bad";
    warning.textContent = result.warnings.join("；");
    content.push(warning);
  }
  if (result.note) {
    const note = document.createElement("p");
    note.className = "small";
    note.textContent = result.note;
    content.push(note);
  }
  centerComparisonResult.replaceChildren(...content);
}

function setCenterComparisonTracks(result) {
  const decoded = (result.map_tracks || []).filter((track) => (track.points || []).length);
  centerComparisonTracks = decoded.map((track, index) => ({
    ...track,
    legend: track.name || track.legend,
    color: multiTrackColor(index),
    source: "center-comparison",
    readOnly: true,
  }));
  tracks = tracks.filter((track) => track.source !== "center-comparison");
  tracks.unshift(...centerComparisonTracks);
  renderTracks();
}

async function compareCenterReports() {
  if (centerReports.length < 2) {
    if (centerReportStatus) centerReportStatus.textContent = "請至少加入兩份報文。";
    return;
  }
  if (centerReportStatus) centerReportStatus.textContent = "正在解析並比較…";
  try {
    const response = await fetch("/api/compare-centers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reports: centerReports }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "多中心比較失敗");
    renderCenterComparison(result);
    setCenterComparisonTracks(result);
    if (centerReportStatus) centerReportStatus.textContent = `比較完成：${result.supported_report_count || 0} 份報文納入表格與地圖。`;
  } catch (error) {
    if (centerReportStatus) centerReportStatus.textContent = `比較失敗：${error.message}`;
  }
}

function clearCenterReports() {
  centerReports = [];
  if (centerReportInput) centerReportInput.value = "";
  if (centerReportFiles) centerReportFiles.value = "";
  if (centerReportLabel) centerReportLabel.value = "貼上報文";
  if (centerReportStatus) centerReportStatus.textContent = "已清除比較報文。";
  if (centerComparisonResult) centerComparisonResult.replaceChildren();
  renderCenterReportQueue();
  clearCenterComparisonTracks();
}

function clearManualTracks() {
  tracks = tracks.filter((track) => track.source !== "manual");
  if (trackInput) trackInput.value = "";
  renderTracks();
  if (manualTrackStatus) manualTrackStatus.textContent = "已清除手動／JSON 路徑。";
}

function renderMultiComparison(trackSet) {
  // Keep the action compatible with a tab that still has an older cached
  // plot.html without the comparison-table container.
  if (!multiTrackComparison) return;
  if (!trackSet.length) {
    multiTrackComparison.replaceChildren();
    return;
  }
  const hours = [...new Set(trackSet.flatMap((track) => track.points.map((point) => Number(point.hour))))]
    .filter(Number.isFinite)
    .sort((a, b) => a - b);
  const table = document.createElement("table");
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["時效", ...trackSet.map(multiTrackTableLabel)].forEach((label) => {
    const cell = document.createElement("th");
    cell.textContent = label;
    headRow.appendChild(cell);
  });
  head.appendChild(headRow);
  table.appendChild(head);
  const body = document.createElement("tbody");
  hours.forEach((hour) => {
    const row = document.createElement("tr");
    const hourCell = document.createElement("td");
    hourCell.textContent = `${hour}H`;
    row.appendChild(hourCell);
    trackSet.forEach((track) => {
      const cell = document.createElement("td");
      const point = track.points.find((candidate) => Number(candidate.hour) === hour);
      if (point) {
        const hasKmH = point.wind_kmh !== null && point.wind_kmh !== undefined && Number.isFinite(Number(point.wind_kmh));
        const hasKt = point.wind_kt !== null && point.wind_kt !== undefined && Number.isFinite(Number(point.wind_kt));
        const hasPressure = point.pressure_hpa !== null && point.pressure_hpa !== undefined && Number.isFinite(Number(point.pressure_hpa));
        const details = [formatCoord(point.lat, point.lon)];
        if (hasKmH) details.push(`${Number(point.wind_kmh)}km/h`);
        if (hasKt) details.push(`(${Number(point.wind_kt)}KT)`);
        if (hasPressure) details.push(`${Number(point.pressure_hpa)}hPa`);
        cell.textContent = details.join(" ");
        cell.setAttribute("aria-label", [point.valid_time, point.category, ...details].filter(Boolean).join("；"));
      } else {
        cell.textContent = "—";
      }
      row.appendChild(cell);
    });
    body.appendChild(row);
  });
  table.appendChild(body);
  const title = document.createElement("strong");
  title.textContent = "多機構時效對照";
  multiTrackComparison.replaceChildren(title, table);
}

function renderLegend() {
  if (!tracks.length) {
    plotLegend.textContent = "尚未解讀報文";
    return;
  }
  plotLegend.replaceChildren(...tracks.map((track) => {
    const item = document.createElement("span");
    item.className = "legend-item";
    const swatch = document.createElement("i");
    swatch.className = "legend-swatch";
    swatch.style.background = track.color || "#d1495b";
    const label = document.createElement("span");
    label.textContent = track.legend || track.name;
    item.append(swatch, label);
    return item;
  }));
}

function renderReport(result) {
  lastReport = result;
  const reminder = `<p class="small">${escapeHtml(result.receive_reminder || "")}</p>`;
  if (!result.supported) {
    clearReportTrack();
    reportStatus.innerHTML = `<span class="bad">未支援：${escapeHtml(result.reason || "未知報文")}</span>`;
    reportOutput.innerHTML = `${reminder}<p class="bad">此報文沒有被解析，也沒有被修改。</p><details><summary>查看原始報文</summary><pre></pre></details>`;
    reportOutput.querySelector("pre").textContent = result.original_raw || reportInput.value;
    return;
  }
  const parsed = result.parsed || {}, system = (parsed.systems || [])[0] || null, fields = system?.fields || {}, position = fields.position?.value, forecasts = parsed.forecasts || [];
  setReportTrack(result);
  const forecastRows = forecasts.map((item) => { const p = item.position?.value; return `<tr><td>${escapeHtml(item.lead_time?.value ?? item.valid_time?.value ?? "-")}</td><td>${p ? escapeHtml(formatCoord(p.lat, p.lon)) : escapeHtml(item.status?.value || "-")}</td></tr>`; }).join("");
  reportStatus.innerHTML = `<span class="good">已解讀：${escapeHtml(result.profile.label)}</span>`;
  reportOutput.innerHTML = `${reminder}<p class="small">${escapeHtml(result.manual_entry_note || "解讀結果僅供參考。")}</p><div class="kv-section"><strong>目前系統</strong><dl><dt>名稱</dt><dd>${escapeHtml(fields.name?.value || system?.identity || "-")}</dd><dt>目前位置</dt><dd>${position ? escapeHtml(formatCoord(position.lat, position.lon)) : "-"}</dd><dt>中心氣壓</dt><dd>${escapeHtml(fields.pressure?.value ?? "-")} ${escapeHtml(fields.pressure?.unit || "")}</dd><dt>最大風速</dt><dd>${escapeHtml(fields.max_wind?.value ?? "-")} ${escapeHtml(fields.max_wind?.unit || "")}</dd></dl></div><div class="table-wrap" style="margin-top:10px"><table><thead><tr><th>預報時效</th><th>位置／狀態</th></tr></thead><tbody>${forecastRows || "<tr><td colspan=2>報文未提供可辨識預報位置</td></tr>"}</tbody></table></div><details style="margin-top:10px"><summary>查看完整唯讀解讀 JSON</summary><pre></pre></details>`;
  reportOutput.querySelector("details pre").textContent = JSON.stringify(parsed, null, 2);
}

async function interpretReport() {
  const raw = reportInput.value;
  if (!raw.trim()) { reportStatus.textContent = "請先貼上或上傳報文。"; return; }
  reportStatus.textContent = "解讀中…";
  try {
    const response = await fetch("/api/interpret-allowed-report", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ raw }) });
    const result = await response.json(); if (!response.ok) throw new Error(result.error || "解讀失敗"); renderReport(result);
  } catch (error) { reportStatus.innerHTML = `<span class="bad">${escapeHtml(error.message)}</span>`; }
}

function parseCoordinateText(text) {
  const points = [];
  for (const [index, line] of text.split(/\r?\n/).entries()) {
    const cleaned = line.trim(); if (!cleaned || cleaned.startsWith("#")) continue;
    const parts = cleaned.split(/[\s,]+/).filter(Boolean); if (parts.length < 3) throw new Error(`第 ${index + 1} 行格式錯誤，應為 時效, 緯度, 經度。`);
    const [hour, lat, lon] = parts.slice(0, 3).map(Number); if (![hour, lat, lon].every(Number.isFinite)) throw new Error(`第 ${index + 1} 行包含非數字。`);
    points.push({ hour, lat, lon });
  }
  if (!points.length) throw new Error("沒有可繪製的座標。"); return points.sort((a, b) => a.hour - b.hour);
}

function addTrack(name, color, points) { tracks.push({ name: name || `路徑 ${tracks.length + 1}`, legend: name || `路徑 ${tracks.length + 1}`, color: color || "#d1495b", source: "manual", points }); renderTracks(); }

function renderTracks() {
  const list = document.querySelector("#trackList");
  list.replaceChildren(...tracks.map((track, index) => { const item = document.createElement("div"); item.className = "track-item"; const sourceLabel = track.source === "multi" ? "多路徑自動帶入" : track.source === "center-comparison" ? "多中心報文自動帶入" : "報文自動帶入"; const removeButton = track.readOnly ? `<span class="small">${sourceLabel}</span>` : "<button class=\"danger\" type=\"button\">移除</button>"; item.innerHTML = `<div class="track-name"><span class="swatch"></span><span>${escapeHtml(track.name)}（${track.points.length} 點）</span></div>${removeButton}`; item.querySelector(".swatch").style.background = track.color; const button = item.querySelector("button"); if (button) button.addEventListener("click", () => { tracks.splice(index, 1); renderTracks(); }); return item; }));
  renderLegend();
  drawTrackMap(document.querySelector("#plotCanvas"), tracks, { showUncertainty: true });
  document.querySelector("#trackJson").textContent = tracks.length ? JSON.stringify({ tracks }, null, 2) : "尚未加入路徑。";
}

document.querySelector("#interpretReport").addEventListener("click", interpretReport);
document.querySelector("#clearReport").addEventListener("click", clearReportData);
document.querySelector("#reportFile").addEventListener("change", async (event) => { const file = event.target.files[0]; if (!file) return; reportInput.value = await file.text(); reportStatus.textContent = `已載入 ${file.name}；請按「解讀報文」。`; });
document.querySelector("#interpretMultiTrack").addEventListener("click", async () => {
  const raw = multiTrackInput.value;
  if (!raw.trim()) { multiTrackStatus.textContent = "請先貼上或上傳多路徑資料。"; return; }
  multiTrackStatus.textContent = "讀取中…";
  try {
    const response = await fetch("/api/interpret-multi-track", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ raw }) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "多路徑讀取失敗");
    if (!result.supported) throw new Error(result.reason || "找不到可繪製的多路徑");
    setMultiTracks(result);
    const warning = result.warnings?.length ? `；${result.warnings.length} 行未解讀` : "";
    multiTrackStatus.textContent = `已載入 ${result.storm_name || "多機構路徑"}：${result.tracks.length} 條路徑${warning}`;
  } catch (error) { multiTrackStatus.innerHTML = `<span class="bad">${escapeHtml(error.message)}</span>`; }
});
document.querySelector("#multiTrackFile").addEventListener("change", async (event) => { const file = event.target.files[0]; if (!file) return; multiTrackInput.value = await file.text(); multiTrackStatus.textContent = `已載入 ${file.name}；請按「載入多路徑」。`; });
document.querySelector("#clearMultiTrack").addEventListener("click", clearMultiTracks);
document.querySelector("#addCenterReport").addEventListener("click", () => {
  try {
    addCenterReport(centerReportLabel?.value, centerReportInput?.value);
    if (centerReportInput) centerReportInput.value = "";
    if (centerReportStatus) centerReportStatus.textContent = `已加入 ${centerReports.length} 份報文。`;
  } catch (error) {
    if (centerReportStatus) centerReportStatus.textContent = error.message;
  }
});
centerReportFiles?.addEventListener("change", async (event) => {
  const files = [...(event.target.files || [])];
  if (centerReports.length + files.length > 20) {
    if (centerReportStatus) centerReportStatus.textContent = "單次最多加入 20 份報文。";
    event.target.value = "";
    return;
  }
  try {
    for (const file of files) addCenterReport(file.name, await file.text());
    if (centerReportStatus) centerReportStatus.textContent = `已加入 ${centerReports.length} 份報文。`;
  } catch (error) {
    if (centerReportStatus) centerReportStatus.textContent = error.message;
  }
});
document.querySelector("#compareCenters").addEventListener("click", compareCenterReports);
document.querySelector("#clearCenterReports").addEventListener("click", clearCenterReports);
document.querySelector("#addTrack").addEventListener("click", () => { try { addTrack(document.querySelector("#trackName").value, document.querySelector("#trackColor").value, parseCoordinateText(trackInput.value)); if (manualTrackStatus) manualTrackStatus.textContent = "已加入手動路徑。"; } catch (error) { if (manualTrackStatus) manualTrackStatus.innerHTML = `<span class="bad">${escapeHtml(error.message)}</span>`; } });
document.querySelector("#clearManualTracks").addEventListener("click", clearManualTracks);
document.querySelector("#forecastFile").addEventListener("change", async (event) => { const file = event.target.files[0]; if (!file) return; try { const data = JSON.parse(await file.text()); const points = (data.points || data.track || []).map((point) => ({ hour: Number(point.hour), lat: Number(point.lat), lon: Number(point.lon), uncertainty_km: Number(point.uncertainty_km || 0) })); addTrack(file.name.replace(/\.json$/i, ""), "#245b9b", points); } catch (error) { reportStatus.innerHTML = `<span class="bad">座標 JSON 匯入失敗：${escapeHtml(error.message)}</span>`; } });
document.querySelector("#downloadTracks").addEventListener("click", () => { if (tracks.length) downloadText("tracks.json", JSON.stringify({ tracks }, null, 2)); });
document.querySelector("#downloadPng").addEventListener("click", () => { const link = document.createElement("a"); link.download = "typhoon_tracks.png"; link.href = document.querySelector("#plotCanvas").toDataURL("image/png"); link.click(); });
function setSectionExpanded(toggle, expanded) {
  const body = document.getElementById(toggle.getAttribute("aria-controls"));
  if (!body) return;
  body.hidden = !expanded;
  toggle.setAttribute("aria-expanded", String(expanded));
  toggle.textContent = expanded ? "收合" : "展開";
  toggle.setAttribute("aria-label", `${expanded ? "收合" : "展開"}${toggle.dataset.sectionName || "區段"}`);
}

const sectionToggles = [...document.querySelectorAll("[data-section-toggle]")];
sectionToggles.forEach((toggle) => {
  setSectionExpanded(toggle, toggle.getAttribute("aria-expanded") !== "false");
  toggle.addEventListener("click", () => {
    setSectionExpanded(toggle, toggle.getAttribute("aria-expanded") !== "true");
  });
});
document.querySelector("#collapseAllSections").addEventListener("click", () => sectionToggles.forEach((toggle) => setSectionExpanded(toggle, false)));
document.querySelector("#expandAllSections").addEventListener("click", () => sectionToggles.forEach((toggle) => setSectionExpanded(toggle, true)));
renderTracks();
