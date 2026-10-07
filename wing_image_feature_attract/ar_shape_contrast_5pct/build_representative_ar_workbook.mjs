import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";


function requiredPath(index, label) {
  const value = process.argv[index];
  if (!value) {
    throw new Error(
      `Missing ${label}. Usage: node build_representative_ar_workbook.mjs ` +
      `data.json output.xlsx preview_dir`,
    );
  }
  return path.resolve(value);
}


const inputPath = requiredPath(2, "input JSON");
const outputPath = requiredPath(3, "output workbook");
const previewDir = requiredPath(4, "preview directory");
const payload = JSON.parse(await fs.readFile(inputPath, "utf8"));

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("Normalized_AR");
sheet.showGridLines = false;

const headers = [
  "图像文件",
  "面板",
  "蝴蝶名称",
  "归一化翼面积",
  "AR",
];
const rows = payload.rows.map((row) => [
  row.figure,
  row.panel,
  row.name,
  Number(row.normalized_area),
  null,
]);

sheet.getRange("A1:E1").values = [headers];
sheet.getRange("A1:E1").format = {
  fill: "#1F4E78",
  font: {
    bold: true,
    color: "#FFFFFF",
    name: "Times New Roman",
    size: 12,
  },
  verticalAlignment: "center",
  horizontalAlignment: "center",
  wrapText: true,
  borders: { preset: "outside", style: "thin", color: "#17365D" },
};
sheet.getRange("A1:E1").format.rowHeight = 30;

if (rows.length > 0) {
  const lastRow = rows.length + 1;
  sheet.getRange(`A2:E${lastRow}`).values = rows;
  sheet.getRange(`E2:E${lastRow}`).formulas = rows.map((_, index) => [
    `=IFERROR(1/D${index + 2},"")`,
  ]);
  sheet.getRange(`A2:E${lastRow}`).format = {
    font: {
      color: "#1F2937",
      name: "Times New Roman",
      size: 11,
    },
    verticalAlignment: "center",
  };
  sheet.getRange(`B2:B${lastRow}`).format.horizontalAlignment = "center";
  sheet.getRange(`D2:E${lastRow}`).format.numberFormat = "0.000000";
  const table = sheet.tables.add(`A1:E${lastRow}`, true, "NormalizedARTable");
  table.style = "TableStyleMedium2";
  table.showBandedRows = true;
  table.showFilterButton = true;
}

sheet.getRange("A:A").format.columnWidth = 20;
sheet.getRange("B:B").format.columnWidth = 10;
sheet.getRange("C:C").format.columnWidth = 42;
sheet.getRange("D:E").format.columnWidth = 20;
sheet.freezePanes.freezeRows(1);
sheet.freezePanes.freezeColumns(3);

console.log((await workbook.inspect({
  kind: "table",
  range: "Normalized_AR!A1:E25",
  include: "values,formulas",
  tableMaxRows: 25,
  tableMaxCols: 5,
  maxChars: 8000,
})).ndjson);
console.log((await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "formula error scan",
  maxChars: 3000,
})).ndjson);

await fs.mkdir(previewDir, { recursive: true });
const preview = await workbook.render({
  sheetName: "Normalized_AR",
  range: "A1:E25",
  scale: 1.5,
  format: "png",
});
await fs.writeFile(
  path.join(previewDir, "representative_normalized_ar.png"),
  new Uint8Array(await preview.arrayBuffer()),
);

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
await fs.rm(`${outputPath}.inspect.ndjson`, { force: true });
console.log(`Saved workbook: ${outputPath}`);
