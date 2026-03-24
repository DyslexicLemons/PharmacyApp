/**
 * Client-side SIG code translation.
 *
 * Mirrors the logic in backend/app/sig_codes.py.
 * Converts a space-separated SIG code string into a human-readable
 * prescription instruction, using the drug's physical form to supply
 * sensible defaults when unit / route are omitted.
 *
 * Examples:
 *   translateSig("1 TAB PO QD CF", "Tablet")  → "Take 1 tablet by mouth once daily with food"
 *   translateSig("QD", "Liquid")               → "Take ___ mL by mouth once daily"
 *   translateSig("2 GTT OD QID PRN PA", "Drops") → "Instil 2 drops in the right eye four times daily for pain"
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type SigCategory = "verb" | "route" | "location" | "unit" | "freq" | "mod" | "cond";

interface SigEntry {
  cat: SigCategory;
  expansion: string | [string, string | null];
}

// ---------------------------------------------------------------------------
// SIG code dictionary
// ---------------------------------------------------------------------------

const SIG_CODES: Record<string, SigEntry> = {
  // ── Explicit verbs ───────────────────────────────────────────────────────
  T:      { cat: "verb",     expansion: "Take" },
  G:      { cat: "verb",     expansion: "Give" },
  DR:     { cat: "verb",     expansion: "Drink" },
  I:      { cat: "verb",     expansion: "Inhale" },
  INJ:    { cat: "verb",     expansion: "Inject" },
  APP:    { cat: "verb",     expansion: "Apply" },
  INS:    { cat: "verb",     expansion: "Instil" },
  IR:     { cat: "verb",     expansion: "Insert" },
  PL:     { cat: "verb",     expansion: "Place" },

  // ── Routes (implied verb + route text) ──────────────────────────────────
  PO:     { cat: "route",    expansion: ["Take",   "by mouth"] },
  SL:     { cat: "route",    expansion: ["Place",  "under the tongue"] },
  R:      { cat: "route",    expansion: ["Insert", "into the rectum"] },
  V:      { cat: "route",    expansion: ["Insert", "into the vagina"] },

  // ── Locations (implied verb + anatomical site) ───────────────────────────
  AU:     { cat: "location", expansion: ["Instil", "in each ear"] },
  OU:     { cat: "location", expansion: ["Instil", "in each eye"] },
  IEN:    { cat: "location", expansion: ["Instil", "in each nostril"] },
  AL:     { cat: "location", expansion: ["Instil", "in the left ear"] },
  AD:     { cat: "location", expansion: ["Instil", "in the right ear"] },
  OS:     { cat: "location", expansion: ["Instil", "in the left eye"] },
  OD:     { cat: "location", expansion: ["Instil", "in the right eye"] },
  AA:     { cat: "location", expansion: ["Apply",  "to the affected area"] },

  // ── Units (singular) ─────────────────────────────────────────────────────
  TAB:    { cat: "unit",     expansion: "tablet" },
  TABS:   { cat: "unit",     expansion: "tablet" },
  CAP:    { cat: "unit",     expansion: "capsule" },
  CAPS:   { cat: "unit",     expansion: "capsule" },
  GTT:    { cat: "unit",     expansion: "drop" },
  GTTS:   { cat: "unit",     expansion: "drop" },
  PF:     { cat: "unit",     expansion: "puff" },
  SUPP:   { cat: "unit",     expansion: "suppository" },
  TSP:    { cat: "unit",     expansion: "teaspoon" },
  TSPS:   { cat: "unit",     expansion: "teaspoon" },
  TBL:    { cat: "unit",     expansion: "tablespoon" },
  TBLS:   { cat: "unit",     expansion: "tablespoon" },
  APL:    { cat: "unit",     expansion: "applicatorful" },
  SS:     { cat: "unit",     expansion: "one-half" }, // treated as a quantity string

  // ── Frequency ────────────────────────────────────────────────────────────
  QD:     { cat: "freq",     expansion: "once daily" },
  DY:     { cat: "freq",     expansion: "daily" },
  BID:    { cat: "freq",     expansion: "twice daily" },
  TID:    { cat: "freq",     expansion: "three times daily" },
  QID:    { cat: "freq",     expansion: "four times daily" },
  QBID:   { cat: "freq",     expansion: "one to two times daily" },
  BTID:   { cat: "freq",     expansion: "two to three times daily" },
  TQID:   { cat: "freq",     expansion: "three to four times daily" },
  HS:     { cat: "freq",     expansion: "at bedtime" },
  QAM:    { cat: "freq",     expansion: "every morning" },
  QPM:    { cat: "freq",     expansion: "every evening" },
  N:      { cat: "freq",     expansion: "at night" },
  Q1H:    { cat: "freq",     expansion: "every hour" },
  Q2H:    { cat: "freq",     expansion: "every 2 hours" },
  Q3H:    { cat: "freq",     expansion: "every 3 hours" },
  Q4H:    { cat: "freq",     expansion: "every 4 hours" },
  Q6H:    { cat: "freq",     expansion: "every 6 hours" },
  Q8H:    { cat: "freq",     expansion: "every 8 hours" },
  Q12H:   { cat: "freq",     expansion: "every 12 hours" },
  Q2D:    { cat: "freq",     expansion: "every other day" },
  "Q2-3H":{ cat: "freq",     expansion: "every 2 to 3 hours" },
  "Q2-4H":{ cat: "freq",     expansion: "every 2 to 4 hours" },
  "Q4-6H":{ cat: "freq",     expansion: "every 4 to 6 hours" },
  STAT:   { cat: "freq",     expansion: "immediately" },
  PRN:    { cat: "freq",     expansion: "as needed" },
  PRNF:   { cat: "freq",     expansion: "as needed for" },

  // ── Modifiers ────────────────────────────────────────────────────────────
  CC:     { cat: "mod",      expansion: "with meals" },
  CF:     { cat: "mod",      expansion: "with food" },
  PC:     { cat: "mod",      expansion: "after meals" },
  AC:     { cat: "mod",      expansion: "before meals" },
  CR:     { cat: "mod",      expansion: "crushed" },
  SW:     { cat: "mod",      expansion: "shake well" },
  UF:     { cat: "mod",      expansion: "until finished" },
  SP:     { cat: "mod",      expansion: "sparingly" },
  C:      { cat: "mod",      expansion: "with" },
  S:      { cat: "mod",      expansion: "without" },
  AQ:     { cat: "mod",      expansion: "with water" },
  JU:     { cat: "mod",      expansion: "with juice" },
  FL:     { cat: "mod",      expansion: "with fluids" },
  UD:     { cat: "mod",      expansion: "as directed" },

  // ── Conditions (PRN reasons) ─────────────────────────────────────────────
  PA:     { cat: "cond",     expansion: "for pain" },
  SB:     { cat: "cond",     expansion: "for shortness of breath" },
  FE:     { cat: "cond",     expansion: "for fever" },
  DI:     { cat: "cond",     expansion: "for diarrhea" },
  CON:    { cat: "cond",     expansion: "for constipation" },
  INF:    { cat: "cond",     expansion: "for inflammation" },
  BP:     { cat: "cond",     expansion: "for blood pressure" },
  HD:     { cat: "cond",     expansion: "for headache" },
  CI:     { cat: "cond",     expansion: "for circulation" },
  RA:     { cat: "cond",     expansion: "for rash" },
  AR:     { cat: "cond",     expansion: "for arthritis" },
};

// ---------------------------------------------------------------------------
// Pluralisation
// ---------------------------------------------------------------------------

const PLURALS: Record<string, string> = {
  tablet:        "tablets",
  capsule:       "capsules",
  drop:          "drops",
  puff:          "puffs",
  suppository:   "suppositories",
  teaspoon:      "teaspoons",
  tablespoon:    "tablespoons",
  applicatorful: "applicatorfuls",
  patch:         "patches",
  film:          "films",
};

// ---------------------------------------------------------------------------
// Drug-form defaults  [verb, routeText | null, unit | null, defaultQty]
// defaultQty is a number (solid forms) or "___" (variable liquid/injection)
// or null when quantity makes no sense (e.g. topical)
// ---------------------------------------------------------------------------

type FormDefaults = [string, string | null, string | null, number | string | null];

const FORM_DEFAULTS: Record<string, FormDefaults> = {
  Tablet:      ["Take",    "by mouth",             "tablet",       1],
  Capsule:     ["Take",    "by mouth",             "capsule",      1],
  Liquid:      ["Take",    "by mouth",             "mL",           "___"],
  Injection:   ["Inject",  "subcutaneously",       "mL",           "___"],
  Patch:       ["Apply",   "to skin",              "patch",        1],
  Film:        ["Place",   "under the tongue",     "film",         1],
  Topical:     ["Apply",   "to the affected area", null,           null],
  Inhaler:     ["Inhale",  null,                   "puff",         "___"],
  Drops:       ["Instil",  "as directed",          "drop",         2],
  Suppository: ["Insert",  "rectally",             "suppository",  1],
  Powder:      ["Take",    "by mouth",             "dose",         "___"],
  Unknown:     ["Take",    "as directed",          "dose",         null],
};

const DEFAULT_FALLBACK: FormDefaults = ["Take", "as directed", "dose", null];

function getFormDefaults(drugForm: string | null | undefined): FormDefaults {
  if (!drugForm) return DEFAULT_FALLBACK;
  return FORM_DEFAULTS[drugForm] ?? DEFAULT_FALLBACK;
}

// ---------------------------------------------------------------------------
// Main translation function
// ---------------------------------------------------------------------------

export function translateSig(codeStr: string, drugForm?: string | null): string {
  if (!codeStr || !codeStr.trim()) return "";

  const tokens = codeStr.trim().toUpperCase().split(/\s+/);

  let qty: number | string | null = null;
  let unit: string | null = null;
  let verb: string | null = null;
  let routeText: string | null = null;
  let freq: string | null = null;
  const modifiers: string[] = [];
  const conditions: string[] = [];

  for (const token of tokens) {
    // Numeric quantity?
    const num = Number(token);
    if (!isNaN(num) && token !== "") {
      qty = Number.isInteger(num) ? num : num;
      continue;
    }

    const entry = SIG_CODES[token];
    if (!entry) continue;

    const { cat, expansion } = entry;

    if (cat === "verb") {
      if (verb === null) verb = expansion as string;
    } else if (cat === "route") {
      const [impliedVerb, rt] = expansion as [string, string];
      if (verb === null) verb = impliedVerb;
      routeText = rt;
    } else if (cat === "location") {
      const [impliedVerb, loc] = expansion as [string, string];
      if (verb === null) verb = impliedVerb;
      routeText = loc;
    } else if (cat === "unit") {
      if (expansion === "one-half") {
        qty = "one-half";
      } else {
        unit = expansion as string;
      }
    } else if (cat === "freq") {
      freq = expansion as string;
    } else if (cat === "mod") {
      modifiers.push(expansion as string);
    } else if (cat === "cond") {
      conditions.push(expansion as string);
    }
  }

  // Fill gaps from drug-form defaults
  const [fVerb, fRoute, fUnit, fQty] = getFormDefaults(drugForm);
  if (verb === null) verb = fVerb;
  if (routeText === null) routeText = fRoute;
  if (unit === null) unit = fUnit;
  if (qty === null) qty = fQty;

  // Pluralise unit when quantity is a whole number > 1
  if (unit && typeof qty === "number" && qty !== 1) {
    unit = PLURALS[unit] ?? unit;
  }

  // Assemble
  const parts: string[] = [];
  if (verb) parts.push(verb);
  if (qty !== null) parts.push(String(qty));
  if (unit) parts.push(unit);
  if (routeText) parts.push(routeText);
  if (freq) parts.push(freq);
  for (const m of modifiers) parts.push(m);
  for (const c of conditions) parts.push(c);

  if (parts.length === 0) return codeStr;

  const result = parts.join(" ");
  return result.charAt(0).toUpperCase() + result.slice(1);
}

// ---------------------------------------------------------------------------
// Helper: check whether a string looks like it contains SIG codes
// (used to decide whether to show the SIG preview panel)
// ---------------------------------------------------------------------------

export function looksLikeSigCode(input: string): boolean {
  if (!input || !input.trim()) return false;
  const tokens = input.trim().toUpperCase().split(/\s+/);
  const known = tokens.filter(t => SIG_CODES[t] !== undefined || /^\d+(\.\d+)?$/.test(t));
  // Show preview if at least half the tokens are recognised SIG codes or numbers
  return known.length >= 1 && known.length / tokens.length >= 0.4;
}

// ---------------------------------------------------------------------------
// Export the full code list so the UI can render a reference panel
// ---------------------------------------------------------------------------

export interface SigCodeInfo {
  code: string;
  category: string;
  description: string;
}

export const ALL_SIG_CODES: SigCodeInfo[] = Object.entries(SIG_CODES).map(([code, entry]) => {
  const desc = Array.isArray(entry.expansion)
    ? (entry.expansion[1] ?? entry.expansion[0])
    : entry.expansion;
  return { code, category: entry.cat, description: desc as string };
});
