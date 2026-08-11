import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const projectRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const syntheticRoot = path.join(projectRoot, "data", "synthetic");
const kbRoot = path.join(projectRoot, "data", "knowledge_base");
const outputDir = path.join(projectRoot, "outputs", "synthetic_data");
const previewDir = "/private/tmp/journeyback_synthetic_workbook_previews";

const cases = (await fs.readFile(path.join(syntheticRoot, "journeyback_cases.jsonl"), "utf8"))
  .trim()
  .split("\n")
  .filter(Boolean)
  .map((line) => JSON.parse(line));
const quality = JSON.parse(await fs.readFile(path.join(syntheticRoot, "quality_report.json"), "utf8"));
const framework = JSON.parse(await fs.readFile(path.join(syntheticRoot, "evaluation_framework.json"), "utf8"));
const sources = JSON.parse(await fs.readFile(path.join(kbRoot, "normalized", "sources.json"), "utf8"));

const workbook = Workbook.create();
const overview = workbook.worksheets.add("Overview");
const casesSheet = workbook.worksheets.add("Cases");
const evaluation = workbook.worksheets.add("Evaluation");
const dictionary = workbook.worksheets.add("Data Dictionary");
const qa = workbook.worksheets.add("QA Checks");
const sourceSheet = workbook.worksheets.add("Sources");

const navy = "#0B1F3A";
const blue = "#006FCF";
const paleBlue = "#EAF3FB";
const paleGreen = "#E8F5E9";
const paleAmber = "#FFF4D6";
const paleRed = "#FDECEC";
const gray = "#5F6B7A";
const lightBorder = "#D9E2EC";

function titleBand(sheet, range, title, subtitleRange, subtitle) {
  sheet.showGridLines = false;
  sheet.getRange(range).merge();
  sheet.getRange(range).values = [[title]];
  sheet.getRange(range).format = {
    fill: navy,
    font: { bold: true, color: "#FFFFFF", size: 18 },
    verticalAlignment: "center",
  };
  sheet.getRange(range).format.rowHeight = 32;
  sheet.getRange(subtitleRange).merge();
  sheet.getRange(subtitleRange).values = [[subtitle]];
  sheet.getRange(subtitleRange).format = {
    fill: paleBlue,
    font: { color: navy, italic: true, size: 10 },
    wrapText: true,
    verticalAlignment: "center",
  };
  sheet.getRange(subtitleRange).format.rowHeight = 30;
}

function styleHeader(range) {
  range.format = {
    fill: blue,
    font: { bold: true, color: "#FFFFFF" },
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "outside", style: "thin", color: lightBorder },
  };
}

function setColumns(sheet, widths) {
  for (const [column, width] of Object.entries(widths)) {
    sheet.getRange(`${column}:${column}`).format.columnWidth = width;
  }
}

titleBand(
  overview,
  "A1:J1",
  "Journeyback Synthetic Dataset v1",
  "A2:J2",
  "600 deterministic, fully synthetic Singapore travel-disruption cases grounded in the imported public policy corpus. No real customer, booking or claim data."
);
overview.getRange("A4:B8").values = [
  ["Metric", "Value"],
  ["Synthetic cases", null],
  ["Knowledge-base sources", 14],
  ["Formal policy chunks", 22],
  ["Automated data quality score", quality.quality_score / 100],
];
overview.getRange("B5").formulas = [["=COUNTA('Cases'!$A$5:$A$604)"]];
styleHeader(overview.getRange("A4:B4"));
overview.getRange("B5:B7").format.numberFormat = "#,##0";
overview.getRange("B8").format.numberFormat = "0%";
overview.getRange("A5:B8").format.borders = { preset: "outside", style: "thin", color: lightBorder };

overview.getRange("A10:E15").values = [
  ["Scenario class", "Expected", "Actual", "Actual share", "Variance"],
  ["eligible_complete", 180, null, null, null],
  ["ineligible_rule", 150, null, null, null],
  ["insufficient_evidence", 120, null, null, null],
  ["boundary_manual_review", 90, null, null, null],
  ["unsupported_or_product_unknown", 60, null, null, null],
];
for (let row = 11; row <= 15; row += 1) {
  overview.getRange(`C${row}`).formulas = [[`=COUNTIF('Cases'!$C$5:$C$604,A${row})`]];
  overview.getRange(`D${row}`).formulas = [[`=C${row}/$B$5`]];
  overview.getRange(`E${row}`).formulas = [[`=C${row}-B${row}`]];
}
styleHeader(overview.getRange("A10:E10"));
overview.getRange("B11:C15").format.numberFormat = "#,##0";
overview.getRange("D11:D15").format.numberFormat = "0%";
overview.getRange("E11:E15").format.numberFormat = "0";
overview.getRange("A11:E15").format.borders = { preset: "outside", style: "thin", color: lightBorder };

overview.getRange("G10:J13").values = [
  ["Dataset split", "Expected", "Actual", "Share"],
  ["development", 360, null, null],
  ["validation", 120, null, null],
  ["test", 120, null, null],
];
for (let row = 11; row <= 13; row += 1) {
  overview.getRange(`I${row}`).formulas = [[`=COUNTIF('Cases'!$B$5:$B$604,G${row})`]];
  overview.getRange(`J${row}`).formulas = [[`=I${row}/$B$5`]];
}
styleHeader(overview.getRange("G10:J10"));
overview.getRange("H11:I13").format.numberFormat = "#,##0";
overview.getRange("J11:J13").format.numberFormat = "0%";
overview.getRange("G11:J13").format.borders = { preset: "outside", style: "thin", color: lightBorder };

const productRows = Object.entries(quality.product_distribution).sort((a, b) => a[0].localeCompare(b[0]));
overview.getRange("A18:D18").values = [["Product code", "Cases", "Share", "Coverage status"]];
overview.getRange(`A19:D${18 + productRows.length}`).values = productRows.map(([product, count]) => [
  product,
  count,
  count / cases.length,
  product === "UNKNOWN_PRODUCT" || product.endsWith("UNCOVERED") ? "Manual / out of scope" : "Policy-grounded",
]);
styleHeader(overview.getRange("A18:D18"));
overview.getRange(`B19:B${18 + productRows.length}`).format.numberFormat = "#,##0";
overview.getRange(`C19:C${18 + productRows.length}`).format.numberFormat = "0.0%";
overview.getRange(`A19:D${18 + productRows.length}`).format.borders = { preset: "outside", style: "thin", color: lightBorder };

overview.getRange("A28:J31").merge();
overview.getRange("A28:J31").values = [[
  "Safety boundary: every row has synthetic=true, expected_payout_sgd=null and human_review_required=true. " +
  "Potential eligibility is a benchmark label, not claim approval. Public policy versions must be confirmed before customer-facing use."
]];
overview.getRange("A28:J31").format = {
  fill: paleAmber,
  font: { bold: true, color: "#6B4F00" },
  wrapText: true,
  verticalAlignment: "center",
  borders: { preset: "outside", style: "thin", color: "#E4B849" },
};
overview.freezePanes.freezeRows(2);
setColumns(overview, { A: 36, B: 15, C: 14, D: 18, E: 12, F: 3, G: 20, H: 14, I: 14, J: 14 });

const caseColumns = [
  ["Case ID", "case_id"],
  ["Split", "split"],
  ["Scenario Class", "scenario_class"],
  ["Difficulty", "difficulty"],
  ["Language", "language"],
  ["Market", "market"],
  ["Product Code", "product_code"],
  ["Product Name", "product_name"],
  ["Product Status", "product_resolution_status"],
  ["Event Type", "event_type"],
  ["Origin", "origin_airport"],
  ["Destination", "destination_airport"],
  ["Scheduled UTC", "scheduled_departure_utc"],
  ["Duration Minutes", "incident_duration_minutes"],
  ["Duration Hours", "_formula_duration_hours"],
  ["Route Phase", "route_phase"],
  ["Final Return Leg", "is_final_return_leg"],
  ["Traveler Type", "traveler_type"],
  ["Traveler Age", "traveler_age"],
  ["Family Size", "family_size"],
  ["Trip Paid with Card", "origin_return_paid_with_card"],
  ["Expense on Card", "expense_charged_to_card"],
  ["Claim Notice Days", "claim_notice_days"],
  ["Has Ticket", "has_flight_ticket"],
  ["Carrier Confirmation", "has_carrier_confirmation"],
  ["Has PIR", "has_pir"],
  ["Has Receipts", "has_receipts"],
  ["Has Policy Certificate", "has_policy_certificate"],
  ["Expense Category", "expense_category"],
  ["Expense SGD", "expense_sgd"],
  ["Expected Eligibility", "expected_eligibility"],
  ["Expected Routing", "expected_routing"],
  ["Reference Limit SGD", "reference_limit_sgd"],
  ["Missing Documents", "expected_missing_documents"],
  ["Reason Codes", "expected_reason_codes"],
  ["Expected Actions", "expected_actions"],
  ["Source IDs", "expected_source_ids"],
  ["Chunk IDs", "expected_chunk_ids"],
  ["Human Review", "human_review_required"],
  ["User Query", "user_query"],
  ["Safety Note", "safety_note"],
  ["Content Hash", "content_hash"],
];

titleBand(
  casesSheet,
  "A1:H1",
  "Synthetic Cases",
  "A2:P2",
  "Filter by split, scenario class, product and event. Arrays are flattened with | for review; the JSONL remains the runtime source of truth."
);
casesSheet.getRange("A4:AP4").values = [caseColumns.map(([label]) => label)];
const caseValues = cases.map((row) => caseColumns.map(([, key]) => {
  if (key === "_formula_duration_hours") return null;
  const value = row[key];
  if (Array.isArray(value)) return value.join(" | ");
  return value ?? null;
}));
casesSheet.getRange(`A5:AP${4 + caseValues.length}`).values = caseValues;
casesSheet.getRange("O5").formulas = [["=N5/60"]];
casesSheet.getRange(`O5:O${4 + caseValues.length}`).fillDown();
styleHeader(casesSheet.getRange("A4:AP4"));
casesSheet.tables.add(`A4:AP${4 + caseValues.length}`, true, "SyntheticCasesTable");
casesSheet.getRange(`M5:M${4 + caseValues.length}`).format.numberFormat = "yyyy-mm-dd hh:mm";
casesSheet.getRange(`N5:O${4 + caseValues.length}`).format.numberFormat = "0.0";
casesSheet.getRange(`S5:T${4 + caseValues.length}`).format.numberFormat = "0";
casesSheet.getRange(`W5:W${4 + caseValues.length}`).format.numberFormat = "0";
casesSheet.getRange(`AD5:AG${4 + caseValues.length}`).format.numberFormat = "#,##0";
casesSheet.getRange(`AH5:AO${4 + caseValues.length}`).format.wrapText = true;
casesSheet.freezePanes.freezeRows(4);
casesSheet.freezePanes.freezeColumns(4);
setColumns(casesSheet, {
  A: 16, B: 13, C: 31, D: 11, E: 10, F: 9, G: 31, H: 32, I: 18, J: 22,
  K: 11, L: 12, M: 23, N: 13, O: 12, P: 13, Q: 14, R: 16, S: 11, T: 11,
  U: 16, V: 15, W: 14, X: 12, Y: 18, Z: 11, AA: 13, AB: 20, AC: 25, AD: 13,
  AE: 25, AF: 34, AG: 17, AH: 32, AI: 35, AJ: 55, AK: 30, AL: 45, AM: 14,
  AN: 65, AO: 65, AP: 28,
});

titleBand(
  evaluation,
  "A1:E1",
  "100-Point Evaluation Framework",
  "A2:E2",
  "Enter a 0–1 score for each component. Weighted points calculate automatically; apply the lowest relevant hard cap after scoring."
);
evaluation.getRange("A4:E10").values = [
  ["Component", "Weight", "Score (0–1)", "Weighted points", "Definition"],
  ...framework.components.map((item) => [item.component, item.weight, 0, null, item.definition]),
];
for (let row = 5; row <= 10; row += 1) {
  evaluation.getRange(`D${row}`).formulas = [[`=B${row}*C${row}`]];
}
evaluation.getRange("A12:D12").values = [["Total", null, null, null]];
evaluation.getRange("B12").formulas = [["=SUM(B5:B10)"]];
evaluation.getRange("D12").formulas = [["=SUM(D5:D10)"]];
styleHeader(evaluation.getRange("A4:E4"));
evaluation.getRange("A12:D12").format = { fill: paleBlue, font: { bold: true, color: navy } };
evaluation.getRange("B5:B12").format.numberFormat = "0";
evaluation.getRange("C5:C10").format.numberFormat = "0.0";
evaluation.getRange("D5:D12").format.numberFormat = "0.0";
evaluation.getRange("C5:C10").format.fill = paleAmber;
evaluation.getRange("A15:C15").values = [["Hard-cap condition", "Maximum total", "Purpose"]];
evaluation.getRange("A16:C18").values = framework.hard_caps.map((item) => [
  item.condition,
  item.maximum_total_score,
  "Safety override",
]);
styleHeader(evaluation.getRange("A15:C15"));
evaluation.getRange("B16:B18").format.numberFormat = "0";
evaluation.getRange("A16:C18").format = {
  fill: paleRed,
  wrapText: true,
  borders: { preset: "outside", style: "thin", color: "#E6A7A7" },
};
evaluation.getRange("16:18").format.rowHeight = 36;
evaluation.freezePanes.freezeRows(4);
setColumns(evaluation, { A: 34, B: 13, C: 14, D: 18, E: 90 });

const dictionaryRows = [
  ["Identity", "case_id", "string", "Stable synthetic case identifier", "JB-SYN-0001"],
  ["Partition", "split", "enum", "Development, validation or held-out test partition", "test"],
  ["Partition", "scenario_class", "enum", "Strictly allocated case archetype", "insufficient_evidence"],
  ["Product", "product_code", "string", "Resolved policy product or explicit uncovered/unknown marker", "SG_PLATINUM_CHARGE"],
  ["Product", "product_resolution_status", "enum", "resolved, uncovered_product or unknown", "resolved"],
  ["Incident", "event_type", "enum", "Flight, connection, baggage or support event", "baggage_delay"],
  ["Incident", "incident_duration_minutes", "integer", "Observed duration used against the product-specific threshold", "420"],
  ["Incident", "is_final_return_leg", "boolean", "Whether baggage trouble occurred on the final return segment", "false"],
  ["Eligibility", "origin_return_paid_with_card", "boolean", "Whether originating and return travel cost met the Card payment condition", "true"],
  ["Eligibility", "expense_charged_to_card", "boolean", "Whether claimed expense was charged to the Card when required", "true"],
  ["Evidence", "has_carrier_confirmation", "boolean", "Written disruption confirmation available", "false"],
  ["Evidence", "has_pir", "boolean", "Property Irregularity Report available", "true"],
  ["Evidence", "has_receipts", "boolean", "Itemised expense receipts available", "true"],
  ["Evidence", "has_policy_certificate", "boolean", "Purchased-policy certificate available", "true"],
  ["Label", "expected_eligibility", "enum", "Gold benchmark output; never a claim decision", "potentially_eligible"],
  ["Label", "reference_limit_sgd", "integer/null", "Policy limit context, not expected payout", "400"],
  ["Label", "expected_payout_sgd", "null", "Always null by design", "null"],
  ["Label", "expected_missing_documents", "array", "Evidence the assistant should request", "pir | receipts"],
  ["Grounding", "expected_source_ids", "array", "Official source identifiers expected for retrieval", "POL-SG-PLATINUM-2021-06"],
  ["Grounding", "expected_chunk_ids", "array", "Policy chunks expected for retrieval", "POL-SG-PLATINUM-BAGGAGE"],
  ["Safety", "human_review_required", "boolean", "Always true for customer-facing policy conclusions", "true"],
  ["Safety", "safety_note", "string", "Required non-approval and version caveat", "Never promise coverage"],
  ["Audit", "content_hash", "sha256", "Detects accidental row mutation", "64 hexadecimal characters"],
];
titleBand(
  dictionary,
  "A1:E1",
  "Data Dictionary",
  "A2:E2",
  "The JSONL contains additional contextual fields; these are the fields most important to system behaviour, evaluation and audit."
);
dictionary.getRange(`A4:E${4 + dictionaryRows.length}`).values = [
  ["Category", "Field", "Type", "Definition", "Example"],
  ...dictionaryRows,
];
styleHeader(dictionary.getRange("A4:E4"));
dictionary.getRange(`A5:E${4 + dictionaryRows.length}`).format.wrapText = true;
dictionary.getRange(`A4:E${4 + dictionaryRows.length}`).format.borders = { preset: "outside", style: "thin", color: lightBorder };
dictionary.freezePanes.freezeRows(4);
setColumns(dictionary, { A: 15, B: 34, C: 16, D: 75, E: 38 });

const checkRows = Object.entries(quality.checks);
titleBand(
  qa,
  "A1:D1",
  "Automated Quality Checks",
  "A2:D2",
  "All checks must pass before the dataset is accepted for development, evaluation or demonstration."
);
qa.getRange("A4:C4").values = [["Check", "Passed", "Interpretation"]];
qa.getRange(`A5:C${4 + checkRows.length}`).values = checkRows.map(([name, passed]) => [
  name,
  passed,
  passed ? "Requirement satisfied" : "Dataset must not be used",
]);
qa.getRange("E4:F8").values = [
  ["Quality summary", "Value"],
  ["Pass rate", null],
  ["Quality score", quality.quality_score / 100],
  ["Seed", quality.seed],
  ["Cases", quality.case_count],
];
qa.getRange("F5").formulas = [[`=COUNTIF(C5:C${4 + checkRows.length},"Requirement satisfied")/COUNTA(C5:C${4 + checkRows.length})`]];
styleHeader(qa.getRange("A4:C4"));
styleHeader(qa.getRange("E4:F4"));
qa.getRange(`B5:B${4 + checkRows.length}`).format.fill = paleGreen;
qa.getRange("F5:F6").format.numberFormat = "0%";
qa.getRange("F7:F8").format.numberFormat = "0";
qa.getRange(`A5:C${4 + checkRows.length}`).format.borders = { preset: "outside", style: "thin", color: lightBorder };
qa.freezePanes.freezeRows(4);
setColumns(qa, { A: 42, B: 12, C: 32, D: 3, E: 22, F: 14 });

titleBand(
  sourceSheet,
  "A1:G1",
  "Knowledge-Base Sources",
  "A2:G2",
  "Official public sources used to ground the benchmark labels. Formal policy wording outranks summaries and FAQs after product and version confirmation."
);
sourceSheet.getRange(`A4:G${4 + sources.length}`).values = [
  ["Source ID", "Product", "Document Type", "Published", "Version Status", "Authority Rank", "Official URL"],
  ...sources.map((source) => [
    source.source_id,
    source.product,
    source.document_type,
    source.published_date ?? "Not stated",
    source.version_status,
    source.authority_rank,
    source.url,
  ]),
];
styleHeader(sourceSheet.getRange("A4:G4"));
sourceSheet.getRange(`A5:G${4 + sources.length}`).format.wrapText = true;
sourceSheet.getRange(`F5:F${4 + sources.length}`).format.numberFormat = "0";
sourceSheet.getRange(`A4:G${4 + sources.length}`).format.borders = { preset: "outside", style: "thin", color: lightBorder };
sourceSheet.freezePanes.freezeRows(4);
setColumns(sourceSheet, { A: 32, B: 36, C: 28, D: 14, E: 52, F: 14, G: 90 });

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const previewRanges = {
  Overview: "A1:J31",
  Cases: "A1:P18",
  Evaluation: "A1:E18",
  "Data Dictionary": "A1:E27",
  "QA Checks": `A1:F${Math.min(22, 4 + checkRows.length)}`,
  Sources: `A1:G${Math.min(18, 3 + sources.length)}`,
};
for (const [sheetName, range] of Object.entries(previewRanges)) {
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(
    path.join(previewDir, `${sheetName.replaceAll(" ", "_")}.png`),
    new Uint8Array(await preview.arrayBuffer())
  );
}

const output = await SpreadsheetFile.exportXlsx(workbook);
const outputPath = path.join(outputDir, "Journeyback_Synthetic_Data_v1.xlsx");
await output.save(outputPath);

const errorInspect = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
await fs.rm(`${outputPath}.inspect.ndjson`, { force: true });

console.log(JSON.stringify({
  outputPath,
  sheets: ["Overview", "Cases", "Evaluation", "Data Dictionary", "QA Checks", "Sources"],
  cases: cases.length,
  formulaErrorScan: errorInspect.ndjson,
  previewDir,
}, null, 2));
