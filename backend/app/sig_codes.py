"""SIG code translation: converts pharmacy shorthand into human-readable instructions.

SIG codes are standard pharmacy abbreviations (e.g. QD, BID, TAB, PO) used to write
prescription directions compactly.  This module parses a space-separated SIG code
string and assembles a grammatically correct English instruction, using the drug's
physical form to supply sensible defaults when unit/route are omitted.

Example:
    >>> translate_sig("1 TAB PO QD CF", "Tablet")
    'Take 1 tablet by mouth once daily with food'

    >>> translate_sig("QD", "Liquid")
    'Take ___ mL by mouth once daily'

    >>> translate_sig("2 GTT OD QID PRN PA", "Drops")
    'Instil 2 drops in the right eye four times daily as needed for pain'
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# SIG code dictionary
# Each entry: code → (category, expansion)
#
# Categories:
#   "verb"      – explicit action verb (overrides route-implied verb)
#   "route"     – route of administration; expansion = (implied_verb, route_text)
#   "location"  – anatomical target; expansion = (implied_verb, location_text)
#   "unit"      – dosage unit (singular form)
#   "freq"      – frequency / timing
#   "mod"       – administration modifier (with food, crushed, etc.)
#   "cond"      – clinical condition (for pain, for fever, etc.)
# ---------------------------------------------------------------------------

SIG_CODES: dict[str, tuple[str, object]] = {
    # ── Explicit verbs ──────────────────────────────────────────────────────
    "T":      ("verb",     "Take"),
    "G":      ("verb",     "Give"),
    "DR":     ("verb",     "Drink"),
    "I":      ("verb",     "Inhale"),
    "INJ":    ("verb",     "Inject"),
    "APP":    ("verb",     "Apply"),
    "INS":    ("verb",     "Instil"),
    "IR":     ("verb",     "Insert"),
    "PL":     ("verb",     "Place"),

    # ── Routes (carry implied verb + route text) ─────────────────────────────
    "PO":     ("route",    ("Take",   "by mouth")),
    "SL":     ("route",    ("Place",  "under the tongue")),
    "R":      ("route",    ("Insert", "into the rectum")),
    "V":      ("route",    ("Insert", "into the vagina")),

    # ── Locations (imply both verb and where) ────────────────────────────────
    "AU":     ("location", ("Instil", "in each ear")),
    "OU":     ("location", ("Instil", "in each eye")),
    "IEN":    ("location", ("Instil", "in each nostril")),
    "AL":     ("location", ("Instil", "in the left ear")),
    "AD":     ("location", ("Instil", "in the right ear")),
    "OS":     ("location", ("Instil", "in the left eye")),
    "OD":     ("location", ("Instil", "in the right eye")),
    "AA":     ("location", ("Apply",  "to the affected area")),

    # ── Dosage units (singular) ──────────────────────────────────────────────
    "TAB":    ("unit",     "tablet"),
    "TABS":   ("unit",     "tablet"),   # plural input → still store singular, pluralize at render
    "CAP":    ("unit",     "capsule"),
    "CAPS":   ("unit",     "capsule"),
    "GTT":    ("unit",     "drop"),
    "GTTS":   ("unit",     "drop"),
    "PF":     ("unit",     "puff"),
    "SUPP":   ("unit",     "suppository"),
    "TSP":    ("unit",     "teaspoon"),
    "TSPS":   ("unit",     "teaspoon"),
    "TBL":    ("unit",     "tablespoon"),
    "TBLS":   ("unit",     "tablespoon"),
    "APL":    ("unit",     "applicatorful"),
    "SS":     ("unit",     "one-half"),   # SS = ½; treated as quantity string

    # ── Frequency / timing ───────────────────────────────────────────────────
    "QD":     ("freq",     "once daily"),
    "DY":     ("freq",     "daily"),
    "BID":    ("freq",     "twice daily"),
    "TID":    ("freq",     "three times daily"),
    "QID":    ("freq",     "four times daily"),
    "QBID":   ("freq",     "one to two times daily"),
    "BTID":   ("freq",     "two to three times daily"),
    "TQID":   ("freq",     "three to four times daily"),
    "HS":     ("freq",     "at bedtime"),
    "QAM":    ("freq",     "every morning"),
    "QPM":    ("freq",     "every evening"),
    "N":      ("freq",     "at night"),
    "Q1H":    ("freq",     "every hour"),
    "Q2H":    ("freq",     "every 2 hours"),
    "Q3H":    ("freq",     "every 3 hours"),
    "Q4H":    ("freq",     "every 4 hours"),
    "Q6H":    ("freq",     "every 6 hours"),
    "Q8H":    ("freq",     "every 8 hours"),
    "Q12H":   ("freq",     "every 12 hours"),
    "Q2D":    ("freq",     "every other day"),
    "Q2-3H":  ("freq",     "every 2 to 3 hours"),
    "Q2-4H":  ("freq",     "every 2 to 4 hours"),
    "Q4-6H":  ("freq",     "every 4 to 6 hours"),
    "STAT":   ("freq",     "immediately"),
    "PRN":    ("freq",     "as needed"),
    "PRNF":   ("freq",     "as needed for"),

    # ── Modifiers ────────────────────────────────────────────────────────────
    "CC":     ("mod",      "with meals"),
    "CF":     ("mod",      "with food"),
    "PC":     ("mod",      "after meals"),
    "AC":     ("mod",      "before meals"),
    "CR":     ("mod",      "crushed"),
    "SW":     ("mod",      "shake well"),
    "UF":     ("mod",      "until finished"),
    "SP":     ("mod",      "sparingly"),
    "C":      ("mod",      "with"),
    "S":      ("mod",      "without"),
    "AQ":     ("mod",      "with water"),
    "JU":     ("mod",      "with juice"),
    "FL":     ("mod",      "with fluids"),
    "UD":     ("mod",      "as directed"),

    # ── Conditions (PRN reasons) ─────────────────────────────────────────────
    "PA":     ("cond",     "for pain"),
    "SB":     ("cond",     "for shortness of breath"),
    "FE":     ("cond",     "for fever"),
    "DI":     ("cond",     "for diarrhea"),
    "CON":    ("cond",     "for constipation"),
    "INF":    ("cond",     "for inflammation"),
    "BP":     ("cond",     "for blood pressure"),
    "HD":     ("cond",     "for headache"),
    "CI":     ("cond",     "for circulation"),
    "RA":     ("cond",     "for rash"),
    "AR":     ("cond",     "for arthritis"),
}

# ---------------------------------------------------------------------------
# Pluralisation map (singular → plural) for known unit words
# ---------------------------------------------------------------------------
_PLURALS: dict[str, str] = {
    "tablet":        "tablets",
    "capsule":       "capsules",
    "drop":          "drops",
    "puff":          "puffs",
    "suppository":   "suppositories",
    "teaspoon":      "teaspoons",
    "tablespoon":    "tablespoons",
    "applicatorful": "applicatorfuls",
    "patch":         "patches",
    "film":          "films",
}

# ---------------------------------------------------------------------------
# Drug-form defaults
# Returns (verb, route_text, unit, default_qty)
#   default_qty = int 1, or the string "___" when the quantity cannot be inferred
# ---------------------------------------------------------------------------
_FORM_DEFAULTS: dict[str, tuple[str, str | None, str | None, object]] = {
    "Tablet":      ("Take",    "by mouth",              "tablet",       1),
    "Capsule":     ("Take",    "by mouth",              "capsule",      1),
    "Liquid":      ("Take",    "by mouth",              "mL",           "___"),
    "Injection":   ("Inject",  "subcutaneously",        "mL",           "___"),
    "Patch":       ("Apply",   "to skin",               "patch",        1),
    "Film":        ("Place",   "under the tongue",      "film",         1),
    "Topical":     ("Apply",   "to the affected area",  None,           None),
    "Inhaler":     ("Inhale",  None,                    "puff",         "___"),
    "Drops":       ("Instil",  "as directed",           "drop",         2),
    "Suppository": ("Insert",  "rectally",              "suppository",  1),
    "Powder":      ("Take",    "by mouth",              "dose",         "___"),
    "Unknown":     ("Take",    "as directed",           "dose",         None),
}

_DEFAULT_FALLBACK = ("Take", "as directed", "dose", None)


def _form_defaults(drug_form: str | None) -> tuple[str, str | None, str | None, object]:
    if drug_form is None:
        return _DEFAULT_FALLBACK
    return _FORM_DEFAULTS.get(drug_form, _DEFAULT_FALLBACK)


def translate_sig(code_str: str, drug_form: str | None = None) -> str:
    """Translate a space-separated SIG code string to a human-readable instruction.

    Args:
        code_str:  Raw SIG input, e.g. ``"1 TAB PO QD CF"`` or ``"QD"``.
        drug_form: Value of ``DrugForm`` enum (e.g. ``"Tablet"``), used to
                   supply defaults when unit/route are omitted.

    Returns:
        A capitalised English instruction string.  Returns *code_str* unchanged
        if no recognisable tokens are found.
    """
    if not code_str or not code_str.strip():
        return ""

    tokens = code_str.strip().upper().split()

    qty: object = None         # numeric or string quantity ("one-half", "___")
    unit: str | None = None
    verb: str | None = None
    route_text: str | None = None
    freq: str | None = None
    modifiers: list[str] = []
    conditions: list[str] = []

    for token in tokens:
        # Numeric quantity?
        try:
            val = float(token)
            qty = int(val) if val == int(val) else val
            continue
        except ValueError:
            pass

        info = SIG_CODES.get(token)
        if info is None:
            continue  # unrecognised token — skip silently

        cat, expansion = info

        if cat == "verb":
            if verb is None:
                verb = expansion  # type: ignore[assignment]
        elif cat == "route":
            implied_verb, rt = expansion  # type: ignore[misc]
            if verb is None:
                verb = implied_verb
            route_text = rt
        elif cat == "location":
            implied_verb, loc = expansion  # type: ignore[misc]
            if verb is None:
                verb = implied_verb
            route_text = loc
        elif cat == "unit":
            if expansion == "one-half":  # type: ignore[comparison-overlap]
                qty = "one-half"
            else:
                unit = expansion  # type: ignore[assignment]
        elif cat == "freq":
            freq = expansion  # type: ignore[assignment]
        elif cat == "mod":
            modifiers.append(expansion)  # type: ignore[arg-type]
        elif cat == "cond":
            conditions.append(expansion)  # type: ignore[arg-type]

    # Fill missing parts from drug-form defaults
    form_verb, form_route, form_unit, form_qty = _form_defaults(drug_form)

    if verb is None:
        verb = form_verb
    if route_text is None:
        route_text = form_route
    if unit is None:
        unit = form_unit
    if qty is None:
        qty = form_qty

    # Pluralise unit when quantity is a whole number > 1
    if unit and isinstance(qty, (int, float)) and qty != 1:
        unit = _PLURALS.get(unit, unit)

    # Assemble sentence parts
    parts: list[str] = []
    if verb:
        parts.append(verb)
    if qty is not None:
        parts.append(str(qty))
    if unit:
        parts.append(unit)
    if route_text:
        parts.append(route_text)
    if freq:
        parts.append(freq)
    for mod in modifiers:
        parts.append(mod)
    for cond in conditions:
        parts.append(cond)

    if not parts:
        return code_str  # nothing parsed — return original input

    result = " ".join(parts)
    return result[0].upper() + result[1:]
