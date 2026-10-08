import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const here = path.dirname(fileURLToPath(import.meta.url));
const outputDir = path.resolve(here, "../../outputs/wps-meeting-mock-v1");
const workbook = Workbook.create();
const sheet = workbook.worksheets.add("实验记录");
sheet.showGridLines = false;

// Invented measurements. The workbook is an editable WPS-compatible input,
// not a real experiment or a Motif skill.
sheet.getRange("A1:G7").values = [
  ["run_id", "variant", "seed", "test_cases", "correct", "duration_s", "source_run"],
  ["base_s1", "baseline", 1, 100, 70, 111.2, "synthetic://base/s1"],
  ["base_s2", "baseline", 2, 100, 71, 108.9, "synthetic://base/s2"],
  ["base_s3", "baseline", 3, 100, 72, 113.4, "synthetic://base/s3"],
  ["cand_s1", "candidate", 1, 100, 78, 104.5, "synthetic://candidate/s1"],
  ["cand_s2", "candidate", 2, 100, 79, 103.8, "synthetic://candidate/s2"],
  ["cand_s3", "candidate", 3, 100, 80, 102.7, "synthetic://candidate/s3"],
];
sheet.getRange("A1:G7").format.font = { name: "Arial", size: 10, color: "#1F2937" };
sheet.getRange("A1:G1").format = {
  fill: "#17324D",
  font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
  rowHeight: 25,
  verticalAlignment: "center",
  horizontalAlignment: "center",
};
sheet.getRange("A2:G7").format.rowHeight = 22;
sheet.getRange("A:A").format.columnWidth = 17;
sheet.getRange("B:B").format.columnWidth = 17;
sheet.getRange("C:E").format.columnWidth = 14;
sheet.getRange("F:F").format.columnWidth = 17;
sheet.getRange("G:G").format.columnWidth = 32;
sheet.getRange("C2:E7").setNumberFormat("0");
sheet.getRange("F2:F7").setNumberFormat("0.0");
sheet.freezePanes.freezeRows(1);

workbook.recalculate();
const check = await workbook.inspect({
  kind: "table", range: "实验记录!A1:G7", include: "values,formulas",
  tableMaxRows: 8, tableMaxCols: 7, maxChars: 5000,
});
console.log(check.ndjson);
const errors = await workbook.inspect({
  kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 20 }, maxChars: 1200,
});
console.log(errors.ndjson);
await fs.mkdir(outputDir, { recursive: true });
const preview = await workbook.render({ sheetName: "实验记录", range: "A1:G7", scale: 2, format: "png" });
await fs.writeFile(path.join(outputDir, "experiment_log_preview.png"), new Uint8Array(await preview.arrayBuffer()));
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(path.join(outputDir, "experiment_log.xlsx"));
