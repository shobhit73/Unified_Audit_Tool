"""ADP Consolidated Audit.

Runs the three existing ADP standalone audits — Census, Direct Deposit (Payment),
and Emergency Contact — in a single pass and produces one chief workbook.

Logic comes entirely from the standalone tools via their compute_audit_dataframes()
entry points. This module never re-derives audit logic — it only stitches sheets.

UI takes 6 file uploads (one Uzio + one ADP file per audit) because each standalone
ADP audit is tuned for a specific export shape (Census Template vs Direct Deposit
export vs Emergency Contact export). See the discussion in CLAUDE.md / chat history
about why a single ADP master is not viable here.
"""

import importlib
import io
from datetime import datetime

import pandas as pd
import streamlit as st

APP_TITLE = "ADP - Consolidated Audit"


def _safe_compute(module_path: str, func_name: str, *args):
    """Reload the standalone module and call its compute entry point.

    Returns (dict_of_dfs, error_msg). On success error_msg is None; on failure the
    dict is empty and error_msg holds the exception text so the consolidator can
    show a per-audit error without aborting the whole run.
    """
    try:
        mod = importlib.import_module(module_path)
        importlib.reload(mod)
        fn = getattr(mod, func_name)
        return fn(*args), None
    except Exception as exc:
        return {}, f"{type(exc).__name__}: {exc}"


def _count(df: pd.DataFrame, column: str, predicate) -> int:
    if df is None or df.empty or column not in df.columns:
        return 0
    return int(df[column].apply(predicate).sum())


def _build_summary(census_dfs, payment_dfs, emergency_dfs,
                   census_err, payment_err, emergency_err) -> pd.DataFrame:
    rows = []

    rows.append({"Section": "Run Status", "Metric": "Census Audit",
                 "Value": "OK" if census_err is None else f"FAILED: {census_err}"})
    rows.append({"Section": "Run Status", "Metric": "Direct Deposit (Payment) Audit",
                 "Value": "OK" if payment_err is None else f"FAILED: {payment_err}"})
    rows.append({"Section": "Run Status", "Metric": "Emergency Contact Audit",
                 "Value": "OK" if emergency_err is None else f"FAILED: {emergency_err}"})

    # ---- Census ----
    if census_err is None and census_dfs:
        census_summary = census_dfs.get("Summary")
        if census_summary is not None and not census_summary.empty:
            for _, r in census_summary.iterrows():
                rows.append({"Section": "Census", "Metric": str(r["Metric"]),
                             "Value": r["Value"]})

    # ---- Payment ----
    if payment_err is None and payment_dfs:
        df_cmp = payment_dfs.get("Comparison_Detail", pd.DataFrame())
        df_exc = payment_dfs.get("Exception_Mixed_Mode", pd.DataFrame())
        rows.append({"Section": "Direct Deposit", "Metric": "Comparison rows",
                     "Value": int(len(df_cmp))})
        rows.append({"Section": "Direct Deposit", "Metric": "Data Mismatches",
                     "Value": _count(df_cmp, "Status",
                                     lambda v: "mismatch" in str(v).lower())})
        rows.append({"Section": "Direct Deposit", "Metric": "Mixed-Mode Exception rows",
                     "Value": int(len(df_exc))})
        rows.append({"Section": "Direct Deposit", "Metric": "Mixed-Mode (Corrected Setup)",
                     "Value": _count(df_exc, "Status",
                                     lambda v: "corrected setup" in str(v).lower())})
        rows.append({"Section": "Direct Deposit", "Metric": "Mixed-Mode Mismatches",
                     "Value": _count(df_exc, "Status",
                                     lambda v: "mismatch (mixed mode)" in str(v).lower())})

    # ---- Emergency ----
    if emergency_err is None and emergency_dfs:
        df_em = emergency_dfs.get("Emergency_Contact_Audit", pd.DataFrame())
        rows.append({"Section": "Emergency Contact", "Metric": "Comparison rows",
                     "Value": int(len(df_em))})
        rows.append({"Section": "Emergency Contact", "Metric": "Data Mismatches",
                     "Value": _count(df_em, "Status",
                                     lambda v: str(v).strip() == "Data Mismatch")})
        rows.append({"Section": "Emergency Contact", "Metric": "Missing in Uzio",
                     "Value": _count(df_em, "Status",
                                     lambda v: "missing in uzio" in str(v).lower())})
        rows.append({"Section": "Emergency Contact", "Metric": "Missing in ADP",
                     "Value": _count(df_em, "Status",
                                     lambda v: "missing in adp" in str(v).lower())})

    return pd.DataFrame(rows, columns=["Section", "Metric", "Value"])


def _write_workbook(summary_df: pd.DataFrame, census_dfs, payment_dfs,
                    emergency_dfs) -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        summary_df.to_excel(writer, sheet_name="Chief_Summary", index=False)

        # Census sheets (prefix CEN_ to avoid sheet-name collisions with the other
        # audits — Payment also has a "Summary" sheet in its standalone output).
        for name, df in (census_dfs or {}).items():
            if df is None or df.empty:
                continue
            sheet = f"CEN_{name}"[:31]
            df.to_excel(writer, sheet_name=sheet, index=False)

        # Payment sheets (with conditional formatting on the mixed-mode tab —
        # mirrors the standalone payment_audit's behavior so the user sees the
        # same green/red highlighting they expect).
        df_cmp = (payment_dfs or {}).get("Comparison_Detail", pd.DataFrame())
        df_exc = (payment_dfs or {}).get("Exception_Mixed_Mode", pd.DataFrame())
        if not df_cmp.empty:
            df_cmp.to_excel(writer, sheet_name="DD_Comparison_Detail", index=False)
        if not df_exc.empty:
            df_exc.to_excel(writer, sheet_name="DD_Exception_Mixed_Mode", index=False)
            workbook = writer.book
            exc_sheet = writer.sheets["DD_Exception_Mixed_Mode"]
            green_fmt = workbook.add_format({"bg_color": "#C6EFCE", "font_color": "#006100"})
            red_fmt = workbook.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"})
            last_row = max(len(df_exc), 1) + 1
            exc_sheet.conditional_format(f"G2:G{last_row}", {
                "type": "text", "criteria": "containing",
                "value": "Corrected Setup", "format": green_fmt,
            })
            exc_sheet.conditional_format(f"G2:G{last_row}", {
                "type": "text", "criteria": "containing",
                "value": "Mismatch (Mixed Mode)", "format": red_fmt,
            })

        # Emergency sheet
        df_em = (emergency_dfs or {}).get("Emergency_Contact_Audit", pd.DataFrame())
        if not df_em.empty:
            df_em.to_excel(writer, sheet_name="EC_Emergency_Contact_Audit", index=False)

    return out.getvalue()


def render_ui():
    st.title(APP_TITLE)
    st.caption(
        "Runs the ADP Census, Direct Deposit, and Emergency Contact audits in a "
        "single pass. Output is one chief workbook with one tab per source audit."
    )

    client_name = st.text_input("Client Name", value="Client", key="adp_cons_client")

    st.markdown("### 1. Census Audit Files")
    c1, c2 = st.columns(2)
    with c1:
        cen_uzio = st.file_uploader("Uzio Census Template (.xlsx/.xlsm/.csv)",
                                    type=["xlsx", "xlsm", "csv"], key="adp_cons_cen_u")
    with c2:
        cen_adp = st.file_uploader("ADP Census Export (.xlsx/.csv)",
                                   type=["xlsx", "csv"], key="adp_cons_cen_a")

    st.markdown("### 2. Direct Deposit (Payment) Files")
    p1, p2 = st.columns(2)
    with p1:
        pay_uzio = st.file_uploader("Uzio Direct Deposit Export (.xlsx/.csv)",
                                    type=["xlsx", "csv"], key="adp_cons_pay_u")
    with p2:
        pay_adp = st.file_uploader("ADP Direct Deposit Export (.xlsx/.csv)",
                                   type=["xlsx", "csv"], key="adp_cons_pay_a")

    st.markdown("### 3. Emergency Contact Files")
    e1, e2 = st.columns(2)
    with e1:
        em_uzio = st.file_uploader("Uzio Emergency Contact Export (.xlsx)",
                                   type=["xlsx"], key="adp_cons_em_u")
    with e2:
        em_adp = st.file_uploader("ADP Emergency Contact Export (.xlsx)",
                                  type=["xlsx"], key="adp_cons_em_a")

    if st.button("Run Consolidated Audit", type="primary"):
        missing = []
        if not (cen_uzio and cen_adp): missing.append("Census")
        if not (pay_uzio and pay_adp): missing.append("Direct Deposit")
        if not (em_uzio and em_adp):   missing.append("Emergency Contact")
        if missing:
            st.error(
                "Please upload both files for: " + ", ".join(missing) +
                ". All three pairs are required."
            )
            return

        with st.spinner("Running Census audit..."):
            census_dfs, census_err = _safe_compute(
                "apps.adp.census_audit", "compute_audit_dataframes",
                cen_uzio, cen_adp,
            )
        with st.spinner("Running Direct Deposit (Payment) audit..."):
            payment_dfs, payment_err = _safe_compute(
                "apps.adp.payment_audit", "compute_audit_dataframes",
                pay_uzio, pay_adp,
            )
        with st.spinner("Running Emergency Contact audit..."):
            emergency_dfs, emergency_err = _safe_compute(
                "apps.adp.emergency_audit", "compute_audit_dataframes",
                em_uzio, em_adp,
            )

        for label, err in (("Census", census_err),
                           ("Direct Deposit", payment_err),
                           ("Emergency Contact", emergency_err)):
            if err:
                st.error(f"{label} audit failed: {err}")

        summary_df = _build_summary(
            census_dfs, payment_dfs, emergency_dfs,
            census_err, payment_err, emergency_err,
        )

        st.markdown("### Chief Summary")
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

        report_bytes = _write_workbook(summary_df, census_dfs, payment_dfs,
                                       emergency_dfs)
        ts = datetime.now().strftime("%d_%m_%Y_%H%M")
        safe_client = "".join(ch for ch in client_name
                              if ch.isalnum() or ch in ("_", "-")) or "Client"
        st.download_button(
            label="Download Chief Consolidated Audit Report",
            data=report_bytes,
            file_name=f"ADP_Chief_Consolidated_Audit_Report_{safe_client}_{ts}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
