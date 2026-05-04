"""Paycom - Prior Payroll Setup Helper Tool.

Replaces the deprecated 'Paycom - Deduction Analyzer'. Mirrors the ADP
'Prior Payroll Setup Helper' shape: three answers, one Excel output with
exactly three tabs.

Inputs (both Paycom files required):
  1. Paycom Prior Payroll Register (long format with Type Code / Type
     Description / Amount / Code Description columns).
  2. Paycom Scheduled Deductions Report (with Deduction Code / Deduction
     Desc / Tax Treatment columns).

Outputs:
  Tab 1  What to Set Up (Earnings | Contributions | Deductions, codes only)
  Tab 2  Pre-Tax vs Post-Tax (read straight from Tax Treatment column;
         no algorithm needed -- Paycom labels each deduction directly)
  Tab 3  Bonus Verdict (FLSA: Strategy A+C using Paycom's WOT vs plain
         OT differential when present, otherwise indeterminate)
"""

from __future__ import annotations
import io
import re

import pandas as pd
import streamlit as st


# ---------- Pure-Python analysis (mirrors core/paycom/prior_payroll_setup_helper.py) ----------

def _num(v):
    if v is None:
        return 0.0
    if isinstance(v, (int, float)) and not pd.isna(v):
        return float(v)
    s = str(v).strip().replace(",", "").replace("$", "")
    if s in ("", "-", "nan", "NaT", "None"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _read_either(file) -> pd.DataFrame:
    """Streamlit UploadedFile -> DataFrame."""
    file.seek(0)
    name = (file.name or "").lower()
    if name.endswith(".csv"):
        return pd.read_csv(file)
    return pd.read_excel(file)


CONTRIB_PATTERN = re.compile(r"\b(401[Kk]?|403[Bb]?|457|ROTH|HSA|FSA|RETIREMENT)\b")
BONUS_RE = re.compile(r"\b(BONUS|BNS|BND|BNH|BN[0-9]?|NA[0-9])\b", re.IGNORECASE)


def build_earnings_catalog(prior_df):
    if "Code Description" not in prior_df.columns:
        return []
    earn = prior_df[prior_df["Code Description"].astype(str).str.strip() == "Earnings"]
    rows, seen = [], set()
    for _, r in earn.iterrows():
        tc = str(r.get("Type Code", "")).strip()
        td = str(r.get("Type Description", "")).strip()
        key = (tc, td)
        if not tc or key in seen:
            continue
        seen.add(key)
        amt = earn[(earn["Type Code"] == tc) & (earn["Type Description"] == td)]["Amount"].apply(_num)
        rows.append({
            "Type Code": tc, "Type Description": td,
            "Total $": round(float(amt.sum()), 2),
            "Employees": int(len(amt[amt != 0])),
        })
    return rows


def build_taxes_discovered(prior_df):
    if "Code Description" not in prior_df.columns:
        return []
    tax = prior_df[prior_df["Code Description"].astype(str).str.strip() == "W/H Taxes"]
    rows, seen = [], set()
    for _, r in tax.iterrows():
        tc = str(r.get("Type Code", "")).strip()
        td = str(r.get("Type Description", "")).strip()
        key = (tc, td)
        if not tc or key in seen:
            continue
        seen.add(key)
        amt = tax[(tax["Type Code"] == tc) & (tax["Type Description"] == td)]["Amount"].apply(_num)
        rows.append({
            "Type Code": tc, "Type Description": td,
            "Total $": round(float(amt.sum()), 2),
            "Employees": int(len(amt[amt != 0])),
        })
    return rows


def split_contribs_deductions(scheduled_df):
    if "Deduction Code" not in scheduled_df.columns:
        return [], []
    rows, seen = [], set()
    for _, r in scheduled_df.iterrows():
        dc = str(r.get("Deduction Code", "")).strip()
        dd = str(r.get("Deduction Desc", "")).strip()
        key = (dc, dd)
        if not dc or key in seen:
            continue
        seen.add(key)
        rows.append({
            "Deduction Code": dc, "Deduction Desc": dd,
            "Setup Count": int(((scheduled_df["Deduction Code"] == dc)
                                & (scheduled_df["Deduction Desc"] == dd)).sum()),
        })
    contribs, deds = [], []
    for r in rows:
        u = (r["Deduction Code"] + " " + r["Deduction Desc"]).upper()
        (contribs if CONTRIB_PATTERN.search(u) else deds).append(r)
    return contribs, deds


def classify_pre_post_tax(scheduled_df):
    if "Deduction Code" not in scheduled_df.columns or "Tax Treatment" not in scheduled_df.columns:
        return []
    rows = []
    grouped = scheduled_df.groupby(["Deduction Code", "Deduction Desc"], dropna=False)
    for (dc, dd), grp in grouped:
        treatments = grp["Tax Treatment"].dropna().astype(str).str.strip().unique().tolist()
        if not treatments:
            verdict, flavor, why = "unknown", "", "Tax Treatment column was blank for every row of this deduction."
        else:
            primary = grp["Tax Treatment"].dropna().astype(str).str.strip().mode()
            tt = primary.iloc[0] if not primary.empty else treatments[0]
            tt_upper = tt.upper()
            if tt_upper.startswith("B"):
                verdict, flavor = "PRE-TAX", "Section 125"
                why = f"Tax Treatment '{tt}' = Section 125 cafeteria plan (reduces FIT, FICA, Medicare, and state-income taxable wages)."
            elif tt_upper.startswith("H"):
                verdict, flavor = "PRE-TAX", "401k traditional"
                why = f"Tax Treatment '{tt}' = traditional 401(k) (reduces FIT and SIT but NOT FICA/Medicare)."
            elif tt_upper.startswith("A"):
                verdict, flavor = "POST-TAX", ""
                why = f"Tax Treatment '{tt}' = post-tax deduction (does not reduce taxable wages)."
            else:
                verdict, flavor = "unknown", "review"
                why = f"Tax Treatment '{tt}' is not a recognized Paycom code -- please review manually."
            if len(treatments) > 1:
                why += f"  (Multiple distinct Tax Treatments seen: {treatments}; using the most common.)"
        rows.append({
            "Code": str(dc).strip(),
            "Description": str(dd).strip() if dd is not None else "",
            "Verdict": verdict, "Flavor": flavor, "Why": why,
        })
    return rows


def classify_bonus(prior_df):
    if "Code Description" not in prior_df.columns or "Type Code" not in prior_df.columns:
        return {"verdict": "indeterminate",
                "reason": "Prior Payroll Register is missing Code Description / Type Code columns.",
                "bonus_codes_found": [], "samples": []}
    earn = prior_df[prior_df["Code Description"].astype(str).str.strip() == "Earnings"]
    bonus_codes = sorted({
        str(r["Type Code"]).strip() for _, r in earn.iterrows()
        if BONUS_RE.search(f"{r.get('Type Code', '')} {r.get('Type Description', '')}".upper())
    })
    ot_codes = ["OT", "OVT", "OVR"]
    wot_codes = ["WOT"]
    has_ot = any(c in earn["Type Code"].astype(str).unique() for c in ot_codes)
    has_wot = any(c in earn["Type Code"].astype(str).unique() for c in wot_codes)

    if not bonus_codes:
        return {"verdict": "no_bonus_in_file",
                "reason": ("No bonus codes found in the Prior Payroll Register. "
                           "(Looked for Type Codes containing BONUS / BNS / BND / BNH / BN# / NA#.) "
                           "If a bonus exists outside this pay period, supply that file too."),
                "bonus_codes_found": [], "ot_present": has_ot, "wot_present": has_wot,
                "samples": []}

    if not (has_ot and has_wot):
        msg = []
        if has_wot and not has_ot:
            msg.append("File contains only Paycom's WOT (weighted overtime) lines; "
                       "the plain-OT comparison line is absent so the WOT-vs-OT differential "
                       "test cannot run.")
        elif has_ot and not has_wot:
            msg.append("File contains only plain-OT lines; the WOT (weighted overtime) "
                       "comparison is absent.")
        else:
            msg.append("File contains neither OT nor WOT lines.")
        msg.append("To classify the bonus, supply a Paycom Payroll Register Detail report "
                   "with hours, OR confirm the bonus type with the implementer directly.")
        return {"verdict": "indeterminate", "reason": " ".join(msg),
                "bonus_codes_found": bonus_codes, "ot_present": has_ot,
                "wot_present": has_wot, "samples": []}

    pivot = earn.pivot_table(
        index="EE Code", columns="Type Code", values="Amount",
        aggfunc=lambda s: float(sum(_num(v) for v in s)), fill_value=0.0,
    )
    samples = []
    differential_rows = matching_rows = 0
    rate_tol_pct = 0.005
    for eid, row in pivot.iterrows():
        ot_amt = sum(_num(row[c]) for c in ot_codes if c in row.index)
        wot_amt = sum(_num(row[c]) for c in wot_codes if c in row.index)
        bonus_amt = sum(_num(row[c]) for c in bonus_codes if c in row.index)
        if ot_amt <= 0 or wot_amt <= 0 or bonus_amt <= 0:
            continue
        diff_pct = (wot_amt - ot_amt) / ot_amt if ot_amt > 0 else 0.0
        if diff_pct > rate_tol_pct:
            differential_rows += 1
        else:
            matching_rows += 1
        if len(samples) < 5:
            samples.append({
                "employee": str(eid),
                "plain_ot_amount": round(ot_amt, 2),
                "weighted_ot_amount": round(wot_amt, 2),
                "differential_pct": round(diff_pct * 100, 3),
                "bonus_amount": round(bonus_amt, 2),
                "row_verdict": "non_discretionary" if diff_pct > rate_tol_pct else "discretionary",
            })
    rows_tested = differential_rows + matching_rows
    if rows_tested == 0:
        return {"verdict": "indeterminate",
                "reason": ("Bonus codes were found but no employee in this pay period had both "
                           "OT, WOT, and a bonus amount in the same row."),
                "bonus_codes_found": bonus_codes, "samples": []}
    if differential_rows > 0:
        return {"verdict": "non_discretionary",
                "reason": (f"{differential_rows} of {rows_tested} employees show Paycom's WOT "
                           f"materially higher than plain OT. Paycom rolls non-discretionary "
                           f"bonuses into the regular rate before computing weighted OT, so the "
                           f"gap means the bonus is non-discretionary under FLSA."),
                "bonus_codes_found": bonus_codes,
                "rows_tested": rows_tested, "differential_rows": differential_rows,
                "matching_rows": matching_rows, "samples": samples}
    return {"verdict": "discretionary",
            "reason": (f"All {rows_tested} tested employees show WOT == plain OT (no weighted "
                       f"adjustment). Paycom did NOT roll the bonus into the regular rate, so "
                       f"the bonus is discretionary."),
            "bonus_codes_found": bonus_codes,
            "rows_tested": rows_tested, "differential_rows": 0,
            "matching_rows": matching_rows, "samples": samples}


def _pick_bonus_example(bonus_info):
    samples = bonus_info.get("samples", [])
    if not samples:
        return None
    if bonus_info["verdict"] == "non_discretionary":
        cands = [s for s in samples if s["row_verdict"] == "non_discretionary"]
        return max(cands, key=lambda s: s["differential_pct"]) if cands else samples[0]
    if bonus_info["verdict"] == "discretionary":
        cands = [s for s in samples if s["row_verdict"] == "discretionary"]
        return min(cands, key=lambda s: abs(s["differential_pct"])) if cands else samples[0]
    return samples[0]


def build_simplified_xlsx_bytes(results):
    """Three-tab xlsx output matching the ADP setup helper format."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        wb = writer.book
        header_fmt = wb.add_format({"bold": True, "bg_color": "#1F4E78",
                                    "font_color": "white", "border": 1,
                                    "align": "left", "valign": "vcenter"})
        wrap_fmt = wb.add_format({"valign": "top", "text_wrap": True})
        v_pre = wb.add_format({"bold": True, "bg_color": "#C6EFCE",
                               "font_color": "#006100", "align": "center", "valign": "vcenter"})
        v_post = wb.add_format({"bold": True, "bg_color": "#FFC7CE",
                                "font_color": "#9C0006", "align": "center", "valign": "vcenter"})
        v_nondisc = wb.add_format({"bold": True, "bg_color": "#FFC7CE",
                                   "font_color": "#9C0006", "align": "left",
                                   "valign": "vcenter", "font_size": 14})
        v_disc = wb.add_format({"bold": True, "bg_color": "#C6EFCE",
                                "font_color": "#006100", "align": "left",
                                "valign": "vcenter", "font_size": 14})

        # Tab 1
        earn = [r["Type Code"] + " - " + r["Type Description"] for r in results["Earnings_Codes"]]
        contrib = [r["Deduction Code"] + " - " + r["Deduction Desc"] for r in results["Contributions"]]
        ded = [r["Deduction Code"] + " - " + r["Deduction Desc"] for r in results["Deductions"]]
        max_n = max(len(earn), len(contrib), len(ded), 1)
        df1 = pd.DataFrame([{
            "Earnings": earn[i] if i < len(earn) else "",
            "Contributions": contrib[i] if i < len(contrib) else "",
            "Deductions": ded[i] if i < len(ded) else "",
        } for i in range(max_n)])
        df1.to_excel(writer, sheet_name="1. What to Set Up", index=False)
        ws1 = writer.sheets["1. What to Set Up"]
        ws1.set_column("A:A", 38); ws1.set_column("B:B", 32); ws1.set_column("C:C", 38)
        for i, c in enumerate(df1.columns):
            ws1.write(0, i, c, header_fmt)
        ws1.set_row(0, 24)

        # Tab 2
        rows2 = [{"Code": r["Code"], "Description": r["Description"], "Verdict": r["Verdict"],
                  "Flavor": r["Flavor"], "Why": r["Why"]} for r in results["Pre_Post_Tax"]]
        if not rows2:
            rows2 = [{"Code": "(none)", "Description": "", "Verdict": "", "Flavor": "",
                      "Why": "Scheduled Deductions report had no rows."}]
        df2 = pd.DataFrame(rows2)
        df2.to_excel(writer, sheet_name="2. Pre-Tax vs Post-Tax", index=False)
        ws2 = writer.sheets["2. Pre-Tax vs Post-Tax"]
        ws2.set_column("A:A", 14); ws2.set_column("B:B", 30)
        ws2.set_column("C:C", 11); ws2.set_column("D:D", 20)
        ws2.set_column("E:E", 90, wrap_fmt)
        for i, c in enumerate(df2.columns):
            ws2.write(0, i, c, header_fmt)
        ws2.set_row(0, 24)
        for ri, r in enumerate(rows2, start=1):
            v = r["Verdict"]
            if v == "PRE-TAX":
                ws2.write(ri, 2, "PRE-TAX", v_pre)
            elif v == "POST-TAX":
                ws2.write(ri, 2, "POST-TAX", v_post)
            ws2.set_row(ri, 30)

        # Tab 3
        bonus = results["Bonus"]
        sample = _pick_bonus_example(bonus)
        verdict_label = bonus["verdict"].upper().replace("_", "-")
        rows3 = [
            ("Verdict", verdict_label),
            ("Reason", bonus["reason"]),
            ("Bonus codes detected", ", ".join(bonus.get("bonus_codes_found", [])) or "(none)"),
        ]
        if "rows_tested" in bonus:
            rows3 += [
                ("Employees tested", bonus.get("rows_tested", 0)),
                ("    of which non-discretionary (WOT > OT)", bonus.get("differential_rows", 0)),
                ("    of which discretionary (WOT == OT)", bonus.get("matching_rows", 0)),
            ]
        if sample:
            rows3 += [
                ("", ""),
                ("---- Example employee that proves the verdict ----", ""),
                ("Employee", sample["employee"]),
                ("Plain OT amount (Paycom 'OT')", f"${sample['plain_ot_amount']:,}"),
                ("Weighted OT amount (Paycom 'WOT', FLSA-corrected)", f"${sample['weighted_ot_amount']:,}"),
                ("Differential (%)", f"{sample['differential_pct']}%"),
                ("Bonus amount in this period", f"${sample['bonus_amount']:,}"),
                ("", ""),
                ("Plain-English explanation",
                    "WOT > OT => Paycom rolled the bonus into the regular rate before "
                    "calculating the weighted OT. Per FLSA, that means the bonus is "
                    "NON-DISCRETIONARY."
                    if bonus["verdict"] == "non_discretionary" else
                    "WOT matches plain OT exactly => Paycom did NOT roll the bonus into the "
                    "regular rate => bonus is DISCRETIONARY."
                    if bonus["verdict"] == "discretionary" else
                    bonus["reason"]),
            ]
        df3 = pd.DataFrame(rows3, columns=["Field", "Value"])
        df3.to_excel(writer, sheet_name="3. Bonus Verdict", index=False)
        ws3 = writer.sheets["3. Bonus Verdict"]
        ws3.set_column("A:A", 50); ws3.set_column("B:B", 80, wrap_fmt)
        for i, c in enumerate(df3.columns):
            ws3.write(0, i, c, header_fmt)
        ws3.set_row(0, 24)
        if bonus["verdict"] == "non_discretionary":
            ws3.write(1, 1, verdict_label, v_nondisc)
        elif bonus["verdict"] == "discretionary":
            ws3.write(1, 1, verdict_label, v_disc)
        ws3.set_row(1, 28)

    return buf.getvalue()


def _deduction_reason_short(verdict, flavor):
    if verdict == "PRE-TAX" and flavor == "Section 125":
        return "Reduces FIT, FICA, Medicare, and state-income taxable wages -- Section 125 cafeteria plan."
    if verdict == "PRE-TAX" and flavor == "401k traditional":
        return "Reduces FIT and state-income taxable wages but NOT FICA/Medicare -- traditional 401(k)/403(b)."
    if verdict == "POST-TAX":
        return "Does not reduce taxable wages."
    return "Tax Treatment value not recognized -- review manually."


# ---------- Streamlit UI ----------

def render_ui():
    st.title("Paycom - Prior Payroll Setup Helper")
    st.caption(
        "Three answers from two Paycom files: what to set up in Uzio, "
        "is each deduction pre-tax or post-tax, and is the bonus discretionary."
    )

    col1, col2 = st.columns(2)
    with col1:
        prior_file = st.file_uploader(
            "Paycom Prior Payroll Register (long format)",
            type=["xlsx", "xls", "csv"],
            key="ppsh_prior",
        )
    with col2:
        sched_file = st.file_uploader(
            "Paycom Scheduled Deductions Report",
            type=["xlsx", "xls", "csv"],
            key="ppsh_sched",
        )

    if not (prior_file and sched_file):
        st.info("Upload both files to begin.")
        return

    if not st.button("Run", type="primary"):
        return

    with st.spinner("Analyzing..."):
        try:
            prior_df = _read_either(prior_file)
            sched_df = _read_either(sched_file)
            earnings = build_earnings_catalog(prior_df)
            taxes = build_taxes_discovered(prior_df)
            contributions, deductions = split_contribs_deductions(sched_df)
            pre_post = classify_pre_post_tax(sched_df)
            bonus = classify_bonus(prior_df)
            results = {
                "Earnings_Codes": earnings,
                "Contributions": contributions,
                "Deductions": deductions,
                "Taxes_Discovered": taxes,
                "Pre_Post_Tax": pre_post,
                "Bonus": bonus,
            }
        except Exception as e:
            st.error(f"Failed to analyze the files: {e}")
            raise

    # ANSWER 1
    st.markdown("## 1. What to set up in Uzio")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Earnings**")
        for r in earnings:
            st.markdown(f"- {r['Type Code']} -- {r['Type Description']}")
        if not earnings:
            st.caption("(none)")
    with c2:
        st.markdown("**Contributions**")
        for r in contributions:
            st.markdown(f"- {r['Deduction Code']} -- {r['Deduction Desc']}")
        if not contributions:
            st.caption("(none)")
    with c3:
        st.markdown("**Deductions**")
        for r in deductions:
            st.markdown(f"- {r['Deduction Code']} -- {r['Deduction Desc']}")
        if not deductions:
            st.caption("(none)")

    # ANSWER 2 -- pre/post-tax
    st.markdown("## 2. Pre-tax vs post-tax (per deduction)")
    if not pre_post:
        st.caption("Scheduled Deductions report did not include rows.")
    else:
        df_pp = pd.DataFrame([{"Code": r["Code"], "Verdict": r["Verdict"],
                               "Why": _deduction_reason_short(r["Verdict"], r["Flavor"])}
                              for r in pre_post])
        st.dataframe(df_pp, hide_index=True, use_container_width=True)

    # ANSWER 3 -- bonus
    st.markdown("## 3. Bonus: discretionary or non-discretionary?")
    verdict = bonus["verdict"]
    if verdict == "non_discretionary":
        st.error("**NON-DISCRETIONARY**")
    elif verdict == "discretionary":
        st.success("**DISCRETIONARY**")
    elif verdict == "no_bonus_in_file":
        st.info("**NO BONUS IN THIS FILE** — see reason below.")
    else:
        st.warning(f"**{verdict.upper().replace('_', '-')}**")
    st.markdown(f"_{bonus['reason']}_")

    sample = _pick_bonus_example(bonus)
    if sample:
        st.markdown(
            f"""
**Example: Employee `{sample['employee']}`**

- Plain OT amount (Paycom `OT`): **${sample['plain_ot_amount']:,}**
- Weighted OT amount (Paycom `WOT`, FLSA-corrected): **${sample['weighted_ot_amount']:,}**
- Differential: **{sample['differential_pct']}%**
- Bonus amount in this period: **${sample['bonus_amount']:,}**
"""
        )
        if verdict == "non_discretionary":
            st.markdown(
                "→ Paycom's WOT is **higher** than plain OT, which means a bonus was rolled "
                "into the regular rate before computing weighted OT. Per FLSA, that's "
                "**non-discretionary**."
            )
        elif verdict == "discretionary":
            st.markdown(
                "→ WOT matches plain OT exactly. The bonus did **not** inflate the regular "
                "rate basis, so it's **discretionary**."
            )

    st.markdown("---")
    base = (prior_file.name or "Paycom_Prior_Payroll").rsplit(".", 1)[0]
    xlsx_bytes = build_simplified_xlsx_bytes(results)
    st.download_button(
        "Download 3-tab Setup Helper Report (xlsx)",
        data=xlsx_bytes,
        file_name=f"{base}_Setup_Helper.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
