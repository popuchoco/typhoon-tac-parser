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

  const family = parsed.family;
  if (family === "metar") renderMetar(root, parsed);
  else if (family === "dropsonde_temp_drop") renderDropsonde(root, parsed);
  else if (family === "nhc_tcpod_recon_plan") renderTcpod(root, parsed);
  else if (family === "agency_auto_dvorak_analysis") renderDvts(root, parsed);
  else if (family === "knes_dvorak_satellite_analysis" || family === "phfo_satellite_fix") renderKnesDvorak(root, parsed);
  else if (family === "dvorak_tropical_satellite_analysis") renderTppnDvorak(root, parsed);
  else if (family === "hebert_poteat_subtropical_analysis") renderHebertPoteat(root, parsed);
  else if (family === "babj_numbered_telecode_bulletin") renderBabjTelecode(root, parsed);
  else renderTropicalTac(root, parsed);

  target.replaceChildren(root);
  target.classList.remove("empty");
}

function renderMetar(root, parsed) {
  const fields = parsed.fields || {};
  root.appendChild(renderKeyValues("航空天氣資訊", [
    ["測站", formatStation(fields.station)],
    ["英文站名", fields.station?.value?.name_en],
    ["國家/地區", fields.station?.value?.state],
    ["觀測時間", formatTacTime(fields.issue_time?.value || fields.issue_time)],
    ["地面風", formatMetarWind(fields.wind)],
    ["能見度", formatVisibility(fields.visibility)],
    ["溫度/露點", formatTemperature(fields.temperature_dewpoint)],
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
    ["資料類型", "氣象機構自動 Dvorak 分析"],
    ["筆數", parsed.fields?.record_count?.value],
  ]));
  root.appendChild(renderTable("機構分析列表", ["洋域", "編號", "時間", "位置", "風速", "T/CI", "趨勢", "發報單位"], (parsed.systems || []).map((system) => {
    const fields = system.fields || {};
    return [
      formatField(fields.basin),
      formatField(fields.storm_number),
      formatField(fields.analysis_time),
      formatPosition(fields.position),
      formatField(fields.wind),
      formatDvorakPair(fields.dvorak),
      formatTrend(fields.trend),
      [formatField(fields.issuing_agency), formatField(fields.issuing_center)].filter(Boolean).join(" / "),
    ];
  })));
}

function renderKnesDvorak(root, parsed) {
  const system = firstSystem(parsed);
  const fields = system.fields || {};
  const subject = fields.subject?.value || {};
  root.appendChild(renderKeyValues("Dvorak / 衛星分析", [
    ["分析對象", formatSubject(system)],
    ["系統等級", translateSubjectClassification(subject.classification)],
    ["系統編號", subject.id],
    ["系統代碼", subject.code],
    ["觀測時間", formatField(fields.analysis_time)],
    ["定位", formatPosition(fields.position)],
    ["衛星/定位法", formatField(fields.satellite_fix)],
    ["分類", formatDvorakClassification(fields.dvorak_classification)],
    ["影像通道", formatArrayField(fields.imagery)],
  ]));
  appendDiscussion(root, system, "備註翻譯", translateDvorakRemark);
}

function renderTppnDvorak(root, parsed) {
  const system = firstSystem(parsed);
  const fields = system.fields || {};
  const dv = fields.dvorak_classification?.value || {};
  root.appendChild(renderKeyValues("Dvorak / 德法分析", [
    ["分析對象", system.name || system.identity],
    ["觀測時間", formatField(fields.analysis_time)],
    ["定位", formatPosition(fields.position)],
    ["衛星/定位法", formatField(fields.satellite_fix)],
    ["T 判定", dv.raw_code || formatField(fields.dvorak_classification)],
    ["T-number", formatNumber(dv.t_number)],
    ["CI number", formatNumber(dv.ci_number)],
    ["T 對應風速", dv.t_wind_kt ? `${dv.t_wind_kt} kt` : ""],
    ["CI 對應風速", dv.ci_wind_kt ? `${dv.ci_wind_kt} kt` : ""],
    ["24h 趨勢", formatTrendCode(dv.trend_24h)],
    ["短期趨勢", formatTrendCode(dv.short_term_trend)],
    ["附註", translateDvorakNote(dv.note)],
    ["影像通道", formatArrayField(fields.imagery)],
  ]));
  root.appendChild(renderTextBlock("德法結論", dvorakConclusion(dv)));
  appendDiscussion(root, system, "備註翻譯", translateDvorakRemark);
}

function renderHebertPoteat(root, parsed) {
  const system = firstSystem(parsed);
  const fields = system.fields || {};
  const st = fields.st_classification?.value || {};
  root.appendChild(renderKeyValues("Hebert-Poteat / 亞熱帶分析", [
    ["分析對象", system.name || system.identity],
    ["觀測時間", formatField(fields.analysis_time)],
    ["定位", formatPosition(fields.position)],
    ["衛星/定位法", formatField(fields.satellite_fix)],
    ["ST 判定", st.raw_code || formatField(fields.st_classification)],
    ["ST number", formatNumber(st.st_number)],
    ["趨勢數值", formatNumber(st.trend_number)],
    ["雲型對應風速", st.cloud_feature_wind_kt ? `${st.cloud_feature_wind_kt.min}-${st.cloud_feature_wind_kt.max} kt` : ""],
    ["影像通道", formatArrayField(fields.imagery)],
  ]));
  appendDiscussion(root, system, "備註翻譯", translateHebertPoteatRemark);
  root.appendChild(renderTextBlock("判讀說明", "Hebert-Poteat 用於副熱帶氣旋衛星強度分析；ST 數值與 Dvorak T 數值不是同一套分類。"));
}

function renderBabjTelecode(root, parsed) {
  const fields = parsed.fields || {};
  root.appendChild(renderTextBlock("WSCI40 解碼內容", fields.decoded_text?.value || "尚未取得完整中文電碼解讀。"));
  root.appendChild(renderKeyValues("BABJ 電碼資訊", [
    ["收報單位", formatArrayField(fields.recipients)],
    ["電碼組數", fields.group_count?.value],
    ["結尾識別", fields.trailer?.value],
    ["未知碼", formatArrayField(fields.unknown_codes)],
  ]));
  const groups = fields.telecode_groups?.value || [];
  if (groups.length) {
    root.appendChild(renderTable("電碼組", ["序號", "代碼", "附加值", "原始組"], groups.map((group, index) => [
      index + 1,
      group.code || "-",
      group.extra || "-",
      group.raw || "-",
    ])));
  }
}

function renderTropicalTac(root, parsed) {
  const systems = parsed.systems || [];
  if (!systems.length && !(parsed.forecasts || []).length) {
    root.appendChild(renderNotice("這份 TAC 報文尚未抽取到氣旋中心或預報點。"));
    return;
  }

  systems.forEach((system, index) => {
    const fields = system.fields || {};
    root.appendChild(renderKeyValues(index === 0 ? "氣旋資訊" : `氣旋資訊 ${index + 1}`, [
      ["名稱/編號", system.identity],
      ["名稱", formatField(fields.name)],
      ["編號", formatField(fields.storm_number)],
      ["分類", formatField(fields.classification)],
      ["位置", formatPosition(fields.position)],
      ["最大風", formatField(fields.max_wind)],
      ["陣風", formatField(fields.gust)],
      ["氣壓", formatField(fields.pressure)],
      ["移動", formatMovement(fields.movement)],
      ["15 m/s 半徑", formatField(fields.radius_over_15ms)],
      ["發展潛勢", formatField(fields.development_potential_24h)],
    ]));
    renderWindRadii(root, fields.wind_radii);
    if (fields.compact_groups) root.appendChild(renderTextBlock("緊縮碼", formatField(fields.compact_groups)));
    if (fields.cloud_analysis) root.appendChild(renderTextBlock("雲型/發展碼", formatAnyField(fields.cloud_analysis)));
  });

  const forecasts = parsed.forecasts || flatForecasts(systems);
  if (forecasts.length) renderForecasts(root, forecasts);
}

function renderForecasts(root, forecasts) {
  root.appendChild(renderTable("預報位置", ["時距", "有效時間", "位置/狀態", "氣壓", "最大風"], forecasts.map((forecast) => [
    forecast.tau || forecast.hour || forecast.period || "-",
    formatAnyField(forecast.valid_time || forecast.valid_at),
    forecast.position ? formatPosition(forecast.position) : formatAny(forecast.status || forecast.state),
    formatField(forecast.pressure),
    formatField(forecast.max_wind || forecast.wind),
  ])));
}

function renderWindRadii(root, windRadii) {
  if (!windRadii?.length) return;
  root.appendChild(renderTable("風圈半徑", ["風速門檻", "方位/區域", "半徑"], windRadii.map((item) => [
    formatValue(item.threshold || item.wind || item.value?.threshold, item.unit || item.value?.unit),
    translateDirection(item.quadrant || item.area || item.value?.quadrant || item.value?.area),
    formatValue(item.radius || item.value?.radius, item.radius_unit || item.value?.radius_unit),
  ])));
}

function renderDropsonde(root, parsed) {
  const fields = parsed.fields || {};
  root.appendChild(renderKeyValues("TEMP DROP / XXAA-XXBB 投落送資料", [
    ["資料類型", "投落送上空探測資料"],
    ["位置", formatPosition(fields.position)],
    ["TEMP 標頭", formatAnyField(fields.xxaa_header)],
    ["Marsden square", formatAnyField(fields.marsden_square)],
  ]));
  renderSupplementalReports(root, fields.supplemental_reports?.value);
  renderLevelTable(root, "XXAA 標準層", fields.mandatory_levels);
  renderLevelTable(root, "XXBB 特性溫度層", fields.significant_temperature_levels);
  renderLevelTable(root, "XXBB 特性風層", fields.significant_wind_levels);
  renderLevelTable(root, "61616 附加風層", fields.additional_wind_levels);
  if (!fields.supplemental_reports?.value?.length && fields.supplemental?.value?.length) {
    root.appendChild(renderTextBlock("附加資訊", fields.supplemental.value.join("\n")));
  }
}

function renderSupplementalReports(root, reports) {
  if (!reports?.length) return;
  root.appendChild(renderTable("61616 / 62626 附加資訊", ["任務", "OB", "MBL 風", "DLM 風", "釋放點", "落水點", "其他"], reports.map((item) => [
    [item.aircraft, item.mission_id, item.mission_type].filter(Boolean).join(" ") || "-",
    item.observation || "-",
    formatWindObject(item.mean_boundary_layer_wind),
    formatWindObject(item.deep_layer_mean_wind),
    formatFixObject(item.release),
    formatFixObject(item.splash),
    [item.aev ? `AEV ${item.aev}` : "", item.wind_level ? `${item.wind_level.code} ${(item.wind_level.groups || []).join(" ")}` : ""].filter(Boolean).join(" / ") || "-",
  ])));
}

function renderLevelTable(root, title, rows) {
  if (!rows?.length) return;
  root.appendChild(renderTable(title, ["氣壓/標記", "高度組", "氣溫", "露點差", "風"], rows.map((item) => {
    const value = item.value || {};
    return [
      value.pressure_hpa ? `${value.pressure_hpa} hPa` : value.pressure || value.marker || "-",
      value.height_group || "-",
      value.temperature_c === null || value.temperature_c === undefined ? "-" : `${value.temperature_c} °C`,
      value.dewpoint_depression_c === null || value.dewpoint_depression_c === undefined ? "-" : `${value.dewpoint_depression_c} °C`,
      formatWindObject(value),
    ];
  })));
}

function renderTcpod(root, parsed) {
  const fields = parsed.fields || {};
  root.appendChild(renderKeyValues("NHC TCPOD 偵察飛行計畫", [
    ["TCPOD 編號", formatField(fields.tcpod_number)],
    ["有效期間", formatAnyField(fields.valid_period)],
    ["發布時間", formatField(fields.issued_local)],
  ]));
  (parsed.systems || []).forEach((basinSection) => {
    const basin = basinSection.fields?.basin?.value || basinSection.identity || "需求";
    (basinSection.fields?.requirements?.value || []).forEach((requirement) => {
      if (requirement.negative) {
        root.appendChild(renderNotice(`${basin}：無偵察需求。`));
        return;
      }
      root.appendChild(renderTextBlock(`${basin} 需求`, requirement.name));
      if (requirement.flights?.length) {
        root.appendChild(renderTable("飛行任務", ["航班", "機型", "A", "B", "C", "D", "E", "F", "G", "H"], requirement.flights.map((flight) => [
          flight.label,
          flight.aircraft,
          flight.fields?.A || "-",
          flight.fields?.B || "-",
          flight.fields?.C || "-",
          flight.fields?.D || "-",
          flight.fields?.E || "-",
          flight.fields?.F || "-",
          flight.fields?.G || "-",
          flight.fields?.H || "-",
        ])));
      }
    });
    const outlook = basinSection.fields?.outlook?.value || [];
    if (outlook.length) root.appendChild(renderTextBlock(`${basin} 後續展望`, outlook.join("\n")));
  });
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
    root.appendChild(renderDecodedBufr(decoded));
  } else if (parsed.decoded?.error) {
    root.appendChild(renderNotice(`BUFR 展開失敗：${parsed.decoded.error}`));
  }
  if (parsed.warnings?.length) root.appendChild(renderNotice(parsed.warnings.join("\n")));
  elements.bufrOutput.replaceChildren(root);
  elements.bufrOutput.classList.remove("empty");
}

function renderDecodedBufr(decoded) {
  const fields = decoded.fields || [];
  const get = (key) => fields.find((item) => item.key === key)?.value;
  const section = div();
  section.appendChild(renderKeyValues(decoded.label || "熱帶氣旋 BUFR 解碼", [
    ["系統名稱", get("storm_name")],
    ["國際編號", get("international_number")],
    ["熱帶氣旋識別碼", get("tc_identifier")],
    ["資料時間", `${get("year") || ""}-${get("month") || ""}-${get("day") || ""} ${String(get("hour") ?? "").padStart(2, "0")}:${String(get("minute") ?? "").padStart(2, "0")} UTC`],
    ["衛星 ID", get("satellite_identifier")],
    ["位置", get("latitude") !== undefined && get("longitude") !== undefined ? `${get("latitude")}, ${get("longitude")} degree` : ""],
    ["移動", get("motion_direction_degree") !== undefined ? `${get("motion_direction_degree")}° / ${get("motion_speed")}` : ""],
    ["定位精度碼", get("position_accuracy_code")],
    ["雲區直徑碼", get("overcast_cloud_diameter_code")],
    ["24h 強度變化碼", get("intensity_change_24h_code")],
  ]));
  section.appendChild(renderKeyValues("Dvorak / 衛星強度", [
    ["CI number", get("ci_number")],
    ["DT number", get("dt_number")],
    ["DT 雲型碼", get("dt_cloud_pattern_type")],
    ["MET number", get("met_number")],
    ["24h 趨勢", formatAny(get("trend_24h_code")?.text || get("trend_24h"))],
    ["PT number", get("pt_number")],
    ["PT 雲圖型態碼", get("pt_cloud_picture_type")],
    ["Final T", get("final_t_number")],
    ["Final T 型態碼", get("final_t_type")],
  ]));
  section.appendChild(renderTable("BUFR 原始解碼欄位", ["欄位", "值"], fields.map((field) => [
    field.label || field.key,
    formatAny(field.value),
  ])));
  return section;
}

function firstSystem(parsed) {
  return (parsed.systems || [])[0] || {};
}

function appendDiscussion(root, system, title, translator) {
  if (!system.discussion?.length) return;
  root.appendChild(renderTextBlock(title, system.discussion.map((line) => translator ? translator(line) : line).join("\n")));
}

function flatForecasts(systems) {
  return systems.flatMap((system) => system.forecasts || system.fields?.forecasts?.value || []);
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

function formatMetarWind(field) {
  const value = field?.value;
  if (!value || typeof value !== "object") return formatField(field);
  const direction = value.direction === "VRB" ? "風向不定" : `${value.direction} 度`;
  const gust = value.gust ? `，陣風 ${value.gust} ${field.unit || ""}` : "";
  return `${direction}，風速 ${value.speed} ${field.unit || ""}${gust}`;
}

function formatVisibility(field) {
  if (!field) return "";
  if (field.value === 9999) return "10 公里以上";
  return formatField(field);
}

function formatTemperature(field) {
  const value = field?.value;
  if (!value || typeof value !== "object") return formatField(field);
  return `${value.temperature_c} / ${value.dewpoint_c} °C`;
}

function formatMovement(field) {
  const value = field?.value;
  if (!value || typeof value !== "object") return formatField(field);
  const unit = field.unit ? ` ${field.unit}` : "";
  const parts = [];
  if (value.period_hours) parts.push(`未來 ${value.period_hours} 小時`);
  if (value.direction) parts.push(`向${translateDirection(value.direction)}移動`);
  if (value.speed !== undefined) parts.push(`速度 ${value.speed}${unit}`);
  if (value.becoming_direction) parts.push(`之後轉向${translateDirection(value.becoming_direction)}`);
  if (value.becoming_speed !== undefined) parts.push(`速度 ${value.becoming_speed}${unit}`);
  return parts.join("，");
}

function formatDvorakPair(field) {
  const value = field?.value;
  if (!value) return "";
  if (value.available === false) return "不可用";
  return `T${Number(value.t_number).toFixed(1)} / CI${Number(value.ci_number).toFixed(1)}`;
}

function formatDvorakClassification(field) {
  const value = field?.value;
  if (!value || typeof value !== "object") return formatField(field);
  if (value.raw_code) return value.raw_code;
  if (value.available === false) return "系統過弱，無法分類";
  return formatAny(value);
}

function formatTrend(field) {
  const value = field?.value;
  if (!value) return "";
  if (value.available === false) return "不可用";
  const direction = { developing: "增強", steady: "維持", weakening: "減弱" }[value.direction] || value.direction;
  return `${value.hours} 小時${direction} ${Number(value.change).toFixed(1)}`;
}

function formatTrendCode(trend) {
  if (!trend) return "";
  return `${trend.code}${trend.value} / ${trend.period} (${trendText(trend)})`;
}

function trendText(trend) {
  if (trend.direction === "developing") return "增強";
  if (trend.direction === "weakening") return "減弱";
  if (trend.direction === "steady") return "維持";
  return "未知";
}

function dvorakConclusion(dv) {
  const ftWind = dv.t_wind_kt ? `<${dv.t_wind_kt} kt` : "未知";
  const ciWind = dv.ci_wind_kt ? `<${dv.ci_wind_kt} kt` : "未知";
  const trend24 = dv.trend_24h ? `${trendText(dv.trend_24h)} (${dv.trend_24h.code}${dv.trend_24h.value})` : "未標示";
  const trendShort = dv.short_term_trend ? `${trendText(dv.short_term_trend)} (${dv.short_term_trend.code}${dv.short_term_trend.value})` : "未標示";
  return `FT ${dv.t_number ?? "-"} (${ftWind})，CI ${dv.ci_number ?? "-"} (${ciWind})，24 小時趨勢為${trend24}，短期趨勢為${trendShort}。`;
}

function formatArrayField(field) {
  const value = field?.value ?? field;
  return Array.isArray(value) ? value.join(" / ") : formatAny(value);
}

function formatNumber(value) {
  return value === undefined || value === null ? "" : String(value);
}

function formatSubject(system) {
  const subject = system.fields?.subject?.value;
  if (subject?.raw && subject?.classification) {
    return subject.raw.replace(subject.classification, translateSubjectClassification(subject.classification));
  }
  if (!system.identity || system.identity === system.name) return system.name || system.identity || "";
  return `${system.name || ""} (${system.identity})`;
}

function formatWindObject(wind) {
  if (!wind) return "-";
  if (wind.wind_direction_degree === null || wind.wind_direction_degree === undefined) return "-";
  return `${wind.wind_direction_degree}° / ${wind.wind_speed_kt} kt`;
}

function formatFixObject(fix) {
  if (!fix) return "-";
  if (fix.lat === null || fix.lat === undefined || fix.lon === null || fix.lon === undefined) {
    return [fix.raw, fix.time].filter(Boolean).join(" ") || "-";
  }
  return `${formatCoordinate(fix.lat, "lat")} ${formatCoordinate(fix.lon, "lon")} ${fix.time || ""}`.trim();
}

function formatCoordinate(value, axis) {
  const hemi = axis === "lat" ? (value >= 0 ? "N" : "S") : (value >= 0 ? "E" : "W");
  return `${Math.abs(value).toFixed(2).replace(/\.?0+$/, "")}${hemi}`;
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
    rpmm_tropical_cyclone_warning: "PAGASA 航海熱帶氣旋警報",
    rksl_tropical_cyclone_advisory: "韓國氣象廳熱帶氣旋報文",
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

function translateSubjectClassification(value) {
  const map = {
    "TROPICAL DISTURBANCE": "熱帶擾動",
    "TROPICAL DEPRESSION": "熱帶低壓",
    "TROPICAL STORM": "熱帶風暴",
    "SUBTROPICAL DISTURBANCE": "副熱帶擾動",
    "SUBTROPICAL DEPRESSION": "副熱帶低壓",
    HURRICANE: "颶風",
    TYPHOON: "颱風",
  };
  return map[String(value || "").toUpperCase()] || value || "";
}

function translateDirection(direction) {
  const map = {
    N: "北",
    NNE: "北北東",
    NE: "東北",
    ENE: "東北東",
    E: "東",
    ESE: "東南東",
    SE: "東南",
    SSE: "南南東",
    S: "南",
    SSW: "南南西",
    SW: "西南",
    WSW: "西南西",
    W: "西",
    WNW: "西北西",
    NW: "西北",
    NNW: "北北西",
    NORTH: "北",
    NORTHERN: "北側",
    NORTHEAST: "東北",
    EAST: "東",
    EASTERN: "東側",
    SOUTHEAST: "東南",
    SOUTH: "南",
    SOUTHERN: "南側",
    SOUTHWEST: "西南",
    WEST: "西",
    WESTERN: "西側",
    NORTHWEST: "西北",
    "WEST-NORTHWEST": "西北西",
    "NORTHERN SEMICIRCLE": "北半圓",
    "EASTERN SEMICIRCLE": "東半圓",
    ELSEWHERE: "其他區域",
    ALL: "全象限",
  };
  return map[String(direction || "").toUpperCase()] || direction || "";
}

function translateDvorakNote(note) {
  const map = {
    "INITIAL FIX": "初始定位",
    "INIT OBS": "初始觀測",
  };
  return map[String(note || "").toUpperCase()] || note || "";
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

function translateDvorakRemark(text) {
  if (!text) return "";
  return translateSummary(String(text))
    .replaceAll("REMARKS...", "")
    .replaceAll("REMARKS:", "")
    .replaceAll("CNVCTN WRAPS", "對流纏繞")
    .replaceAll("CONVECTION WRAPS", "對流纏繞")
    .replaceAll("ON LOG10 SPIRAL", "於 log10 螺旋")
    .replaceAll("YIELDING A DT OF", "得出 DT")
    .replaceAll("YIELDS A DT OF", "得出 DT")
    .replaceAll("BANDING YIELDS A DT OF", "雲帶型態得出 DT")
    .replaceAll("THE MET AND PT ARE", "MET 與 PT 為")
    .replaceAll("MET AND PT AGREE", "MET 與 PT 一致")
    .replaceAll("PT AGREES", "PT 一致")
    .replaceAll("MET UNAVAILABLE", "MET 不可用")
    .replaceAll("DBO DT", "德法結論依 DT 決定")
    .replaceAll("THIS SYSTEM IS TOO WEAK TO CLASSIFY", "此系統過弱，無法分類")
    .replaceAll("THIS WILL BE THE FINAL BULLETIN UNLESS REGENERATION OCCURS", "除非重新發展，否則這將是最後一報");
}

function translateHebertPoteatRemark(text) {
  if (!text) return "";
  return String(text)
    .replaceAll("PBO", "定位依據")
    .replaceAll("XPSD LLCC/ANMTN", "外露低層環流中心/動畫")
    .replaceAll("PRLY ORGNZD LLCC/ANMTN", "部分組織化低層環流中心/動畫")
    .replaceAll("SUBTROPICAL CYCLONE CLASSIFICATION TECHNIQUE YIELDS", "副熱帶氣旋分類技術得出")
    .replaceAll("THIS SYSTEM IS TOO WEAK TO CLASSIFY", "此系統過弱，無法分類");
}

function currentOutputText() {
  if (state.activeTab === "tac") return elements.tacOutput.innerText;
  if (state.activeTab === "recon") return elements.reconOutput.innerText;
  return elements.bufrOutput.innerText;
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
