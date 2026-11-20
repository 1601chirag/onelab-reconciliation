"""
Synthetic dataset generator for ReconIQ payment reconciliation demo.
Fixed seed (42) ensures reproducibility. Generates exactly four planted discrepancies.
"""

import random
import string
from decimal import Decimal
from datetime import date, timedelta
import pandas as pd

SEED = 42
random.seed(SEED)

NORMAL_COUNT = 95  # normal matched transactions
CURRENCY = "INR"

# ── helpers ──────────────────────────────────────────────────────────────────

def _rand_id(prefix: str, n: int = 8) -> str:
    return prefix + "".join(random.choices(string.digits, k=n))


def _rand_customer() -> str:
    return "CUST" + "".join(random.choices(string.digits, k=6))


def _rand_amount(lo: float = 500.0, hi: float = 50000.0) -> Decimal:
    raw = random.uniform(lo, hi)
    return Decimal(str(round(raw, 2)))


def _rand_date_in_oct() -> date:
    start = date(2026, 10, 1)
    return start + timedelta(days=random.randint(0, 29))  # Oct 1-30


def _settlement_ref(txn_id: str) -> str:
    return "SREF-" + txn_id[4:]


# ── planted discrepancy seeds (fixed values for determinism) ──────────────────

# 1. NEXT-MONTH SETTLEMENT  — platform Oct 31, bank Nov 1
NMS_TXN_ID  = "TXN-NMS00001"
NMS_CUST    = "CUST-NMS001"
NMS_AMOUNT  = Decimal("12750.00")
NMS_PLAT_DT = date(2026, 10, 31)
NMS_BANK_DT = date(2026, 11, 1)

# 2. ROUNDING DIFFERENCES — 10 transactions, each off by ₹0.005 (within ₹0.01 tolerance)
RND_COUNT = 10
RND_TXN_IDS = [f"TXN-RND{i:05d}" for i in range(1, RND_COUNT + 1)]
RND_AMOUNTS_PLAT = [Decimal("5000.00")] * RND_COUNT          # platform amount
RND_AMOUNTS_BANK = [Decimal("4999.995").quantize(Decimal("0.01"))  # ₹4999.99 each
                    ] * RND_COUNT                                   # so diff = ₹0.01 each → cumulative ₹0.10

# 3. DUPLICATE SETTLEMENT
DUP_TXN_ID   = "TXN-DUP00001"
DUP_CUST     = "CUST-DUP001"
DUP_AMOUNT   = Decimal("8500.00")
DUP_PLAT_DT  = date(2026, 10, 15)
DUP_BANK_DT  = date(2026, 10, 16)

# 4. ORPHAN REFUND — bank refund with no platform original
ORF_TXN_ID   = "TXN-ORF00001"   # referenced in bank but absent from platform
ORF_AMOUNT   = Decimal("3200.00")
ORF_BANK_DT  = date(2026, 10, 20)


# ── main generators ───────────────────────────────────────────────────────────

def generate_platform_transactions() -> pd.DataFrame:
    """Return platform transactions DataFrame with all four planted scenarios."""
    rows = []

    # --- NORMAL transactions -------------------------------------------------
    for _ in range(NORMAL_COUNT):
        txn_id = _rand_id("TXN-")
        rows.append({
            "transaction_id":          txn_id,
            "transaction_date":        _rand_date_in_oct().isoformat(),
            "customer_id":             _rand_customer(),
            "transaction_type":        "PAYMENT",
            "amount":                  str(_rand_amount()),
            "currency":                CURRENCY,
            "status":                  "SUCCESS",
            "original_transaction_id": "",
        })

    # --- Scenario 1: NEXT-MONTH SETTLEMENT -----------------------------------
    rows.append({
        "transaction_id":          NMS_TXN_ID,
        "transaction_date":        NMS_PLAT_DT.isoformat(),
        "customer_id":             NMS_CUST,
        "transaction_type":        "PAYMENT",
        "amount":                  str(NMS_AMOUNT),
        "currency":                CURRENCY,
        "status":                  "SUCCESS",
        "original_transaction_id": "",
    })

    # --- Scenario 2: ROUNDING DIFFERENCES ------------------------------------
    for txn_id, amt in zip(RND_TXN_IDS, RND_AMOUNTS_PLAT):
        rows.append({
            "transaction_id":          txn_id,
            "transaction_date":        date(2026, 10, 10).isoformat(),
            "customer_id":             _rand_customer(),
            "transaction_type":        "PAYMENT",
            "amount":                  str(amt),
            "currency":                CURRENCY,
            "status":                  "SUCCESS",
            "original_transaction_id": "",
        })

    # --- Scenario 3: DUPLICATE SETTLEMENT (platform side is clean) -----------
    rows.append({
        "transaction_id":          DUP_TXN_ID,
        "transaction_date":        DUP_PLAT_DT.isoformat(),
        "customer_id":             DUP_CUST,
        "transaction_type":        "PAYMENT",
        "amount":                  str(DUP_AMOUNT),
        "currency":                CURRENCY,
        "status":                  "SUCCESS",
        "original_transaction_id": "",
    })

    # --- Scenario 4: ORPHAN REFUND (original is NOT in platform) -------------
    # (no row added — ORF_TXN_ID is intentionally absent from platform)

    random.shuffle(rows)
    df = pd.DataFrame(rows)
    return df


def generate_bank_settlements(platform_df: pd.DataFrame) -> pd.DataFrame:
    """Return bank settlements DataFrame derived from platform, with planted discrepancies."""
    rows = []

    plat_map = {
        row["transaction_id"]: row
        for _, row in platform_df.iterrows()
    }

    # Build settlements for each platform transaction
    for txn_id, plat_row in plat_map.items():
        plat_date = date.fromisoformat(plat_row["transaction_date"])
        plat_amt  = Decimal(plat_row["amount"])

        # --- Scenario 1: NMS — settle on Nov 1 -------------------------------
        if txn_id == NMS_TXN_ID:
            rows.append({
                "settlement_id":        _rand_id("SET-"),
                "transaction_id":       txn_id,
                "settlement_date":      NMS_BANK_DT.isoformat(),
                "amount":               str(NMS_AMOUNT),
                "currency":             CURRENCY,
                "settlement_reference": _settlement_ref(txn_id),
                "entry_type":           "CREDIT",
            })
            continue

        # --- Scenario 2: ROUNDING — bank settles ₹0.01 less per txn ----------
        if txn_id in RND_TXN_IDS:
            bank_amt = plat_amt - Decimal("0.01")  # diff = ₹0.01, within tolerance
            rows.append({
                "settlement_id":        _rand_id("SET-"),
                "transaction_id":       txn_id,
                "settlement_date":      (plat_date + timedelta(days=1)).isoformat(),
                "amount":               str(bank_amt),
                "currency":             CURRENCY,
                "settlement_reference": _settlement_ref(txn_id),
                "entry_type":           "CREDIT",
            })
            continue

        # --- Scenario 3: DUPLICATE — two identical bank rows -----------------
        if txn_id == DUP_TXN_ID:
            settle_dt = (plat_date + timedelta(days=1)).isoformat()
            sref      = _settlement_ref(txn_id)
            for _ in range(2):   # genuine duplicate
                rows.append({
                    "settlement_id":        _rand_id("SET-"),
                    "transaction_id":       txn_id,
                    "settlement_date":      settle_dt,
                    "amount":               str(DUP_AMOUNT),
                    "currency":             CURRENCY,
                    "settlement_reference": sref,
                    "entry_type":           "CREDIT",
                })
            continue

        # --- NORMAL settlement (T+1) -----------------------------------------
        rows.append({
            "settlement_id":        _rand_id("SET-"),
            "transaction_id":       txn_id,
            "settlement_date":      (plat_date + timedelta(days=1)).isoformat(),
            "amount":               str(plat_amt),
            "currency":             CURRENCY,
            "settlement_reference": _settlement_ref(txn_id),
            "entry_type":           "CREDIT",
        })

    # --- Scenario 4: ORPHAN REFUND — no platform transaction for this id -----
    rows.append({
        "settlement_id":        _rand_id("SET-"),
        "transaction_id":       ORF_TXN_ID,
        "settlement_date":      ORF_BANK_DT.isoformat(),
        "amount":               str(ORF_AMOUNT),
        "currency":             CURRENCY,
        "settlement_reference": _settlement_ref(ORF_TXN_ID),
        "entry_type":           "REFUND",
    })

    random.shuffle(rows)
    df = pd.DataFrame(rows)
    return df


def get_sample_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (platform_df, bank_df) with planted discrepancies."""
    platform_df = generate_platform_transactions()
    bank_df     = generate_bank_settlements(platform_df)
    return platform_df, bank_df


# ── planted scenario metadata (for UI reference) ──────────────────────────────

PLANTED_SCENARIOS = {
    "next_month_settlement": {
        "transaction_id": NMS_TXN_ID,
        "platform_date":  NMS_PLAT_DT.isoformat(),
        "bank_date":      NMS_BANK_DT.isoformat(),
        "amount":         str(NMS_AMOUNT),
        "description":    (
            f"Transaction {NMS_TXN_ID} was processed on Oct 31 but the bank "
            "settled it on Nov 1. This is a timing difference, not a missing settlement."
        ),
    },
    "rounding_differences": {
        "transaction_ids": RND_TXN_IDS,
        "individual_diff": "₹0.01 per transaction (within ₹0.01 tolerance)",
        "cumulative_diff": f"₹{RND_COUNT * Decimal('0.01'):.2f} aggregate",
        "description":     (
            f"{RND_COUNT} transactions each differ by ₹0.01 — within individual tolerance. "
            f"Cumulative rounding residual = ₹{RND_COUNT * Decimal('0.01'):.2f}."
        ),
    },
    "duplicate_settlement": {
        "transaction_id": DUP_TXN_ID,
        "amount":         str(DUP_AMOUNT),
        "description":    (
            f"Transaction {DUP_TXN_ID} has two identical bank settlement entries. "
            "Only one is counted; the duplicate is flagged separately."
        ),
    },
    "orphan_refund": {
        "transaction_id": ORF_TXN_ID,
        "amount":         str(ORF_AMOUNT),
        "bank_date":      ORF_BANK_DT.isoformat(),
        "description":    (
            f"Bank entry for {ORF_TXN_ID} is a REFUND with no corresponding "
            "platform transaction. Classified as orphan refund."
        ),
    },
}