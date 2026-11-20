# Submission Notes — ReconIQ

**Author:** Chirag Poojari  
**Email:** chirag.poojari@mitwpu.edu.in  
**Institution:** MIT World Peace University, Pune  
**Assessment:** Onelab — November 2026

---

## 1. Assumptions

1. **Currency:** INR only. No multi-currency conversion modelled.
2. **Rounding tolerance:** ₹0.01 per transaction (configurable via `INDIVIDUAL_TOLERANCE` in `reconciliation.py`).
3. **Reporting month:** October 2026 by default. Month selector allows Nov 2026 and Sep 2026.
4. **Matching key:** `transaction_id` is the sole join key. Amount equality alone is not a match.
5. **Duplicate detection:** Bank rows sharing `transaction_id + amount + settlement_date + entry_type` are duplicates. First occurrence kept; rest excluded from all totals.
6. **Platform duplicates:** Rows sharing `transaction_id` are platform duplicates. First kept.
7. **Orphan refunds:** A bank `REFUND` entry whose `transaction_id` has no platform record.
8. **Timing difference:** Bank `settlement_date` after reporting month end, with an existing platform transaction — not permanently missing.
9. **Refund amounts:** Positive values in both datasets; `entry_type` distinguishes credits from refunds.
10. **Seed:** `random.seed(42)` guarantees reproducible synthetic data.

---

## 2. Planted Discrepancy Scenarios

### Scenario 1 — Next-Month Settlement

- **Transaction ID:** `TXN-NMS00001`
- **Platform date:** 2026-10-31
- **Bank settlement date:** 2026-11-01
- **Amount:** ₹12,750.00
- **Detection logic:** `settlement_date > reporting_month_end` → `TIMING_DIFFERENCE`
- **Why it matters:** Incorrectly treating this as missing would create a false ₹12,750 discrepancy in the October close.
- **Expected output:** `TIMING_DIFFERENCE` with an explanation naming both dates and confirming it is not permanently missing.

### Scenario 2 — Rounding Differences

- **Transaction IDs:** `TXN-RND00001` through `TXN-RND00010` (10 transactions)
- **Platform amount per transaction:** ₹5,000.00
- **Bank amount per transaction:** ₹4,999.99 (diff = ₹0.01)
- **Individual difference:** ₹0.01 — within the ₹0.01 tolerance
- **Cumulative residual:** ₹0.10
- **Detection logic:** `0 < diff <= INDIVIDUAL_TOLERANCE` → `ROUNDING_DIFFERENCE`; residuals summed in `cumulative_rounding_diff`
- **Why it matters:** Each transaction individually passes the tolerance check, but ₹0.10 aggregate is a real financial exposure requiring disclosure.
- **Expected output:** 10 rows as `ROUNDING_DIFFERENCE`; cumulative residual ₹0.10 displayed prominently.

### Scenario 3 — Duplicate Settlement

- **Transaction ID:** `TXN-DUP00001`
- **Amount:** ₹8,500.00
- **Bank entries:** 2 (identical `transaction_id + amount + settlement_date + entry_type`)
- **Detection logic:** `DataFrame.duplicated(keep="first")`
- **Why it matters:** Without deduplication, bank total overstated by ₹8,500.
- **Expected output:** One bank row kept for matching; second in `result.duplicates` as `DUPLICATE_SETTLEMENT`; `total_bank_entries = 1` for this transaction.

### Scenario 4 — Orphan Refund

- **Transaction ID:** `TXN-ORF00001`
- **Amount:** ₹3,200.00
- **Bank entry type:** REFUND
- **Platform record:** Absent (intentionally)
- **Detection logic:** `transaction_id` not in platform after matching; `entry_type == REFUND` → `ORPHAN_REFUND`
- **Why it matters:** An unexplained refund could indicate fraud or a system error; must be quarantined.
- **Expected output:** `ORPHAN_REFUND` classification; explanation confirms original payment absent from platform records.

---

## 3. Test Cases and Expected Results

| # | Test Class | Scenario | Expected Result |
|---|---|---|---|
| 1 | `TestMatched` | Exact platform/bank match | `matched_count=1`, `unreconciled_amount=0` |
| 2 | `TestMissingSettlement` | No bank entry for platform txn | `MISSING_SETTLEMENT` category |
| 3 | `TestTimingDifference` | Bank settles Nov 1 for Oct period | `TIMING_DIFFERENCE`, not `MISSING_SETTLEMENT` |
| 4 | `TestDuplicatePlatformTransaction` | Two identical platform rows | Duplicate excluded; `total_platform_txns=1` |
| 5 | `TestDuplicateBankSettlement` | Two identical bank rows | Duplicate excluded; `total_bank_amount=1×amount` |
| 6 | `TestOrphanRefund` | Bank REFUND, no platform record | `ORPHAN_REFUND`, count=1 |
| 7 | `TestRoundingTolerance` (within) | ₹0.01 diff | `ROUNDING_DIFFERENCE`, not `AMOUNT_MISMATCH` |
| 8 | `TestRoundingTolerance` (exceeds) | ₹0.02 diff | `AMOUNT_MISMATCH` |
| 9 | `TestCumulativeRounding` | 10 × ₹0.01 diff | `cumulative_rounding_diff = ₹0.10` |
| 10 | `TestInvalidDates` | Non-parseable date strings | Errors list populated or row dropped |
| 11 | `TestInvalidAmounts` | Non-numeric amount strings | Errors list populated or row dropped |
| 12 | `TestMissingColumns` | Required column absent | `result.errors` non-empty |
| 13 | `TestEmptyDatasets` | Empty / None DataFrames | `result.errors` non-empty |
| 14 | `TestUnmatchedBankEntry` | Bank CREDIT, no platform record | `UNMATCHED_BANK_ENTRY` category |
| 15 | `TestDuplicatePrevention` | 2 bank rows → 1 count | `total_bank_entries=1`, `total_bank_amount=1×amount` |
| 16 | `TestReconciliationTotals` | Full sample data | All 4 scenarios detected, rate ≥ 80%, no errors |

---

## 4. Demo Recording Script (~3–4 minutes)

**[0:00–0:20] Introduction**  
"This is ReconIQ — a payment reconciliation tool built for the Onelab assessment. It reconciles platform transactions against bank settlements, classifies every discrepancy, and presents findings through a clean dashboard. I'm Chirag Poojari from MIT World Peace University."

**[0:20–0:50] Dashboard overview**  
Navigate to the browser. Walk through the six KPI cards. Note sample data loaded automatically with no setup required.

**[0:50–1:20] Scenario 1 — Timing Difference**  
In the Transaction Investigation table, filter Category to `TIMING_DIFFERENCE`. Show `TXN-NMS00001`. Read the explanation: "October 31 platform, November 1 bank — timing difference, not a missing payment."

**[1:20–1:50] Scenario 2 — Rounding**  
Clear filters. Point to the yellow cumulative rounding callout: "10 transactions, ₹0.01 each — within individual tolerance. Cumulative residual ₹0.10." Filter to `ROUNDING_DIFFERENCE` to show all 10 rows.

**[1:50–2:20] Scenario 3 — Duplicate**  
Scroll to the Duplicate Records section. Show `TXN-DUP00001`. Return to KPI cards — note de-duplicated bank count.

**[2:20–2:50] Scenario 4 — Orphan Refund**  
Filter Category to `ORPHAN_REFUND`. Show `TXN-ORF00001` — ₹3,200 refund with no platform record.

**[2:50–3:20] Upload and download**  
Download platform CSV, then switch sidebar to Upload mode and re-upload it. Show the dashboard recalculates. Download the full report and discrepancies CSV.

**[3:20–3:40] Tests**  
Switch to terminal. Run `python -m pytest -v`. Show all tests passing.

**[3:40–4:00] Closing**  
"ReconIQ correctly identifies all four discrepancy scenarios, prevents double-counting, and uses Decimal arithmetic throughout. Thank you."

---

## 5. Deployment to Streamlit Community Cloud

**Step 1 — Initialise Git repository**
```bash
cd "/Users/chirag/Downloads/OneLab Assessment/onelab-reconciliation"
git init
git add .
git commit -m "feat: ReconIQ payment reconciliation — Onelab assessment"
```

**Step 2 — Create GitHub remote**
1. Go to https://github.com/new
2. Create a public repository named `onelab-reconciliation`
3. Do not initialise with README

**Step 3 — Push**
```bash
git remote add origin https://github.com/1601chirag/onelab-reconciliation.git
git branch -M main
git push -u origin main
```

**Step 4 — Deploy**
1. Go to https://share.streamlit.io
2. Sign in with GitHub
3. Click New app
4. Repository: `1601chirag/onelab-reconciliation`
5. Branch: `main`
6. Main file: `app.py`
7. Click Deploy

No environment variables or secrets required. Deployment completes in 2–3 minutes.

---

## 6. Production Limitations

1. **Partial and batch-level settlements are not modelled.** Real banks often consolidate multiple transactions into a single settlement batch. The current engine matches one-to-one on `transaction_id`; batch-level reconciliation requiring amount-splitting or batch-to-many matching requires a substantially more complex matching graph.

2. **No persistent audit log or idempotency guarantees.** In production, every reconciliation run must be stamped with a unique run ID, and all classification decisions must be written to an immutable audit trail with timestamps and operator identity.

3. **Multi-currency, chargeback, and bank-specific settlement rules are out of scope.** Live payment platforms handle FX conversion at settlement time, chargeback reversals arriving weeks later, bank-specific cut-off times, and holiday calendars — all requiring dedicated rule engines and external data feeds.