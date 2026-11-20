"""
ReconIQ — Core reconciliation engine.
Pure Python / Pandas / Decimal. No Streamlit dependency.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────

INDIVIDUAL_TOLERANCE: Decimal = Decimal("0.01")   # per-transaction rounding threshold
REPORTING_MONTH_YEAR: tuple[int, int] = (2026, 10)  # default October 2026

REQUIRED_PLATFORM_COLS = {
    "transaction_id", "transaction_date", "customer_id",
    "transaction_type", "amount", "currency", "status",
    "original_transaction_id",
}

REQUIRED_BANK_COLS = {
    "settlement_id", "transaction_id", "settlement_date",
    "amount", "currency", "settlement_reference", "entry_type",
}

# discrepancy category labels
class Cat:
    MATCHED              = "MATCHED"
    TIMING_DIFFERENCE    = "TIMING_DIFFERENCE"
    MISSING_SETTLEMENT   = "MISSING_SETTLEMENT"
    AMOUNT_MISMATCH      = "AMOUNT_MISMATCH"
    ROUNDING_DIFFERENCE  = "ROUNDING_DIFFERENCE"
    DUPLICATE_SETTLEMENT = "DUPLICATE_SETTLEMENT"
    DUPLICATE_TRANSACTION = "DUPLICATE_TRANSACTION"
    ORPHAN_REFUND        = "ORPHAN_REFUND"
    UNMATCHED_BANK_ENTRY = "UNMATCHED_BANK_ENTRY"
    INVALID_RECORD       = "INVALID_RECORD"


# ── result structures ─────────────────────────────────────────────────────────

@dataclass
class ReconciliationResult:
    """Full output of one reconciliation run."""

    # summary scalars
    total_platform_txns:      int     = 0
    total_bank_entries:       int     = 0
    matched_count:            int     = 0
    total_platform_amount:    Decimal = Decimal("0")
    total_bank_amount:        Decimal = Decimal("0")
    unreconciled_amount:      Decimal = Decimal("0")
    reconciliation_rate:      float   = 0.0

    # per-category counts
    missing_settlement_count: int = 0
    timing_difference_count:  int = 0
    duplicate_count:          int = 0
    orphan_refund_count:      int = 0
    amount_mismatch_count:    int = 0
    rounding_difference_count: int = 0
    unmatched_bank_count:     int = 0
    invalid_record_count:     int = 0

    # cumulative rounding
    cumulative_rounding_diff: Decimal = Decimal("0")

    # detailed DataFrames
    all_records:    pd.DataFrame = field(default_factory=pd.DataFrame)
    discrepancies:  pd.DataFrame = field(default_factory=pd.DataFrame)
    duplicates:     pd.DataFrame = field(default_factory=pd.DataFrame)
    timing_records: pd.DataFrame = field(default_factory=pd.DataFrame)
    matched_records: pd.DataFrame = field(default_factory=pd.DataFrame)

    # validation
    errors:   list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ── validation helpers ────────────────────────────────────────────────────────

def _check_columns(df: pd.DataFrame, required: set[str], label: str) -> list[str]:
    missing = required - set(df.columns)
    if missing:
        return [f"{label}: missing columns {sorted(missing)}"]
    return []


def _parse_amount(val: Any) -> Decimal | None:
    try:
        d = Decimal(str(val).strip())
        if d < 0:
            return None          # refunds carry positive amounts with entry_type=REFUND
        return d
    except Exception:
        return None


def _parse_date(val: Any) -> pd.Timestamp | None:
    try:
        return pd.Timestamp(str(val).strip())
    except Exception:
        return None


def _validate_platform(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str]]:
    errors, warnings = [], []
    errors += _check_columns(df, REQUIRED_PLATFORM_COLS, "Platform")
    if errors:
        return df, errors, warnings

    df = df.copy()
    df["transaction_id"] = df["transaction_id"].astype(str).str.strip().str.upper()
    df["currency"]       = df["currency"].astype(str).str.strip().str.upper()
    df["transaction_type"] = df["transaction_type"].astype(str).str.strip().str.upper()
    df["status"]         = df["status"].astype(str).str.strip().str.upper()
    df["original_transaction_id"] = df["original_transaction_id"].astype(str).str.strip().str.upper()

    # parse amounts
    df["_amount_dec"] = df["amount"].apply(_parse_amount)
    bad_amt = df["_amount_dec"].isna()
    if bad_amt.any():
        errors.append(f"Platform: {bad_amt.sum()} rows with invalid amount values.")

    # parse dates
    df["_txn_date"] = df["transaction_date"].apply(_parse_date)
    bad_dt = df["_txn_date"].isna()
    if bad_dt.any():
        errors.append(f"Platform: {bad_dt.sum()} rows with invalid transaction_date.")

    if df["transaction_id"].duplicated().any():
        warnings.append("Platform: duplicate transaction_ids detected — will be handled by engine.")

    return df, errors, warnings


def _validate_bank(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str]]:
    errors, warnings = [], []
    errors += _check_columns(df, REQUIRED_BANK_COLS, "Bank")
    if errors:
        return df, errors, warnings

    df = df.copy()
    df["transaction_id"]       = df["transaction_id"].astype(str).str.strip().str.upper()
    df["settlement_id"]        = df["settlement_id"].astype(str).str.strip().str.upper()
    df["currency"]             = df["currency"].astype(str).str.strip().str.upper()
    df["entry_type"]           = df["entry_type"].astype(str).str.strip().str.upper()
    df["settlement_reference"] = df["settlement_reference"].astype(str).str.strip().str.upper()

    df["_amount_dec"] = df["amount"].apply(_parse_amount)
    bad_amt = df["_amount_dec"].isna()
    if bad_amt.any():
        errors.append(f"Bank: {bad_amt.sum()} rows with invalid amount values.")

    df["_settle_date"] = df["settlement_date"].apply(_parse_date)
    bad_dt = df["_settle_date"].isna()
    if bad_dt.any():
        errors.append(f"Bank: {bad_dt.sum()} rows with invalid settlement_date.")

    return df, errors, warnings


# ── duplicate detection ───────────────────────────────────────────────────────

def _detect_bank_duplicates(
    bank_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    A bank row is a duplicate when transaction_id + amount + settlement_date + entry_type
    all match a row already seen.  First occurrence is kept; subsequent ones are flagged.
    Returns (clean_df, duplicate_df).
    """
    dup_key = ["transaction_id", "_amount_dec", "settlement_date", "entry_type"]
    is_dup  = bank_df.duplicated(subset=dup_key, keep="first")
    return bank_df[~is_dup].copy(), bank_df[is_dup].copy()


def _detect_platform_duplicates(
    plat_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    dup_key = ["transaction_id"]
    is_dup  = plat_df.duplicated(subset=dup_key, keep="first")
    return plat_df[~is_dup].copy(), plat_df[is_dup].copy()


# ── core matching ─────────────────────────────────────────────────────────────

def _reporting_month_end(year: int, month: int) -> pd.Timestamp:
    if month == 12:
        return pd.Timestamp(year + 1, 1, 1) - pd.Timedelta(days=1)
    return pd.Timestamp(year, month + 1, 1) - pd.Timedelta(days=1)


def _classify_row(
    plat_row: pd.Series,
    bank_row: pd.Series | None,
    reporting_end: pd.Timestamp,
    individual_tol: Decimal,
) -> dict[str, Any]:
    """
    Classify a single platform transaction against zero or one bank settlement row.
    Returns a dict with category, explanation, and financial fields.
    """
    txn_id    = plat_row["transaction_id"]
    plat_amt  = plat_row["_amount_dec"]
    plat_date = plat_row["_txn_date"]

    base: dict[str, Any] = {
        "transaction_id":          txn_id,
        "platform_date":           plat_date.date() if pd.notna(plat_date) else None,
        "platform_amount":         plat_amt,
        "bank_amount":             None,
        "settlement_date":         None,
        "settlement_id":           None,
        "difference":              None,
        "category":                None,
        "explanation":             "",
        "customer_id":             plat_row.get("customer_id", ""),
        "transaction_type":        plat_row.get("transaction_type", ""),
        "status":                  plat_row.get("status", ""),
        "original_transaction_id": plat_row.get("original_transaction_id", ""),
    }

    if bank_row is None:
        # No bank entry at all — could be missing or pending
        base["category"]    = Cat.MISSING_SETTLEMENT
        base["explanation"] = (
            f"Transaction {txn_id} (₹{plat_amt:,.2f}) has no corresponding bank "
            "settlement entry in the reporting period."
        )
        return base

    bank_amt    = bank_row["_amount_dec"]
    settle_date = bank_row["_settle_date"]
    settle_id   = bank_row["settlement_id"]
    diff        = (plat_amt - bank_amt).copy_abs()

    base["bank_amount"]    = bank_amt
    base["settlement_date"] = settle_date.date() if pd.notna(settle_date) else None
    base["settlement_id"]  = settle_id
    base["difference"]     = plat_amt - bank_amt

    # 1. Timing difference — settled after reporting month end
    if pd.notna(settle_date) and settle_date > reporting_end:
        base["category"] = Cat.TIMING_DIFFERENCE
        base["explanation"] = (
            f"Transaction {txn_id} was recorded on "
            f"{plat_date.date()} but the bank settled it on "
            f"{settle_date.date()}, which is after the reporting month end "
            f"({reporting_end.date()}). This is a settlement timing difference, "
            "not a permanently missing payment."
        )
        return base

    # 2. Perfect match
    if diff == Decimal("0"):
        base["category"]    = Cat.MATCHED
        base["explanation"] = f"Transaction {txn_id} matched exactly (₹{plat_amt:,.2f})."
        return base

    # 3. Within individual rounding tolerance
    if diff <= individual_tol:
        base["category"]    = Cat.ROUNDING_DIFFERENCE
        base["explanation"] = (
            f"Transaction {txn_id}: platform ₹{plat_amt:,.2f}, bank ₹{bank_amt:,.2f}. "
            f"Difference ₹{diff} is within the ₹{individual_tol} individual tolerance. "
            "Recorded as a rounding difference — contributes to cumulative residual."
        )
        return base

    # 4. Significant amount mismatch
    base["category"] = Cat.AMOUNT_MISMATCH
    base["explanation"] = (
        f"Transaction {txn_id}: platform ₹{plat_amt:,.2f} vs bank ₹{bank_amt:,.2f}. "
        f"Difference ₹{plat_amt - bank_amt:,.2f} exceeds tolerance."
    )
    return base


# ── main reconciliation function ──────────────────────────────────────────────

def reconcile(
    platform_df: pd.DataFrame,
    bank_df: pd.DataFrame,
    reporting_year: int  = REPORTING_MONTH_YEAR[0],
    reporting_month: int = REPORTING_MONTH_YEAR[1],
    individual_tolerance: Decimal = INDIVIDUAL_TOLERANCE,
) -> ReconciliationResult:
    """
    Run full reconciliation of platform transactions against bank settlements.

    Parameters
    ----------
    platform_df         : Raw platform transactions DataFrame.
    bank_df             : Raw bank settlements DataFrame.
    reporting_year      : Year of the reporting month.
    reporting_month     : Month number of the reporting month.
    individual_tolerance: Per-transaction rounding tolerance in INR.

    Returns
    -------
    ReconciliationResult with all classification data and summary metrics.
    """
    result  = ReconciliationResult()
    errors:   list[str] = []
    warnings: list[str] = []

    # ── 0. empty dataset guards ───────────────────────────────────────────────
    if platform_df is None or platform_df.empty:
        errors.append("Platform dataset is empty or not provided.")
    if bank_df is None or bank_df.empty:
        errors.append("Bank dataset is empty or not provided.")
    if errors:
        result.errors = errors
        return result

    # ── 1. validate & normalise ───────────────────────────────────────────────
    plat_df, p_errs, p_warns = _validate_platform(platform_df)
    bank_df, b_errs, b_warns = _validate_bank(bank_df)
    errors   += p_errs + b_errs
    warnings += p_warns + b_warns

    if errors:
        result.errors   = errors
        result.warnings = warnings
        return result

    # Drop rows with unparseable amounts/dates (they became invalid records)
    invalid_plat = plat_df["_amount_dec"].isna() | plat_df["_txn_date"].isna()
    invalid_bank = bank_df["_amount_dec"].isna() | bank_df["_settle_date"].isna()
    result.invalid_record_count = int(invalid_plat.sum() + invalid_bank.sum())

    plat_df = plat_df[~invalid_plat].copy()
    bank_df = bank_df[~invalid_bank].copy()

    reporting_end = _reporting_month_end(reporting_year, reporting_month)

    # ── 2. duplicate detection (before any financial totals) ──────────────────
    bank_clean, bank_dups   = _detect_bank_duplicates(bank_df)
    plat_clean, plat_dups   = _detect_platform_duplicates(plat_df)

    dup_records = []

    for _, row in bank_dups.iterrows():
        dup_records.append({
            "source":         "BANK",
            "settlement_id":  row["settlement_id"],
            "transaction_id": row["transaction_id"],
            "amount":         row["_amount_dec"],
            "date":           row["_settle_date"].date() if pd.notna(row["_settle_date"]) else None,
            "category":       Cat.DUPLICATE_SETTLEMENT,
            "explanation": (
                f"Bank settlement {row['settlement_id']} for transaction "
                f"{row['transaction_id']} (₹{row['_amount_dec']:,.2f}) is a "
                "duplicate entry. It has been excluded from reconciliation totals."
            ),
        })

    for _, row in plat_dups.iterrows():
        dup_records.append({
            "source":         "PLATFORM",
            "settlement_id":  "",
            "transaction_id": row["transaction_id"],
            "amount":         row["_amount_dec"],
            "date":           row["_txn_date"].date() if pd.notna(row["_txn_date"]) else None,
            "category":       Cat.DUPLICATE_TRANSACTION,
            "explanation": (
                f"Platform transaction {row['transaction_id']} appears more than once. "
                "Subsequent occurrences excluded from reconciliation."
            ),
        })

    result.duplicates   = pd.DataFrame(dup_records)
    result.duplicate_count = len(dup_records)

    # ── 3. compute financial totals from clean (de-duplicated) data ───────────
    result.total_platform_txns  = len(plat_clean)
    result.total_bank_entries   = len(bank_clean)

    result.total_platform_amount = plat_clean["_amount_dec"].apply(Decimal).sum()
    result.total_bank_amount     = bank_clean["_amount_dec"].apply(Decimal).sum()

    # ── 4. build bank lookup by transaction_id (keep first after de-dup) ──────
    # For each transaction_id in bank_clean, we store the row.
    # Orphan refunds will be identified after platform matching.
    bank_by_txn: dict[str, pd.Series] = {}
    bank_unmatched_ids: set[str] = set(bank_clean["transaction_id"].unique())

    for _, row in bank_clean.iterrows():
        tid = row["transaction_id"]
        if tid not in bank_by_txn:
            bank_by_txn[tid] = row

    # ── 5. match platform → bank ──────────────────────────────────────────────
    all_records:    list[dict] = []
    timing_records: list[dict] = []
    matched_records: list[dict] = []
    rounding_diff_total = Decimal("0")

    for _, plat_row in plat_clean.iterrows():
        txn_id   = plat_row["transaction_id"]
        bank_row = bank_by_txn.get(txn_id, None)

        classified = _classify_row(
            plat_row, bank_row, reporting_end, individual_tolerance
        )

        if bank_row is not None:
            bank_unmatched_ids.discard(txn_id)

        all_records.append(classified)

        cat = classified["category"]
        if cat == Cat.MATCHED:
            result.matched_count += 1
            matched_records.append(classified)
        elif cat == Cat.TIMING_DIFFERENCE:
            result.timing_difference_count += 1
            timing_records.append(classified)
        elif cat == Cat.MISSING_SETTLEMENT:
            result.missing_settlement_count += 1
        elif cat == Cat.ROUNDING_DIFFERENCE:
            result.rounding_difference_count += 1
            diff_val = classified["difference"]
            if diff_val is not None:
                rounding_diff_total += diff_val
        elif cat == Cat.AMOUNT_MISMATCH:
            result.amount_mismatch_count += 1

    # ── 6. detect orphan refunds & unmatched bank entries ────────────────────
    for tid in bank_unmatched_ids:
        bank_row = bank_by_txn[tid]
        entry_type = bank_row["entry_type"]
        bank_amt   = bank_row["_amount_dec"]
        settle_dt  = bank_row["_settle_date"]

        if entry_type == "REFUND":
            cat = Cat.ORPHAN_REFUND
            explanation = (
                f"Bank entry for {tid} is a REFUND (₹{bank_amt:,.2f}) with no "
                "corresponding platform transaction. This is an orphan refund — "
                "the original payment does not exist in the platform records."
            )
            result.orphan_refund_count += 1
        else:
            cat = Cat.UNMATCHED_BANK_ENTRY
            explanation = (
                f"Bank settlement for {tid} (₹{bank_amt:,.2f}) has no "
                "corresponding platform transaction."
            )
            result.unmatched_bank_count += 1

        all_records.append({
            "transaction_id":          tid,
            "platform_date":           None,
            "platform_amount":         None,
            "bank_amount":             bank_amt,
            "settlement_date":         settle_dt.date() if pd.notna(settle_dt) else None,
            "settlement_id":           bank_row["settlement_id"],
            "difference":              -bank_amt,
            "category":                cat,
            "explanation":             explanation,
            "customer_id":             "",
            "transaction_type":        entry_type,
            "status":                  "",
            "original_transaction_id": "",
        })

    # ── 7. aggregate rounding ─────────────────────────────────────────────────
    result.cumulative_rounding_diff = rounding_diff_total

    # ── 8. build result DataFrames ────────────────────────────────────────────
    all_df = pd.DataFrame(all_records)

    # format Decimal columns for display
    for col in ["platform_amount", "bank_amount", "difference"]:
        if col in all_df.columns:
            all_df[col] = all_df[col].apply(
                lambda x: float(x) if isinstance(x, Decimal) else x
            )

    result.all_records = all_df

    discrepancy_cats = {
        Cat.TIMING_DIFFERENCE, Cat.MISSING_SETTLEMENT, Cat.AMOUNT_MISMATCH,
        Cat.ROUNDING_DIFFERENCE, Cat.ORPHAN_REFUND, Cat.UNMATCHED_BANK_ENTRY,
        Cat.INVALID_RECORD,
    }
    result.discrepancies  = all_df[all_df["category"].isin(discrepancy_cats)].copy()
    result.timing_records = pd.DataFrame(timing_records)
    result.matched_records = pd.DataFrame(matched_records)

    # fix Decimal columns in duplicates df too
    if not result.duplicates.empty:
        result.duplicates["amount"] = result.duplicates["amount"].apply(
            lambda x: float(x) if isinstance(x, Decimal) else x
        )

    # ── 9. summary ────────────────────────────────────────────────────────────
    total_matched_incl_timing = result.matched_count + result.timing_difference_count
    if result.total_platform_txns > 0:
        result.reconciliation_rate = round(
            total_matched_incl_timing / result.total_platform_txns * 100, 2
        )

    result.unreconciled_amount = abs(
        result.total_platform_amount - result.total_bank_amount
    )

    result.errors   = errors
    result.warnings = warnings
    return result