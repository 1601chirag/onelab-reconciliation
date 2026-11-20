# ReconIQ — Payment Reconciliation Intelligence

**Author:** Chirag Poojari  
**Email:** chirag.poojari@mitwpu.edu.in  
**Institution:** MIT World Peace University, Pune  
**Assessment:** Onelab — November 2026

---

## Problem Statement

A payments company records every transaction on its platform. Banks independently report
settled funds. At month-end these two datasets should agree, but they frequently do not.

ReconIQ reconciles platform transactions against bank settlements, identifies the root
cause of every discrepancy, and presents findings through a clean fintech dashboard.

---

## Technology Stack

| Component | Technology |
|---|---|
| Frontend | Streamlit 1.40 |
| Data processing | Pandas 2.2 |
| Monetary arithmetic | Python `decimal.Decimal` |
| Testing | Pytest 8.3 |
| Language | Python 3.11 |
| Hosting | Streamlit Community Cloud (free tier) |

No paid APIs, no database, no authentication required. Works completely offline.

---

## Architecture

```
sample_data.py      →  DataFrames (reproducible, seed=42)
                           │
reconciliation.py   →  ReconciliationResult (pure business logic, no Streamlit)
                           │
app.py              →  Streamlit dashboard (consumes result, renders UI)
                           │
tests/              →  Pytest suite (imports reconciliation.py directly)
```

**Key design decisions:**
- `reconciliation.py` has zero Streamlit imports — independently testable.
- Duplicates removed before any financial totals are computed.
- All monetary arithmetic uses `Decimal` — no floating-point rounding errors.
- Transaction ID is the sole matching key — amount equality alone never triggers a match.

---

## Project Structure

```
onelab-reconciliation/
├── app.py                      Streamlit dashboard
├── reconciliation.py           Reconciliation engine
├── sample_data.py              Synthetic dataset generator
├── requirements.txt            Python dependencies
├── README.md                   This file
├── SUBMISSION_NOTES.md         Assumptions, scenarios, demo script
├── .gitignore
└── tests/
    ├── __init__.py
    └── test_reconciliation.py  Pytest test suite
```

---

## Installation and Running — macOS (M4)

```bash
# 1. Navigate to project directory
cd onelab-reconciliation

# 2. Remove any previous environment if re-running from scratch
rm -rf .venv

# 3. Create virtual environment
python3.11 -m venv .venv

# 4. Activate
source .venv/bin/activate

# 5. Install dependencies
pip install -r requirements.txt

# 6. Run the application
streamlit run app.py

# 7. Run tests (open a second terminal tab, activate .venv first)
source .venv/bin/activate
python -m pytest -v
```

## Installation and Running — Windows

```bat
cd onelab-reconciliation
py -3.11 -m venv .venv
.venv\Scripts\activate
py -3.11 -m pip install -r requirements.txt
py -3.11 -m streamlit run app.py

:: In a second terminal for tests:
py -3.11 -m pytest -v
```

---

## CSV Format

### Platform Transactions

| Column | Type | Description |
|---|---|---|
| transaction_id | string | Unique identifier (`TXN-XXXXXXXX`) |
| transaction_date | YYYY-MM-DD | Date of platform transaction |
| customer_id | string | Customer identifier |
| transaction_type | PAYMENT / REFUND | Type |
| amount | decimal | Amount in INR (positive) |
| currency | string | `INR` |
| status | SUCCESS / FAILED / PENDING | Status |
| original_transaction_id | string | For refunds: original transaction ref |

### Bank Settlements

| Column | Type | Description |
|---|---|---|
| settlement_id | string | Unique settlement identifier |
| transaction_id | string | References platform transaction_id |
| settlement_date | YYYY-MM-DD | Bank settlement date |
| amount | decimal | Settled amount in INR |
| currency | string | `INR` |
| settlement_reference | string | Bank internal reference |
| entry_type | CREDIT / REFUND | Bank entry type |

---

## Reconciliation Methodology

1. **Validate** — check required columns, parse dates and amounts, reject malformed records.
2. **De-duplicate** — identify and remove duplicate bank/platform records before any totals.
3. **Match** — join on `transaction_id`. Amount equality alone is never sufficient.
4. **Classify** each pair with one of these categories:
   - `MATCHED` — exact amount match within reporting month.
   - `TIMING_DIFFERENCE` — settled after reporting month end.
   - `ROUNDING_DIFFERENCE` — |diff| ≤ ₹0.01 (cumulative tracked separately).
   - `AMOUNT_MISMATCH` — |diff| > ₹0.01.
   - `MISSING_SETTLEMENT` — platform transaction with no bank entry.
   - `ORPHAN_REFUND` — bank REFUND entry with no platform transaction.
   - `UNMATCHED_BANK_ENTRY` — bank CREDIT with no platform transaction.
   - `DUPLICATE_SETTLEMENT` / `DUPLICATE_TRANSACTION` — excluded from totals.
5. **Aggregate** — sum totals from de-duplicated clean data only.

---

## Planted Discrepancy Scenarios

| # | Scenario | Transaction ID | Category |
|---|---|---|---|
| 1 | Next-Month Settlement | `TXN-NMS00001` | `TIMING_DIFFERENCE` |
| 2 | Rounding Differences | `TXN-RND00001` – `TXN-RND00010` | `ROUNDING_DIFFERENCE` |
| 3 | Duplicate Settlement | `TXN-DUP00001` | `DUPLICATE_SETTLEMENT` |
| 4 | Orphan Refund | `TXN-ORF00001` | `ORPHAN_REFUND` |


---

## Assumptions

- Reporting currency: INR only.
- Individual rounding tolerance: ₹0.01.
- Reporting month defaults to October 2026.
- A transaction settled on Nov 1 (Oct reporting) is a timing difference, not missing.
- Duplicate detection key: `transaction_id + amount + settlement_date + entry_type`.
- Refund amounts stored as positive values with `entry_type = REFUND`.
