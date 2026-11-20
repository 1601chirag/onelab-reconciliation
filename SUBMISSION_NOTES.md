# Submission Notes — ReconIQ

**Author:** Chirag Poojari  
**Email:** chirag.poojari@mitwpu.edu.in  
**Institution:** MIT World Peace University, Pune  
**Assessment:** Onelab — November 2026

---

## Assumptions

1. Currency: INR only. No multi-currency conversion modelled.
2. Individual rounding tolerance: ₹0.01 per transaction (configurable via `INDIVIDUAL_TOLERANCE` in `reconciliation.py`).
3. Reporting month defaults to October 2026. Month selector allows Sep and Nov 2026.
4. Matching key: `transaction_id` only. Amount equality alone is never a match.
5. Duplicate detection key: `transaction_id + amount + settlement_date + entry_type`.
6. Bank refund amounts are stored as positive values; `entry_type = REFUND` distinguishes them.
7. `random.seed(42)` ensures reproducible synthetic data across all runs.

---

## Planted Discrepancy Scenarios

| # | Scenario | Transaction ID | Category |
|---|---|---|---|
| 1 | Next-Month Settlement | `TXN-NMS00001` | `TIMING_DIFFERENCE` |
| 2 | Rounding Differences (×10) | `TXN-RND00001` – `TXN-RND00010` | `ROUNDING_DIFFERENCE` |
| 3 | Duplicate Bank Settlement | `TXN-DUP00001` | `DUPLICATE_SETTLEMENT` |
| 4 | Orphan Refund | `TXN-ORF00001` | `ORPHAN_REFUND` |

**Scenario 1:** Transaction processed Oct 31, bank settled Nov 1. Classified as a timing difference — not a missing payment.

**Scenario 2:** 10 transactions each differ by ₹0.01 (within individual tolerance). Cumulative residual = ₹0.10, disclosed separately.

**Scenario 3:** Two identical bank entries for the same transaction. Second entry excluded from all financial totals.

**Scenario 4:** Bank REFUND entry with no corresponding platform transaction. Flagged as orphan — potential fraud or system error.

---

## Test Coverage

15 test classes covering: exact match, missing settlement, timing difference, platform duplicate, bank duplicate, orphan refund, individual rounding tolerance, cumulative rounding, invalid dates, invalid amounts, missing columns, empty datasets, unmatched bank entries, duplicate prevention, and full sample data validation.

Run with:
```bash
python -m pytest -v
```

---

## Production Limitations

1. Batch-level and partial settlements are not modelled — engine matches one-to-one on `transaction_id` only.
2. No persistent audit log or idempotency guarantees — required in any production reconciliation system.
3. Multi-currency, chargeback, and bank-specific settlement rules are out of scope.