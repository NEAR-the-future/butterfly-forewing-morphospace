import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";


function requiredPath(index, label) {
  const value = process.argv[index];
  if (!value) {
    throw new Error(
      `Missing ${label}. Usage: node build_ar_shape_contrast_workbook.mjs ` +
      `results.json output.xlsx [preview_dir]`,
    );
  }
  return path.resolve(value);
}


function styleHeader(range) {
  range.format = {
    fill: "#1F4E78",
    font: { bold: true, color: "#FFFFFF" },
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "outside", style: "thin", color: "#17365D" },
  };
  range.format.rowHeight = 32;
}


function styleBody(range) {
  range.format.font = { color: "#1F2937" };
  range.format.verticalAlignment = "center";
}


function addTable(sheet, address, name, style = "TableStyleMedium2") {
  const table = sheet.tables.add(address, true, name);
  table.style = style;
  table.showBandedRows = true;
  table.showFilterButton = true;
  return table;
}


function setWidths(sheet, widths) {
  for (const [address, width] of widths) {
    sheet.getRange(address).format.columnWidth = width;
  }
}


function safeNumber(value) {
  return value === null || value === undefined ? null : Number(value);
}


const inputPath = requiredPath(2, "input JSON path");
const outputPath = requiredPath(3, "output XLSX path");
const previewDir = process.argv[4] ? path.resolve(process.argv[4]) : null;
const payload = JSON.parse(await fs.readFile(inputPath, "utf8"));
const { metadata, measurements, matches, representative_pair_ids: representativeIds } = payload;

const workbook = Workbook.create();
const method = workbook.worksheets.add("Method");
const representative = workbook.worksheets.add("Representative_pairs");
const allMatches = workbook.worksheets.add("All_matches");
const arValues = workbook.worksheets.add("AR_values");

// ---------------------------------------------------------------------------
// Method and run metadata
// ---------------------------------------------------------------------------
const parameterRows = [
  ["参数或统计量", "值", "说明"],
  [
    "AR 配对阈值",
    Number(metadata.threshold_fraction),
    "两只蝴蝶的 AR 对称相对差不超过该值；本次为 5%。",
  ],
  [
    "代表图优先阈值",
    Number(metadata.priority_threshold_fraction),
    "代表图优先从更严格的 AR 差范围内挑选；不足时才扩展到 5%。",
  ],
  [
    "代表图数量",
    Number(metadata.representative_pairs),
    "每张图把 A 的翼形画成黑色，把 B 的轮廓画成红色。",
  ],
  [
    "轮廓 IoU 栅格分辨率",
    Number(metadata.mask_resolution),
    "仅用于代表配对的外形差异排序，不参与 AR 计算。",
  ],
  ["AR 公式", metadata.ar_formula, "span 归一化为 1 后，AR = 1 / 未平滑轮廓面积。"],
  [
    "AR 相对差公式",
    metadata.relative_difference_formula,
    "采用对称相对差，避免任意指定 A 或 B 作为分母。",
  ],
  [
    "轮廓 IoU 定义",
    metadata.shape_iou_definition,
    "root–tip 对齐且 span 归一化后比较；IoU 越低，轮廓差异越大。",
  ],
  [
    "外形差异公式",
    metadata.shape_difference_formula,
    "值越大表示相同 AR 下的平面外形越不同。",
  ],
  ["输入目录", metadata.input_directory, "本次分析使用的处理后翼形 PNG 目录。"],
  ["生成时间（UTC）", metadata.generated_at_utc, "ISO 8601。"],
  ["发现图像数", Number(metadata.images_found), "扫描到的 PNG 文件数。"],
  ["有效 AR 数", Number(metadata.valid_measurements), "成功提取轮廓并计算 AR 的样本数。"],
  ["失败数", Number(metadata.failed_measurements), "失败原因见 AR_values 的“备注”列。"],
  ["5% 内全部配对数", Number(metadata.matching_pairs), "详见 All_matches。"],
  ["代表配对数", Number(metadata.representative_pairs), "详见 Representative_pairs。"],
];
method.getRange(`A1:C${parameterRows.length}`).values = parameterRows;
styleHeader(method.getRange("A1:C1"));
styleBody(method.getRange(`A2:C${parameterRows.length}`));
method.getRange("B2:B3").format.numberFormat = "0.00%";
method.getRange("B4:B5").format.numberFormat = "#,##0";
method.getRange("B11").format.numberFormat = "yyyy-mm-dd hh:mm:ss";
method.getRange("B12:B16").format.numberFormat = "#,##0";
method.getRange(`B2:C${parameterRows.length}`).format.wrapText = true;
method.getRange(`A2:C${parameterRows.length}`).format.rowHeight = 42;
method.getRange(`A1:C${parameterRows.length}`).format.borders = {
  insideHorizontal: { style: "thin", color: "#D9E2F3" },
  top: { style: "thin", color: "#9FBAD0" },
  bottom: { style: "thin", color: "#9FBAD0" },
  left: { style: "thin", color: "#9FBAD0" },
  right: { style: "thin", color: "#9FBAD0" },
};
setWidths(method, [
  ["A:A", 24],
  ["B:B", 56],
  ["C:C", 64],
]);
method.freezePanes.freezeRows(1);
method.showGridLines = false;
addTable(method, `A1:C${parameterRows.length}`, "MethodTable", "TableStyleMedium2");

// ---------------------------------------------------------------------------
// One row per wing. AR is formula-driven from normalized area.
// ---------------------------------------------------------------------------
const arHeaders = [
  "样本序号",
  "蝴蝶名称",
  "类群",
  "文件名",
  "相对路径",
  "状态",
  "轮廓点数",
  "归一化翼面积",
  "AR",
  "原图 span_px",
  "tip 来源",
  "root_X_px",
  "root_Y_px",
  "tip_X_px",
  "tip_Y_px",
  "min_X_norm",
  "max_X_norm",
  "min_Y_norm",
  "max_Y_norm",
  "备注",
];
const arRows = measurements.map((row) => [
  Number(row.sample_index),
  row.name,
  row.family,
  row.file_name,
  row.relative_path,
  row.status,
  safeNumber(row.contour_points),
  safeNumber(row.normalized_area),
  null,
  safeNumber(row.span_px),
  row.tip_source,
  safeNumber(row.root_x_px),
  safeNumber(row.root_y_px),
  safeNumber(row.tip_x_px),
  safeNumber(row.tip_y_px),
  safeNumber(row.min_x_norm),
  safeNumber(row.max_x_norm),
  safeNumber(row.min_y_norm),
  safeNumber(row.max_y_norm),
  row.note,
]);
arValues.getRange("A1:T1").values = [arHeaders];
if (arRows.length > 0) {
  arValues.getRange(`A2:T${arRows.length + 1}`).values = arRows;
  arValues.getRange(`I2:I${arRows.length + 1}`).formulas = arRows.map((_, index) => [
    `=IFERROR(1/H${index + 2},"")`,
  ]);
  styleBody(arValues.getRange(`A2:T${arRows.length + 1}`));
  arValues.getRange(`A2:A${arRows.length + 1}`).format.numberFormat = "#,##0";
  arValues.getRange(`G2:G${arRows.length + 1}`).format.numberFormat = "#,##0";
  arValues.getRange(`H2:I${arRows.length + 1}`).format.numberFormat = "0.000000";
  arValues.getRange(`J2:J${arRows.length + 1}`).format.numberFormat = "#,##0.00";
  arValues.getRange(`L2:S${arRows.length + 1}`).format.numberFormat = "0.0000";
  arValues.getRange(`T2:T${arRows.length + 1}`).format.wrapText = true;
  addTable(arValues, `A1:T${arRows.length + 1}`, "ARValuesTable", "TableStyleMedium2");
}
styleHeader(arValues.getRange("A1:T1"));
setWidths(arValues, [
  ["A:A", 11],
  ["B:B", 38],
  ["C:C", 22],
  ["D:E", 38],
  ["F:F", 11],
  ["G:G", 13],
  ["H:J", 18],
  ["K:K", 23],
  ["L:S", 14],
  ["T:T", 44],
]);
arValues.freezePanes.freezeRows(1);
arValues.freezePanes.freezeColumns(3);
arValues.showGridLines = false;

// ---------------------------------------------------------------------------
// All pairs within the requested threshold.
// ---------------------------------------------------------------------------
const matchHeaders = [
  "配对ID",
  "蝴蝶A名称",
  "类群A",
  "AR_A",
  "蝴蝶B名称",
  "类群B",
  "AR_B",
  "AR绝对差",
  "AR对称相对差",
  "阈值",
  "是否在阈值内",
  "轮廓IoU",
  "外形差异_1减IoU",
  "是否跨类群",
  "代表图序号",
  "图像文件",
];
const matchRows = matches.map((row) => [
  Number(row.pair_id),
  row.wing_a,
  row.family_a,
  null,
  row.wing_b,
  row.family_b,
  null,
  null,
  null,
  null,
  null,
  Number(row.shape_iou),
  null,
  row.cross_family ? "是" : "否",
  row.representative_rank === null ? null : Number(row.representative_rank),
  row.image_file,
]);
allMatches.getRange("A1:P1").values = [matchHeaders];
if (matchRows.length > 0) {
  const lastMatchRow = matchRows.length + 1;
  allMatches.getRange(`A2:P${lastMatchRow}`).values = matchRows;
  allMatches.getRange(`D2:D${lastMatchRow}`).formulas = matches.map((row) => [
    `='AR_values'!I${Number(row.wing_a_index) + 2}`,
  ]);
  allMatches.getRange(`G2:G${lastMatchRow}`).formulas = matches.map((row) => [
    `='AR_values'!I${Number(row.wing_b_index) + 2}`,
  ]);
  allMatches.getRange(`H2:H${lastMatchRow}`).formulas = matches.map((_, index) => [
    `=ABS(D${index + 2}-G${index + 2})`,
  ]);
  allMatches.getRange(`I2:I${lastMatchRow}`).formulas = matches.map((_, index) => [
    `=IFERROR(H${index + 2}/AVERAGE(D${index + 2},G${index + 2}),"")`,
  ]);
  allMatches.getRange(`J2:J${lastMatchRow}`).formulas = matches.map(() => [
    "='Method'!$B$2",
  ]);
  allMatches.getRange(`K2:K${lastMatchRow}`).formulas = matches.map((_, index) => [
    `=IF(I${index + 2}<=J${index + 2},"是","否")`,
  ]);
  allMatches.getRange(`M2:M${lastMatchRow}`).formulas = matches.map((_, index) => [
    `=1-L${index + 2}`,
  ]);
  styleBody(allMatches.getRange(`A2:P${lastMatchRow}`));
  allMatches.getRange(`A2:A${lastMatchRow}`).format.numberFormat = "#,##0";
  allMatches.getRange(`D2:H${lastMatchRow}`).format.numberFormat = "0.000000";
  allMatches.getRange(`I2:J${lastMatchRow}`).format.numberFormat = "0.00%";
  allMatches.getRange(`L2:M${lastMatchRow}`).format.numberFormat = "0.000";
  allMatches.getRange(`O2:O${lastMatchRow}`).format.numberFormat = "#,##0";
  allMatches.getRange(`K2:K${lastMatchRow}`).conditionalFormats.add("containsText", {
    text: "是",
    format: { fill: "#E2F0D9", font: { color: "#375623" } },
  });
  allMatches.getRange(`O2:O${lastMatchRow}`).conditionalFormats.add("cellIs", {
    operator: "greaterThan",
    formula: 0,
    format: { fill: "#FCE4D6", font: { bold: true, color: "#9C0006" } },
  });
  addTable(allMatches, `A1:P${lastMatchRow}`, "AllMatchesTable", "TableStyleMedium2");
}
styleHeader(allMatches.getRange("A1:P1"));
setWidths(allMatches, [
  ["A:A", 11],
  ["B:B", 38],
  ["C:C", 22],
  ["D:D", 14],
  ["E:E", 38],
  ["F:F", 22],
  ["G:H", 14],
  ["I:J", 17],
  ["K:K", 16],
  ["L:M", 18],
  ["N:N", 15],
  ["O:O", 14],
  ["P:P", 24],
]);
allMatches.freezePanes.freezeRows(1);
allMatches.freezePanes.freezeColumns(3);
allMatches.showGridLines = false;

// ---------------------------------------------------------------------------
// Representative pairs, formula-linked to All_matches.
// ---------------------------------------------------------------------------
const idToMatch = new Map(matches.map((row) => [Number(row.pair_id), row]));
const representativeMatches = representativeIds
  .map((id) => idToMatch.get(Number(id)))
  .filter((row) => row !== undefined)
  .sort((a, b) => Number(a.representative_rank) - Number(b.representative_rank));
const representativeHeaders = [
  "代表图序号",
  "配对ID",
  "图像文件",
  "蝴蝶A名称",
  "类群A",
  "AR_A",
  "蝴蝶B名称",
  "类群B",
  "AR_B",
  "AR对称相对差",
  "轮廓IoU",
  "外形差异_1减IoU",
  "是否跨类群",
  "选择说明",
];
const representativeRows = representativeMatches.map((row) => [
  Number(row.representative_rank),
  Number(row.pair_id),
  row.image_file,
  null,
  null,
  null,
  null,
  null,
  null,
  null,
  null,
  null,
  null,
  "优先满足更严格 AR 阈值；低 IoU；样本不重复；优先跨类群。",
]);
representative.getRange("A1:N1").values = [representativeHeaders];
if (representativeRows.length > 0) {
  const lastRepresentativeRow = representativeRows.length + 1;
  representative.getRange(`A2:N${lastRepresentativeRow}`).values = representativeRows;
  representative.getRange(`D2:D${lastRepresentativeRow}`).formulas = representativeMatches.map(
    (row) => [`='All_matches'!B${Number(row.pair_id) + 1}`],
  );
  representative.getRange(`E2:E${lastRepresentativeRow}`).formulas = representativeMatches.map(
    (row) => [`='All_matches'!C${Number(row.pair_id) + 1}`],
  );
  representative.getRange(`F2:F${lastRepresentativeRow}`).formulas = representativeMatches.map(
    (row) => [`='All_matches'!D${Number(row.pair_id) + 1}`],
  );
  representative.getRange(`G2:G${lastRepresentativeRow}`).formulas = representativeMatches.map(
    (row) => [`='All_matches'!E${Number(row.pair_id) + 1}`],
  );
  representative.getRange(`H2:H${lastRepresentativeRow}`).formulas = representativeMatches.map(
    (row) => [`='All_matches'!F${Number(row.pair_id) + 1}`],
  );
  representative.getRange(`I2:I${lastRepresentativeRow}`).formulas = representativeMatches.map(
    (row) => [`='All_matches'!G${Number(row.pair_id) + 1}`],
  );
  representative.getRange(`J2:J${lastRepresentativeRow}`).formulas = representativeMatches.map(
    (row) => [`='All_matches'!I${Number(row.pair_id) + 1}`],
  );
  representative.getRange(`K2:K${lastRepresentativeRow}`).formulas = representativeMatches.map(
    (row) => [`='All_matches'!L${Number(row.pair_id) + 1}`],
  );
  representative.getRange(`L2:L${lastRepresentativeRow}`).formulas = representativeMatches.map(
    (row) => [`='All_matches'!M${Number(row.pair_id) + 1}`],
  );
  representative.getRange(`M2:M${lastRepresentativeRow}`).formulas = representativeMatches.map(
    (row) => [`='All_matches'!N${Number(row.pair_id) + 1}`],
  );
  styleBody(representative.getRange(`A2:N${lastRepresentativeRow}`));
  representative.getRange(`A2:B${lastRepresentativeRow}`).format.numberFormat = "#,##0";
  representative.getRange(`F2:F${lastRepresentativeRow}`).format.numberFormat = "0.000000";
  representative.getRange(`I2:I${lastRepresentativeRow}`).format.numberFormat = "0.000000";
  representative.getRange(`J2:J${lastRepresentativeRow}`).format.numberFormat = "0.00%";
  representative.getRange(`K2:L${lastRepresentativeRow}`).format.numberFormat = "0.000";
  representative.getRange(`N2:N${lastRepresentativeRow}`).format.wrapText = true;
  representative.getRange(`L2:L${lastRepresentativeRow}`).conditionalFormats.add("colorScale", {
    colors: ["#FFF2CC", "#F8CBAD", "#C00000"],
    thresholds: ["min", "50%", "max"],
  });
  addTable(
    representative,
    `A1:N${lastRepresentativeRow}`,
    "RepresentativePairsTable",
    "TableStyleMedium9",
  );
}
styleHeader(representative.getRange("A1:N1"));
setWidths(representative, [
  ["A:B", 13],
  ["C:C", 25],
  ["D:D", 38],
  ["E:E", 22],
  ["F:F", 14],
  ["G:G", 38],
  ["H:H", 22],
  ["I:I", 14],
  ["J:J", 18],
  ["K:L", 18],
  ["M:M", 15],
  ["N:N", 52],
]);
representative.freezePanes.freezeRows(1);
representative.freezePanes.freezeColumns(3);
representative.showGridLines = false;

// ---------------------------------------------------------------------------
// Compact verification and visual rendering of every sheet.
// ---------------------------------------------------------------------------
console.log((await workbook.inspect({
  kind: "table",
  range: `Method!A1:C${parameterRows.length}`,
  include: "values,formulas",
  tableMaxRows: 18,
  tableMaxCols: 3,
  maxChars: 6000,
})).ndjson);
console.log((await workbook.inspect({
  kind: "table",
  range: "Representative_pairs!A1:N14",
  include: "values,formulas",
  tableMaxRows: 14,
  tableMaxCols: 14,
  maxChars: 7000,
})).ndjson);
console.log((await workbook.inspect({
  kind: "table",
  range: "All_matches!A1:P8",
  include: "values,formulas",
  tableMaxRows: 8,
  tableMaxCols: 16,
  maxChars: 6000,
})).ndjson);
console.log((await workbook.inspect({
  kind: "table",
  range: "AR_values!A1:T8",
  include: "values,formulas",
  tableMaxRows: 8,
  tableMaxCols: 20,
  maxChars: 6000,
})).ndjson);
console.log((await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
  maxChars: 5000,
})).ndjson);

if (previewDir) {
  await fs.mkdir(previewDir, { recursive: true });
  const previews = [
    ["Method", `A1:C${parameterRows.length}`, "method.png"],
    ["Representative_pairs", "A1:N14", "representative_pairs.png"],
    ["All_matches", "A1:P20", "all_matches.png"],
    ["AR_values", "A1:T20", "ar_values.png"],
  ];
  for (const [sheetName, range, fileName] of previews) {
    const image = await workbook.render({
      sheetName,
      range,
      scale: 1.25,
      format: "png",
    });
    await fs.writeFile(
      path.join(previewDir, fileName),
      new Uint8Array(await image.arrayBuffer()),
    );
  }
}

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
await fs.rm(`${outputPath}.inspect.ndjson`, { force: true });
console.log(`Saved workbook: ${outputPath}`);
