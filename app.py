"""
ReconIQ — Payment Reconciliation Intelligence
Streamlit frontend dashboard.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

import pandas as pd
import streamlit as st

from reconciliation import reconcile, ReconciliationResult, Cat
from sample_data import get_sample_data, PLANTED_SCENARIOS

st.set_page_config(
    page_title="ReconIQ — Payment Reconciliation Intelligence",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
html, body, [class*="css"] {
    font-family: 'Inter', 'Segoe UI', sans-serif;
    background-color: #F7F9FC;
    color: #0D1F3C;
}

.kpi-card {
    background: #FFFFFF;
    border-radius: 10px;
    padding: 18px 22px;
    box-shadow: 0 1px 4px rgba(13,31,60,0.08);
    border-left: 4px solid #1565C0;
    margin-bottom: 8px;
}
.kpi-label {
    font-size: 11px;
    font-weight: 700;
    color: #546E7A;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    margin-bottom: 6px;
}
.kpi-value {
    font-size: 24px;
    font-weight: 700;
    color: #0D1F3C;
    line-height: 1.1;
}
.kpi-sub {
    font-size: 11px;
    color: #90A4AE;
    margin-top: 4px;
}

.section-header {
    font-size: 15px;
    font-weight: 700;
    color: #0D1F3C;
    border-bottom: 2px solid #1565C0;
    padding-bottom: 5px;
    margin-bottom: 14px;
    margin-top: 28px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.disc-box {
    background: #FFFFFF;
    border-radius: 8px;
    padding: 14px 18px;
    margin-bottom: 10px;
    box-shadow: 0 1px 3px rgba(13,31,60,0.07);
}
.disc-title {
    font-size: 13px;
    font-weight: 700;
    color: #0D1F3C;
    margin-bottom: 4px;
}
.disc-body {
    font-size: 12px;
    color: #546E7A;
    line-height: 1.6;
}
.disc-meta {
    font-size: 11px;
    color: #90A4AE;
    margin-top: 6px;
    font-family: monospace;
}

.rounding-callout {
    background: #FFF8E1;
    border-left: 4px solid #F9A825;
    border-radius: 6px;
    padding: 12px 18px;
    margin-top: 10px;
    font-size: 13px;
    color: #4E342E;
}

section[data-testid="stSidebar"] {
    background: #0D1F3C;
}
section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stRadio label,
section[data-testid="stSidebar"] .stSelectbox label {
    color: #ECEFF1 !important;
}

.footer {
    text-align: center;
    color: #90A4AE;
    font-size: 12px;
    margin-top: 40px;
    padding-top: 16px;
    border-top: 1px solid #E0E0E0;
}
</style>
""", unsafe_allow_html=True)


# ── helpers ───────────────────────────────────────────────────────────────────

def fmt_inr(val) -> str:
    if val is None:
        return "—"
    try:
        return f"₹{float(val):,.2f}"
    except Exception:
        return "—"


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def kpi_card(label: str, value: str, sub: str = "", accent: str = "#1565C0") -> str:
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return (
        f'<div class="kpi-card" style="border-left-color:{accent};">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'{sub_html}</div>'
    )


# ── sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar() -> tuple[pd.DataFrame | None, pd.DataFrame | None, int, int]:
    with st.sidebar:
        st.markdown("## ReconIQ")
        st.markdown("Payment Reconciliation Intelligence")
        st.markdown("---")

        st.markdown("**Reporting Period**")
        month_opts = {
            "October 2026":   (2026, 10),
            "November 2026":  (2026, 11),
            "September 2026": (2026, 9),
        }
        month_sel = st.selectbox("", list(month_opts.keys()), index=0,
                                 key="month_select")
        year, month = month_opts[month_sel]

        st.markdown("---")
        st.markdown("**Data Source**")
        data_source = st.radio(
            "",
            ["Sample Data", "Upload CSV Files"],
            index=0,
            key="data_source_radio",
        )

        platform_df, bank_df = None, None

        if data_source == "Sample Data":
            platform_df, bank_df = get_sample_data()
            st.success(
                f"Sample data loaded\n"
                f"{len(platform_df)} platform transactions\n"
                f"{len(bank_df)} bank entries"
            )
        else:
            plat_file = st.file_uploader("Platform Transactions CSV", type=["csv"],
                                         key="plat_upload")
            bank_file = st.file_uploader("Bank Settlements CSV", type=["csv"],
                                         key="bank_upload")

            if plat_file and bank_file:
                try:
                    platform_df = pd.read_csv(plat_file)
                    bank_df     = pd.read_csv(bank_file)
                    st.success("Files loaded successfully.")
                except Exception as exc:
                    st.error(f"Failed to read CSV: {exc}")
            elif plat_file or bank_file:
                st.warning("Upload both files to run reconciliation.")

        st.markdown("---")
        st.markdown(
            '<span style="font-size:11px;color:#607D8B;">'
            'Chirag Poojari<br>chirag.poojari@mitwpu.edu.in<br>'
            'Onelab Assessment · November 2026'
            '</span>',
            unsafe_allow_html=True,
        )

    return platform_df, bank_df, year, month


# ── header ────────────────────────────────────────────────────────────────────

def render_header(result: Optional[ReconciliationResult]) -> None:
    left, right = st.columns([4, 1])
    with left:
        st.markdown(
            "<h1 style='color:#0D1F3C;margin-bottom:2px;font-size:28px;'>ReconIQ</h1>"
            "<p style='color:#546E7A;font-size:14px;margin-top:0;'>"
            "Payment Reconciliation Intelligence</p>",
            unsafe_allow_html=True,
        )
    with right:
        if result:
            rate = result.reconciliation_rate
            color = "#2E7D32" if rate >= 90 else "#F57F17" if rate >= 70 else "#C62828"
            bg    = "#E8F5E9" if rate >= 90 else "#FFF8E1" if rate >= 70 else "#FFEBEE"
            st.markdown(
                f'<div style="text-align:right;padding-top:12px;">'
                f'<span style="background:{bg};color:{color};border-radius:20px;'
                f'padding:5px 16px;font-size:13px;font-weight:700;">'
                f'{rate:.1f}% Reconciled</span></div>',
                unsafe_allow_html=True,
            )


# ── KPIs ──────────────────────────────────────────────────────────────────────

def render_kpis(result: ReconciliationResult) -> None:
    st.markdown('<div class="section-header">Summary</div>', unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    c4, c5, c6 = st.columns(3)

    matched_total = result.matched_count + result.timing_difference_count

    with c1:
        st.markdown(kpi_card(
            "Platform Transactions",
            str(result.total_platform_txns),
            "De-duplicated",
        ), unsafe_allow_html=True)

    with c2:
        st.markdown(kpi_card(
            "Platform Amount",
            fmt_inr(float(result.total_platform_amount)),
        ), unsafe_allow_html=True)

    with c3:
        st.markdown(kpi_card(
            "Bank Settlements",
            str(result.total_bank_entries),
            "De-duplicated",
        ), unsafe_allow_html=True)

    with c4:
        st.markdown(kpi_card(
            "Bank Amount",
            fmt_inr(float(result.total_bank_amount)),
        ), unsafe_allow_html=True)

    with c5:
        st.markdown(kpi_card(
            "Matched",
            str(matched_total),
            f"{result.matched_count} exact  +  {result.timing_difference_count} timing",
            accent="#2E7D32",
        ), unsafe_allow_html=True)

    with c6:
        unr = float(result.unreconciled_amount)
        accent = "#C62828" if unr > 0 else "#2E7D32"
        st.markdown(kpi_card(
            "Unreconciled Amount",
            fmt_inr(unr),
            "Platform total vs Bank total",
            accent=accent,
        ), unsafe_allow_html=True)

    # Progress bar
    st.progress(result.reconciliation_rate / 100.0)


# ── discrepancy counts ────────────────────────────────────────────────────────

def render_discrepancy_counts(result: ReconciliationResult) -> None:
    st.markdown('<div class="section-header">Discrepancy Breakdown</div>',
                unsafe_allow_html=True)

    items = [
        ("Missing Settlements",    result.missing_settlement_count,    "#FFEBEE", "#C62828"),
        ("Timing Differences",     result.timing_difference_count,     "#FFF8E1", "#F57F17"),
        ("Duplicate Entries",      result.duplicate_count,             "#F3F4F6", "#455A64"),
        ("Orphan Refunds",         result.orphan_refund_count,         "#FFEBEE", "#C62828"),
        ("Amount Mismatches",      result.amount_mismatch_count,       "#FFEBEE", "#C62828"),
        ("Rounding Differences",   result.rounding_difference_count,   "#FFF8E1", "#F57F17"),
        ("Unmatched Bank Entries", result.unmatched_bank_count,        "#E3F2FD", "#1565C0"),
    ]

    cols = st.columns(4)
    for i, (label, count, bg, fg) in enumerate(items):
        with cols[i % 4]:
            st.markdown(
                f'<div style="background:{bg};border-radius:8px;padding:14px 16px;'
                f'margin-bottom:10px;">'
                f'<div style="font-size:11px;font-weight:700;color:#546E7A;'
                f'text-transform:uppercase;letter-spacing:.05em;">{label}</div>'
                f'<div style="font-size:26px;font-weight:700;color:{fg};margin-top:4px;">'
                f'{count}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    if result.cumulative_rounding_diff != Decimal("0"):
        cum = float(result.cumulative_rounding_diff)
        st.markdown(
            f'<div class="rounding-callout">'
            f'<strong>Cumulative Rounding Residual: {fmt_inr(cum)}</strong><br>'
            f'{result.rounding_difference_count} transactions each fall within the '
            f'₹0.01 individual tolerance, but their combined residual is {fmt_inr(cum)}. '
            f'This aggregate difference requires separate disclosure.'
            f'</div>',
            unsafe_allow_html=True,
        )


# ── planted scenario explainers ───────────────────────────────────────────────

def render_scenarios(result: ReconciliationResult) -> None:
    st.markdown('<div class="section-header">Discrepancy Details</div>',
                unsafe_allow_html=True)

    scenarios = [
        {
            "title":  "Next-Month Settlement",
            "accent": "#F57F17",
            "body":   PLANTED_SCENARIOS["next_month_settlement"]["description"],
            "meta": (
                f"Transaction: {PLANTED_SCENARIOS['next_month_settlement']['transaction_id']}  |  "
                f"Platform date: {PLANTED_SCENARIOS['next_month_settlement']['platform_date']}  |  "
                f"Bank date: {PLANTED_SCENARIOS['next_month_settlement']['bank_date']}  |  "
                f"Amount: ₹{PLANTED_SCENARIOS['next_month_settlement']['amount']}"
            ),
        },
        {
            "title":  "Rounding Differences",
            "accent": "#F57F17",
            "body":   PLANTED_SCENARIOS["rounding_differences"]["description"],
            "meta": (
                f"Individual diff: {PLANTED_SCENARIOS['rounding_differences']['individual_diff']}  |  "
                f"Cumulative: {PLANTED_SCENARIOS['rounding_differences']['cumulative_diff']}"
            ),
        },
        {
            "title":  "Duplicate Settlement",
            "accent": "#455A64",
            "body":   PLANTED_SCENARIOS["duplicate_settlement"]["description"],
            "meta": (
                f"Transaction: {PLANTED_SCENARIOS['duplicate_settlement']['transaction_id']}  |  "
                f"Amount: ₹{PLANTED_SCENARIOS['duplicate_settlement']['amount']}"
            ),
        },
        {
            "title":  "Orphan Refund",
            "accent": "#C62828",
            "body":   PLANTED_SCENARIOS["orphan_refund"]["description"],
            "meta": (
                f"Transaction: {PLANTED_SCENARIOS['orphan_refund']['transaction_id']}  |  "
                f"Amount: ₹{PLANTED_SCENARIOS['orphan_refund']['amount']}  |  "
                f"Bank date: {PLANTED_SCENARIOS['orphan_refund']['bank_date']}"
            ),
        },
    ]

    col1, col2 = st.columns(2)
    for i, s in enumerate(scenarios):
        with (col1 if i % 2 == 0 else col2):
            st.markdown(
                f'<div class="disc-box" style="border-left:4px solid {s["accent"]};">'
                f'<div class="disc-title">{s["title"]}</div>'
                f'<div class="disc-body">{s["body"]}</div>'
                f'<div class="disc-meta">{s["meta"]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ── transaction table ─────────────────────────────────────────────────────────

def render_transaction_table(result: ReconciliationResult) -> None:
    st.markdown('<div class="section-header">Transaction Investigation</div>',
                unsafe_allow_html=True)

    df = result.all_records.copy()
    if df.empty:
        st.info("No transaction records to display.")
        return

    # ── filters ───────────────────────────────────────────────────────────────
    fc1, fc2, fc3 = st.columns([2, 2, 3])

    all_cats = ["All"] + sorted(df["category"].dropna().unique().tolist())
    with fc1:
        selected_cat = st.selectbox("Category", all_cats, key="filter_cat")

    all_status = ["All"] + sorted(
        s for s in df["status"].dropna().unique().tolist() if s
    )
    with fc2:
        selected_status = st.selectbox("Status", all_status, key="filter_status")

    with fc3:
        search_id = st.text_input("Search by Transaction ID", value="",
                                  placeholder="e.g. TXN-NMS00001",
                                  key="filter_txn_id")

    if selected_cat != "All":
        df = df[df["category"] == selected_cat]
    if selected_status != "All":
        df = df[df["status"] == selected_status]
    if search_id.strip():
        df = df[df["transaction_id"].str.contains(
            search_id.strip().upper(), na=False
        )]

    # ── format ────────────────────────────────────────────────────────────────
    display = df[[
        "transaction_id", "platform_date", "settlement_date",
        "platform_amount", "bank_amount", "difference",
        "category", "explanation",
    ]].copy()

    display.columns = [
        "Transaction ID", "Platform Date", "Settlement Date",
        "Platform Amt (₹)", "Bank Amt (₹)", "Difference (₹)",
        "Category", "Explanation",
    ]

    for col in ["Platform Amt (₹)", "Bank Amt (₹)", "Difference (₹)"]:
        display[col] = display[col].apply(
            lambda x: f"{x:,.2f}" if isinstance(x, (int, float)) and pd.notna(x) else "—"
        )

    st.markdown(f"**{len(display)}** of **{len(result.all_records)}** records", unsafe_allow_html=False)

    st.dataframe(
        display,
        use_container_width=True,
        height=400,
        column_config={
            "Transaction ID": st.column_config.TextColumn(width="medium"),
            "Category":       st.column_config.TextColumn(width="medium"),
            "Explanation":    st.column_config.TextColumn(width="large"),
        },
    )


# ── duplicates ────────────────────────────────────────────────────────────────

def render_duplicates(result: ReconciliationResult) -> None:
    if result.duplicates.empty:
        return
    st.markdown('<div class="section-header">Duplicate Records</div>',
                unsafe_allow_html=True)
    st.markdown(
        "These entries were excluded from all financial totals to prevent double-counting."
    )
    display = result.duplicates.copy()
    if "amount" in display.columns:
        display["amount"] = display["amount"].apply(
            lambda x: f"{x:,.2f}" if isinstance(x, (int, float)) and pd.notna(x) else "—"
        )
    st.dataframe(display, use_container_width=True)


# ── downloads ─────────────────────────────────────────────────────────────────

def render_downloads(
    platform_df: pd.DataFrame,
    bank_df: pd.DataFrame,
    result: ReconciliationResult,
) -> None:
    st.markdown('<div class="section-header">Downloads</div>', unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.download_button(
            "⬇ Platform CSV",
            data=df_to_csv_bytes(platform_df),
            file_name="platform_transactions.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with c2:
        st.download_button(
            "⬇ Bank CSV",
            data=df_to_csv_bytes(bank_df),
            file_name="bank_settlements.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with c3:
        st.download_button(
            "⬇ Full Report CSV",
            data=df_to_csv_bytes(result.all_records),
            file_name="reconciliation_report.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with c4:
        st.download_button(
            "⬇ Discrepancies CSV",
            data=df_to_csv_bytes(result.discrepancies),
            file_name="discrepancies.csv",
            mime="text/csv",
            use_container_width=True,
        )


# ── validation messages ───────────────────────────────────────────────────────

def render_validation(result: ReconciliationResult) -> None:
    for e in result.errors:
        st.error(f"Error: {e}")
    for w in result.warnings:
        st.warning(f"Warning: {w}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    platform_df, bank_df, rep_year, rep_month = render_sidebar()

    if platform_df is None or bank_df is None:
        st.markdown(
            "<h1 style='color:#0D1F3C;font-size:28px;'>ReconIQ</h1>"
            "<p style='color:#546E7A;'>Payment Reconciliation Intelligence</p>",
            unsafe_allow_html=True,
        )
        st.info("Select Sample Data or upload both CSV files in the sidebar to begin.")
        return

    result = reconcile(platform_df, bank_df, rep_year, rep_month)

    render_header(result)

    if result.errors:
        render_validation(result)
        st.error("Reconciliation halted due to validation errors above.")
        return

    if result.warnings:
        render_validation(result)

    render_kpis(result)
    render_discrepancy_counts(result)
    render_scenarios(result)
    render_transaction_table(result)
    render_duplicates(result)
    render_downloads(platform_df, bank_df, result)

    st.markdown(
        '<div class="footer">'
        'ReconIQ &nbsp;·&nbsp; Chirag Poojari &nbsp;·&nbsp; '
        'chirag.poojari@mitwpu.edu.in &nbsp;·&nbsp; '
        'Onelab Assessment · November 2026'
        '</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()