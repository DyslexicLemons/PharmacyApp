"""seed_data.py — export or import drug/insurance catalog data.

Usage
-----
Export current local data to a JSON fixture file:
    python seed_data.py export seed_data.json

Import a fixture file into the target database (idempotent — skips records
that already exist by NDC / plan_id):
    python seed_data.py import seed_data.json

The DATABASE_URL environment variable controls which database is used.
Override for prod:
    DATABASE_URL=postgresql://... python seed_data.py import seed_data.json

Run inside Docker:
    docker compose exec backend python seed_data.py export seed_data.json
    docker compose exec backend python seed_data.py import seed_data.json

Run as an ECS one-off task (prod):
    aws ecs run-task ... --overrides '{"containerOverrides":[{"name":"backend",
      "command":["python","seed_data.py","import","seed_data.json"]}]}'
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal

# ---------------------------------------------------------------------------
# Bootstrap: load app environment (mirrors what main.py does at startup)
# ---------------------------------------------------------------------------
from app.secrets import load_aws_secrets
load_aws_secrets()

from app.database import SessionLocal
from app.models import Drug, DrugForm, Formulary, InsuranceCompany, Stock


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def _decimal(val) -> str | None:
    if val is None:
        return None
    return str(val)


def export_seed(path: str) -> None:
    db = SessionLocal()
    try:
        drugs = db.query(Drug).all()
        companies = db.query(InsuranceCompany).all()

        drug_rows = []
        for d in drugs:
            stock: Stock | None = db.query(Stock).filter(Stock.drug_id == d.id).first()
            drug_rows.append({
                "drug_name": d.drug_name,
                "ndc": d.ndc,
                "manufacturer": d.manufacturer,
                "cost": _decimal(d.cost),
                "niosh": bool(d.niosh),
                "drug_class": d.drug_class,
                "description": d.description,
                "drug_form": d.drug_form.value if d.drug_form else None,
                "stock_quantity": int(stock.quantity) if stock and stock.quantity else 0,
                "stock_package_size": int(stock.package_size) if stock and stock.package_size else 100,
            })

        company_rows = []
        for c in companies:
            formulary_rows = []
            for f in db.query(Formulary).filter(Formulary.insurance_company_id == c.id).all():
                drug = db.query(Drug).filter(Drug.id == f.drug_id).first()
                formulary_rows.append({
                    "drug_ndc": drug.ndc if drug else None,
                    "drug_name": drug.drug_name if drug else None,
                    "tier": f.tier,
                    "copay_per_30": _decimal(f.copay_per_30),
                    "not_covered": bool(f.not_covered),
                })
            company_rows.append({
                "plan_id": c.plan_id,
                "plan_name": c.plan_name,
                "bin_number": c.bin_number,
                "pcn": c.pcn,
                "phone_number": c.phone_number,
                "formulary": formulary_rows,
            })

        payload = {"drugs": drug_rows, "insurance_companies": company_rows}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        print(f"Exported {len(drug_rows)} drug(s) and {len(company_rows)} insurance company/companies to {path}")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def import_seed(path: str) -> None:
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)

    db = SessionLocal()
    try:
        drugs_imported = 0
        drugs_skipped = 0

        # Map from NDC (or name) → db Drug.id so formulary can reference it
        ndc_to_id: dict[str, int] = {}

        for row in payload.get("drugs", []):
            ndc = row.get("ndc")

            # Find existing by NDC first, then fall back to name
            existing = None
            if ndc:
                existing = db.query(Drug).filter(Drug.ndc == ndc).first()
            if not existing:
                existing = db.query(Drug).filter(Drug.drug_name == row["drug_name"]).first()

            if existing:
                ndc_to_id[ndc or row["drug_name"]] = existing.id
                drugs_skipped += 1
                continue

            form_val = row.get("drug_form")
            drug_form = None
            if form_val:
                try:
                    drug_form = DrugForm(form_val)
                except ValueError:
                    drug_form = DrugForm.unknown

            drug = Drug(
                drug_name=row["drug_name"],
                ndc=ndc,
                manufacturer=row.get("manufacturer"),
                cost=Decimal(row["cost"]) if row.get("cost") else Decimal("0"),
                niosh=row.get("niosh", False),
                drug_class=row.get("drug_class"),
                description=row.get("description"),
                drug_form=drug_form,
            )
            db.add(drug)
            db.flush()  # get drug.id before commit

            stock = Stock(
                drug_id=drug.id,
                quantity=row.get("stock_quantity", 0),
                package_size=row.get("stock_package_size", 100),
            )
            db.add(stock)

            ndc_to_id[ndc or row["drug_name"]] = drug.id
            drugs_imported += 1

        db.flush()
        print(f"Drugs: {drugs_imported} imported, {drugs_skipped} already existed (skipped)")

        companies_imported = 0
        companies_skipped = 0
        formulary_imported = 0

        for row in payload.get("insurance_companies", []):
            existing = db.query(InsuranceCompany).filter(
                InsuranceCompany.plan_id == row["plan_id"]
            ).first()

            if existing:
                companies_skipped += 1
                company_id = existing.id
            else:
                company = InsuranceCompany(
                    plan_id=row["plan_id"],
                    plan_name=row.get("plan_name"),
                    bin_number=row.get("bin_number"),
                    pcn=row.get("pcn"),
                    phone_number=row.get("phone_number"),
                )
                db.add(company)
                db.flush()
                company_id = company.id
                companies_imported += 1

            for f_row in row.get("formulary", []):
                # Resolve drug_id
                drug_ndc = f_row.get("drug_ndc")
                drug_name = f_row.get("drug_name")
                drug_id = ndc_to_id.get(drug_ndc or drug_name or "")
                if not drug_id:
                    # Try live lookup
                    d = None
                    if drug_ndc:
                        d = db.query(Drug).filter(Drug.ndc == drug_ndc).first()
                    if not d and drug_name:
                        d = db.query(Drug).filter(Drug.drug_name == drug_name).first()
                    if not d:
                        print(f"  Warning: formulary entry references unknown drug '{drug_ndc or drug_name}' — skipped")
                        continue
                    drug_id = d.id

                already = db.query(Formulary).filter(
                    Formulary.insurance_company_id == company_id,
                    Formulary.drug_id == drug_id,
                ).first()
                if already:
                    continue

                db.add(Formulary(
                    insurance_company_id=company_id,
                    drug_id=drug_id,
                    tier=f_row.get("tier"),
                    copay_per_30=Decimal(f_row["copay_per_30"]) if f_row.get("copay_per_30") else None,
                    not_covered=f_row.get("not_covered", False),
                ))
                formulary_imported += 1

        db.commit()
        print(
            f"Insurance companies: {companies_imported} imported, {companies_skipped} already existed (skipped)\n"
            f"Formulary entries: {formulary_imported} imported"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()
    path = sys.argv[2]

    if command == "export":
        export_seed(path)
    elif command == "import":
        import_seed(path)
    else:
        print(f"Unknown command '{command}'. Use 'export' or 'import'.")
        sys.exit(1)


if __name__ == "__main__":
    main()
