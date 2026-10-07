import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";


function requireArg(index, label) {
  const value = process.argv[index];
  if (!value) {
    throw new Error(`Missing ${label}. Usage: node build_wing_ar_workbook.mjs input.json output.xlsx [preview_dir]`);
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
  range.format.rowHeight = 30;
}


function styleBody(range) {
  range.format.font = { color: "#1F2937" };
  range.format.verticalAlignment = "center";
}


function addTable(sheet, rangeAddress, name) {
  const table = sheet.tables.add(rangeAddress, true, name);
  table.style = "TableStyleMedium2";
  table.showBandedRows = true;
  table.showFilterButton = true;
  return table;
}


const inputPath = requireArg(2, "input JSON path");
const outputPath = requireArg(3, "output XLSX path");
const previewDir = process.argv[4] ? path.resolve(process.argv[4]) : null;
const payload = JSON.parse(await fs.readFile(inputPath, "utf8"));
const { metadata, measurements, matches } = payload;

const workbook = Workbook.create();
const parameters = workbook.worksheets.add("Parameters");
const values = workbook.worksheets.add("AR_values");
const pairs = workbook.worksheets.add("AR_matches");

// ---------------------------------------------------------------------------
// Parameters / method sheet
// ---------------------------------------------------------------------------
const parameterRows = [
  ["参数", "值", "说明"],
  ["AR相对差阈值", Number(metadata.threshold_fraction), "默认5%；修改后需用Python脚本重新运行，以重新筛选配对。"],
  ["AR公式", metadata.ar_formula, "AR = 展长² / 翅膀轮廓面积；像素尺度相消，结果无量纲。"],
  ["两两相对差公式", metadata.relative_difference_formula, "采用对称相对差，避免指定某一翅膀为基准。"],
  ["输入目录", metadata.input_directory, "本次批处理使用的图像目录。"],
  ["生成时间（UTC）", metadata.generated_at_utc, "ISO 8601。"],
  ["发现图像数", Number(metadata.images_found), "支持PNG/JPG/BMP/TIF。"],
  ["有效AR数", Number(metadata.valid_measurements), "成功提取轮廓并计算AR的图像数。"],
  ["失败数", Number(metadata.failed_measurements), "失败原因见AR_values工作表的备注列。"],
  ["阈值内配对数", Number(metadata.matching_pairs), "AR_matches工作表的记录数。"],
];
parameters.getRange(`A1:C${parameterRows.length}`).values = parameterRows;
styleHeader(parameters.getRange("A1:C1"));
styleBody(parameters.getRange(`A2:C${parameterRows.length}`));
parameters.getRange("B2").format.numberFormat = "0.00%";
parameters.getRange("B7:B10").format.numberFormat = "#,##0";
parameters.getRange(`A1:C${parameterRows.length}`).format.borders = {
  insideHorizontal: { style: "thin", color: "#D9E2F3" },
  outside: { style: "thin", color: "#9FBAD0" },
};
parameters.getRange(`B2:C${parameterRows.length}`).format.wrapText = true;
parameters.getRange(`A2:C${parameterRows.length}`).format.rowHeight = 42;
parameters.getRange("B6").format.numberFormat = "yyyy-mm-dd hh:mm:ss";
parameters.getRange("A:A").format.columnWidth = 22;
parameters.getRange("B:B").format.columnWidth = 50;
parameters.getRange("C:C").format.columnWidth = 58;
parameters.freezePanes.freezeRows(1);
parameters.showGridLines = false;
addTable(parameters, `A1:C${parameterRows.length}`, "ParametersTable");

// ---------------------------------------------------------------------------
// One row per image: raw measurements plus a formula-driven AR column.
// ---------------------------------------------------------------------------
const valueHeaders = [
  "样本序号",
  "文件名",
  "相对路径",
  "状态",
  "图像宽度_px",
  "图像高度_px",
  "轮廓点数",
  "轮廓面积_px2",
  "展长_px",
  "AR_展长平方除以面积",
  "翼根来源",
  "翼尖来源",
  "翼根X_px",
  "翼根Y_px",
  "翼尖X_px",
  "翼尖Y_px",
  "备注",
];
const valueRows = measurements.map((row) => [
  Number(row.sample_id),
  row.file_name,
  row.relative_path,
  row.status,
  row.image_width_px,
  row.image_height_px,
  row.contour_points,
  row.area_px2,
  row.span_px,
  null,
  row.root_source,
  row.tip_source,
  row.root_x_px,
  row.root_y_px,
  row.tip_x_px,
  row.tip_y_px,
  row.note,
]);
values.getRange("A1:Q1").values = [valueHeaders];
if (valueRows.length > 0) {
  values.getRange(`A2:Q${valueRows.length + 1}`).values = valueRows;
  values.getRange(`J2:J${valueRows.length + 1}`).formulas = valueRows.map((_, index) => [
    `=IFERROR(I${index + 2}^2/H${index + 2},"")`,
  ]);
}
styleHeader(values.getRange("A1:Q1"));
if (valueRows.length > 0) {
  styleBody(values.getRange(`A2:Q${valueRows.length + 1}`));
  values.getRange(`A2:A${valueRows.length + 1}`).format.numberFormat = "#,##0";
  values.getRange(`E2:G${valueRows.length + 1}`).format.numberFormat = "#,##0";
  values.getRange(`H2:I${valueRows.length + 1}`).format.numberFormat = "#,##0.00";
  values.getRange(`J2:J${valueRows.length + 1}`).format.numberFormat = "0.000000";
  values.getRange(`M2:P${valueRows.length + 1}`).format.numberFormat = "#,##0.00";
  values.getRange(`Q2:Q${valueRows.length + 1}`).format.wrapText = true;
  addTable(values, `A1:Q${valueRows.length + 1}`, "ARValuesTable");
}
values.getRange("A:A").format.columnWidth = 11;
values.getRange("B:C").format.columnWidth = 34;
values.getRange("D:D").format.columnWidth = 11;
values.getRange("E:G").format.columnWidth = 15;
values.getRange("H:J").format.columnWidth = 20;
values.getRange("K:L").format.columnWidth = 24;
values.getRange("M:P").format.columnWidth = 14;
values.getRange("Q:Q").format.columnWidth = 42;
values.freezePanes.freezeRows(1);
values.freezePanes.freezeColumns(2);
values.showGridLines = false;

// ---------------------------------------------------------------------------
// Only pairs retained by the requested threshold.  The AR and comparison
// columns remain formula-driven and trace directly back to AR_values.
// ---------------------------------------------------------------------------
const pairHeaders = [
  "配对序号",
  "翅膀A",
  "翅膀B",
  "AR_A",
  "AR_B",
  "AR绝对差",
  "AR对称相对差",
  "阈值",
  "是否阈值内",
];
const pairRows = matches.map((row) => [
  Number(row.pair_id),
  row.wing_a,
  row.wing_b,
  null,
  null,
  null,
  null,
  null,
  null,
]);
pairs.getRange("A1:I1").values = [pairHeaders];
if (pairRows.length > 0) {
  pairs.getRange(`A2:I${pairRows.length + 1}`).values = pairRows;
  pairs.getRange(`D2:D${pairRows.length + 1}`).formulas = matches.map((row) => [
    `='AR_values'!J${Number(row.wing_a_index) + 2}`,
  ]);
  pairs.getRange(`E2:E${pairRows.length + 1}`).formulas = matches.map((row) => [
    `='AR_values'!J${Number(row.wing_b_index) + 2}`,
  ]);
  pairs.getRange(`F2:F${pairRows.length + 1}`).formulas = matches.map((_, index) => [
    `=ABS(D${index + 2}-E${index + 2})`,
  ]);
  pairs.getRange(`G2:G${pairRows.length + 1}`).formulas = matches.map((_, index) => [
    `=IFERROR(F${index + 2}/AVERAGE(D${index + 2}:E${index + 2}),"")`,
  ]);
  pairs.getRange(`H2:H${pairRows.length + 1}`).formulas = matches.map(() => [
    "='Parameters'!$B$2",
  ]);
  pairs.getRange(`I2:I${pairRows.length + 1}`).formulas = matches.map((_, index) => [
    `=IF(G${index + 2}<=H${index + 2},"是","否")`,
  ]);
}
styleHeader(pairs.getRange("A1:I1"));
if (pairRows.length > 0) {
  styleBody(pairs.getRange(`A2:I${pairRows.length + 1}`));
  pairs.getRange(`A2:A${pairRows.length + 1}`).format.numberFormat = "#,##0";
  pairs.getRange(`D2:F${pairRows.length + 1}`).format.numberFormat = "0.000000";
  pairs.getRange(`G2:H${pairRows.length + 1}`).format.numberFormat = "0.00%";
  pairs.getRange(`I2:I${pairRows.length + 1}`).conditionalFormats.add("containsText", {
    text: "是",
    format: { fill: "#E2F0D9", font: { color: "#375623" } },
  });
  addTable(pairs, `A1:I${pairRows.length + 1}`, "ARMatchesTable");
}
pairs.getRange("A:A").format.columnWidth = 12;
pairs.getRange("B:C").format.columnWidth = 38;
pairs.getRange("D:F").format.columnWidth = 16;
pairs.getRange("G:H").format.columnWidth = 18;
pairs.getRange("I:I").format.columnWidth = 16;
pairs.freezePanes.freezeRows(1);
pairs.freezePanes.freezeColumns(3);
pairs.showGridLines = false;

// Compact verification before export.
console.log((await workbook.inspect({
  kind: "table",
  range: "Parameters!A1:C10",
  include: "values,formulas",
  tableMaxRows: 12,
  tableMaxCols: 4,
  maxChars: 5000,
})).ndjson);
console.log((await workbook.inspect({
  kind: "table",
  range: "AR_values!A1:Q6",
  include: "values,formulas",
  tableMaxRows: 6,
  tableMaxCols: 17,
  maxChars: 5000,
})).ndjson);
console.log((await workbook.inspect({
  kind: "table",
  range: "AR_matches!A1:I6",
  include: "values,formulas",
  tableMaxRows: 6,
  tableMaxCols: 9,
  maxChars: 5000,
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
    ["Parameters", "A1:C10", "parameters.png"],
    ["AR_values", "A1:Q20", "ar_values.png"],
    ["AR_matches", "A1:I20", "ar_matches.png"],
  ];
  for (const [sheetName, range, fileName] of previews) {
    const image = await workbook.render({ sheetName, range, scale: 1.5, format: "png" });
    await fs.writeFile(path.join(previewDir, fileName), new Uint8Array(await image.arrayBuffer()));
  }
}

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
console.log(`Saved workbook: ${outputPath}`);
