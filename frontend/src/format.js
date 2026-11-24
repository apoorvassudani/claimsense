const inrFmt = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
const dateFmt = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" });
const timeFmt = new Intl.DateTimeFormat("en-IN", {
  day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit",
});

export const inr = (v) => (v === null || v === undefined || v === "" ? "—" : inrFmt.format(Number(v)));
export const fmtDate = (v) => (v ? dateFmt.format(new Date(v.length === 10 ? v + "T00:00:00" : v)) : "—");
export const fmtTime = (v) => (v ? timeFmt.format(new Date(v)) : "—");
export const ms = (v) => (v === null || v === undefined ? "—" : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${v} ms`);

export const CLAIM_TYPES = { MOTOR: "Motor", HEALTH: "Health", PROPERTY: "Property" };
export const DOC_TYPES = {
  CLAIM_FORM: "Claim form", INVOICE: "Invoice", POLICE_REPORT: "Police report",
  MEDICAL_BILL: "Medical bill", OTHER: "Other",
};
export const REQUIRED_DOCS = {
  MOTOR: ["CLAIM_FORM", "INVOICE", "POLICE_REPORT"],
  HEALTH: ["CLAIM_FORM", "MEDICAL_BILL"],
  PROPERTY: ["CLAIM_FORM", "INVOICE"],
};
export const STATUS = {
  SUBMITTED: "Not verified", VALIDATED: "Validated", NEEDS_REVIEW: "Needs review",
  CLEARED: "Cleared", ESCALATED: "Escalated", INFO_REQUESTED: "Info requested",
};
export const DECISIONS = {
  CLEAR: { label: "Clear the claim", help: "No fraud concerns. It can go on to normal settlement.", status: "Cleared" },
  ESCALATE: { label: "Escalate for investigation", help: "Send to the investigation team.", status: "Escalated" },
  REQUEST_INFO: { label: "Request more information", help: "Ask the claimant for missing or corrected documents.", status: "Info requested" },
};
export const RULES = {
  POLICY_PERIOD: "Outside the policy period",
  OVER_SUM_INSURED: "Above the sum insured",
  POLICY_NUMBER_MISMATCH: "Wrong policy number on a document",
  DUPLICATE_DOCUMENT: "Document file reused from another claim",
  DUPLICATE_INVOICE: "Invoice number reused from another claim",
  SHARED_VEHICLE: "Vehicle also on another person's claim",
  EARLY_CLAIM: "Claim soon after the policy started",
  AMOUNT_MISMATCH: "Claimed amount doesn't match the bills",
  NAME_MISMATCH: "Different name on a document",
  SCAN_UNCLEAR: "Scanned value may be misread (check the original)",
  DATE_MISMATCH: "Different incident date on a document",
  SHARED_PHONE: "Phone shared with another claimant",
  PROVIDER_CLUSTER: "Provider with a burst of similar claims",
  LATE_REPORTING: "Reported late",
  MISSING_DOCUMENT: "Required document missing",
};
export const FIELDS = {
  document_type: "Document type", policy_number: "Policy number", claimant_name: "Name",
  incident_date: "Incident / admission date", document_date: "Document date", amount: "Amount",
  invoice_number: "Invoice / bill number", provider_name: "Garage, hospital or contractor",
  vehicle_registration: "Vehicle", phone: "Phone",
};
export const STAGES = {
  "db.read_document": "Read document from database",
  "ai.inference": "AI model call",
  "output.validation": "Check the AI's answer",
  "db.save_extraction": "Save extracted fields",
  "graph.build": "Update fraud graph",
  "rules.evaluate": "Run fraud rules",
  "ocr.read": "Read scanned document (OCR)",
  "rag.retrieve": "Find matching policy clauses",
  "prompt.build": "Build briefing prompt from findings and clauses",
  "citation.check": "Check every cited clause was retrieved",
  "db.save_summary": "Save reviewer briefing",
  "db.save_findings": "Save findings and risk score",
};
export const EVIDENCE_LABELS = {
  incident: "Incident", start: "Policy start", end: "Policy end", days_after_start: "Days after start",
  days: "Days", claimed: "Claimed", sum_insured: "Sum insured", missing: "Missing", bill_total: "Bills total",
  document: "On the document", claim: "On the claim", other_claims: "Other claims", identifier: "Shared item",
  field: "Field",
};
export const ERRORS = {
  timeout: "The AI provider didn't answer in time",
  quota: "The AI provider's rate limit was reached",
  malformed_response: "The AI's answer wasn't usable",
  schema_validation: "The AI's answer had invalid fields",
  empty_input: "The document had no text",
  sql_error: "Database error",
  provider_error: "The AI provider returned an error",
  content_filter: "The AI provider blocked the request",
};
export const errorText = (code) => ERRORS[code] || (code ? `Error: ${code}` : "");
