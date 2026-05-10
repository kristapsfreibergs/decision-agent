"""Create a SQLite demo database with sample procurement data.

Run from the repo root:
    PYTHONPATH=backend/src python scripts/create_demo_db.py

Creates data/demo.db with tables that match configs/data-sources/schema-map.json.
Used for testing the query_sql tool without a real company database.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def main() -> None:
    db_path = Path("data/demo.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # vendor_mgmt.proposals
    cur.execute("""
        CREATE TABLE IF NOT EXISTS "vendor_mgmt.proposals" (
            proposal_id      TEXT PRIMARY KEY,
            vendor_name      TEXT NOT NULL,
            unit_price_eur   REAL,
            delivery_weeks   INTEGER,
            iso27001_certified  INTEGER DEFAULT 0,
            gdpr_dpa_available  INTEGER DEFAULT 0,
            submitted_at     TEXT
        )
    """)
    cur.executemany(
        'INSERT OR REPLACE INTO "vendor_mgmt.proposals" VALUES (?,?,?,?,?,?,?)',
        [
            ("P001", "Lenovo EMEA",       1799.00, 6,  1, 1, "2026-03-15"),
            ("P002", "Dell Technologies", 1924.00, 8,  1, 1, "2026-03-18"),
            ("P003", "HP Inc. EMEA",      1850.00, 10, 0, 1, "2026-03-20"),
            ("P004", "Asus Europe",       1650.00, 12, 0, 1, "2026-03-22"),
            ("P005", "Acer EMEA",         1580.00, 14, 0, 1, "2026-03-25"),
        ],
    )

    # vendor_mgmt.rankings
    cur.execute("""
        CREATE TABLE IF NOT EXISTS "vendor_mgmt.rankings" (
            ranking_id        TEXT PRIMARY KEY,
            vendor_name       TEXT NOT NULL,
            overall_score     REAL,
            compliance_status TEXT,
            ranking_reason    TEXT,
            updated_at        TEXT
        )
    """)
    cur.executemany(
        'INSERT OR REPLACE INTO "vendor_mgmt.rankings" VALUES (?,?,?,?,?,?)',
        [
            ("R001", "Lenovo EMEA",       4.6, "APPROVED", "ISO 27001 confirmed; highest volume throughput in EU", "2026-01-10"),
            ("R002", "Dell Technologies", 4.4, "APPROVED", "ISO 27001 confirmed; minor SLA variance in Eastern EU", "2026-01-10"),
            ("R003", "HP Inc. EMEA",      4.0, "CONDITIONAL", "ISO 27001 EMEA logistics scope unconfirmed — requires RFQ attestation", "2026-01-10"),
            ("R004", "Asus Europe",       3.2, "RISK",     "ISO 27001 corporate only; EU fulfilment scope unverified", "2026-01-10"),
            ("R005", "Acer EMEA",         2.8, "RISK",     "ISO 27001 not confirmed for EU fulfilment operations", "2026-01-10"),
        ],
    )

    # compliance.certifications
    cur.execute("""
        CREATE TABLE IF NOT EXISTS "compliance.certifications" (
            cert_id           TEXT PRIMARY KEY,
            vendor_name       TEXT NOT NULL,
            certification_type TEXT,
            certifying_body   TEXT,
            certificate_number TEXT,
            valid_until       TEXT
        )
    """)
    cur.executemany(
        'INSERT OR REPLACE INTO "compliance.certifications" VALUES (?,?,?,?,?,?)',
        [
            ("C001", "Lenovo EMEA",       "ISO 27001:2022", "BSI",         "IS 660985",    "2026-09-14"),
            ("C002", "Dell Technologies", "ISO 27001:2022", "TÜV Rheinland","DE-22-ISO-0541","2027-03-01"),
            ("C003", "Lenovo EMEA",       "GDPR DPA",       "Self",        "GDPR-L-EU-01", "2099-12-31"),
            ("C004", "Dell Technologies", "GDPR DPA",       "Self",        "GDPR-D-EU-01", "2099-12-31"),
        ],
    )

    # finance.approved_budgets
    cur.execute("""
        CREATE TABLE IF NOT EXISTS "finance.approved_budgets" (
            budget_id         TEXT PRIMARY KEY,
            cost_centre       TEXT,
            budget_ceiling_eur REAL,
            approver_name     TEXT,
            fiscal_year       TEXT,
            approved_at       TEXT
        )
    """)
    cur.executemany(
        'INSERT OR REPLACE INTO "finance.approved_budgets" VALUES (?,?,?,?,?,?)',
        [
            ("B001", "IT-Infrastructure", 200000.00, "CFO Office", "2026", "2026-02-01"),
        ],
    )

    # market_intel.benchmarks
    cur.execute("""
        CREATE TABLE IF NOT EXISTS "market_intel.benchmarks" (
            benchmark_id       TEXT PRIMARY KEY,
            category           TEXT,
            median_price_eur   REAL,
            price_range_low_eur REAL,
            price_range_high_eur REAL,
            source             TEXT,
            published_date     TEXT
        )
    """)
    cur.executemany(
        'INSERT OR REPLACE INTO "market_intel.benchmarks" VALUES (?,?,?,?,?,?,?)',
        [
            ("M001", "Developer laptop 32GB/1TB EU enterprise 100-unit", 1850.0, 1400.0, 2200.0, "European Commission JRC ICT Benchmark 2026", "2026-01-10"),
        ],
    )

    # contracts.signed_agreements (past procurement history)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS "contracts.signed_agreements" (
            agreement_id      TEXT PRIMARY KEY,
            vendor_name       TEXT NOT NULL,
            contract_value_eur REAL,
            scope_summary     TEXT,
            signed_date       TEXT
        )
    """)
    cur.executemany(
        'INSERT OR REPLACE INTO "contracts.signed_agreements" VALUES (?,?,?,?,?)',
        [
            ("AGR001", "Lenovo EMEA", 85000.0, "50 ThinkPad T14s for Berlin office (2024 procurement)", "2024-08-15"),
            ("AGR002", "Dell Technologies", 42000.0, "25 Latitude 5450 for Warsaw office (2024)", "2024-11-20"),
        ],
    )

    conn.commit()
    conn.close()

    total = sum(
        conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]  # type: ignore
        for conn in [sqlite3.connect(str(db_path))]
        for t in [
            "vendor_mgmt.proposals", "vendor_mgmt.rankings", "compliance.certifications",
            "finance.approved_budgets", "market_intel.benchmarks", "contracts.signed_agreements",
        ]
    )
    print(f"Created {db_path} with {total} total rows across 6 tables.")


if __name__ == "__main__":
    main()
