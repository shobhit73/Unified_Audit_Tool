import streamlit as st
import pandas as pd
import numpy as np

def render_ui():
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

        html, body, [class*="css"] {
            font-family: 'IBM Plex Sans', sans-serif;
        }
        .main { background-color: #0f1117; }
        .block-container { padding: 2rem 3rem; }

        h1, h2, h3 { font-family: 'IBM Plex Mono', monospace; }

        .title-block {
            background: linear-gradient(135deg, #1a1f2e, #0f1117);
            border-left: 4px solid #00d4aa;
            padding: 1.5rem 2rem;
            margin-bottom: 2rem;
            border-radius: 0 8px 8px 0;
        }
        .title-block h1 { color: #00d4aa; font-size: 1.8rem; margin: 0; }
        .title-block p  { color: #8892a4; margin: 0.4rem 0 0; font-size: 0.9rem; }

        .card {
            background: #1a1f2e;
            border: 1px solid #2a3044;
            border-radius: 10px;
            padding: 1.2rem 1.5rem;
            margin-bottom: 1rem;
        }
        .card-title {
            font-family: 'IBM Plex Mono', monospace;
            font-size: 0.75rem;
            letter-spacing: 0.1em;
            color: #8892a4;
            text-transform: uppercase;
            margin-bottom: 0.5rem;
        }
        .card-value {
            font-size: 2rem;
            font-weight: 600;
            color: #e8ecf4;
        }

        .tag {
            display: inline-block;
            padding: 0.25rem 0.7rem;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
            font-family: 'IBM Plex Mono', monospace;
            margin: 0.2rem;
        }
        .tag-hourly    { background: #0d3d2e; color: #00d4aa; border: 1px solid #00d4aa44; }
        .tag-flat      { background: #2d1f0e; color: #f59e0b; border: 1px solid #f59e0b44; }
        .tag-nondiscr  { background: #1f0d2e; color: #a78bfa; border: 1px solid #a78bfa44; }
        .tag-discr     { background: #0d1f2e; color: #60a5fa; border: 1px solid #60a5fa44; }

        .section-header {
            font-family: 'IBM Plex Mono', monospace;
            font-size: 1rem;
            color: #00d4aa;
            border-bottom: 1px solid #2a3044;
            padding-bottom: 0.5rem;
            margin: 1.5rem 0 1rem;
        }

        .earning-row {
            background: #1a1f2e;
            border: 1px solid #2a3044;
            border-radius: 8px;
            padding: 0.8rem 1.2rem;
            margin-bottom: 0.5rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .verdict-box {
            padding: 0.4rem 1rem;
            border-radius: 6px;
            font-family: 'IBM Plex Mono', monospace;
            font-size: 0.8rem;
            font-weight: 600;
        }
        .verdict-non  { background: #1f0d2e; color: #a78bfa; }
        .verdict-disc { background: #0d1f2e; color: #60a5fa; }

        div[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
        .stDataFrame { background: #1a1f2e !important; }

        div[data-testid="stFileUploader"] {
            border: 2px dashed #2a3044;
            border-radius: 10px;
            padding: 1rem;
            background: #1a1f2e;
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="title-block">
        <h1>📊 ADP Payroll Setup Agent</h1>
        <p>Upload an ADP Prior Payroll Excel file to classify earnings as Hourly/Flat and Discretionary/Non-Discretionary</p>
    </div>
    """, unsafe_allow_html=True)

    uploaded_file = st.file_uploader("Upload ADP Prior Payroll Excel (.xlsx)", type=["xlsx"])

    if uploaded_file:
        with st.spinner("Reading file..."):
            df = pd.read_excel(uploaded_file)

        # ── Identify column groups ──────────────────────────────────────────────
        all_cols        = list(df.columns)
        hours_cols      = [c for c in all_cols if 'ADDITIONAL HOURS' in c.upper()]
        earning_cols    = [c for c in all_cols if 'ADDITIONAL EARNINGS' in c.upper()]
        reg_earn_col    = next((c for c in all_cols if c.strip().upper() == 'REGULAR EARNINGS'), None)
        ot_earn_col     = next((c for c in all_cols if c.strip().upper() == 'OVERTIME EARNINGS'), None)
        reg_hrs_col     = next((c for c in all_cols if c.strip().upper() == 'REGULAR HOURS'), None)
        ot_hrs_col      = next((c for c in all_cols if c.strip().upper() == 'OVERTIME HOURS'), None)

        def extract_code(col_name):
            """BCK from 'ADDITIONAL EARNINGS  : BCK-BACKUP'"""
            if ':' in col_name:
                return col_name.split(':')[1].strip().split('-')[0].strip()
            return col_name.strip()

        def extract_desc(col_name):
            if ':' in col_name:
                return col_name.split(':')[1].strip()
            return col_name.strip()

        # ── Map hours columns by code ───────────────────────────────────────────
        hours_codes = {extract_code(c): c for c in hours_cols}

        # ── Classify each additional earning as hourly or flat ──────────────────
        hourly_earnings = []
        flat_earnings   = []
        for ecol in earning_cols:
            code = extract_code(ecol)
            desc = extract_desc(ecol)
            if code in hours_codes:
                hourly_earnings.append({'code': code, 'description': desc, 'earn_col': ecol, 'hrs_col': hours_codes[code]})
            else:
                flat_earnings.append({'code': code, 'description': desc, 'earn_col': ecol})

        # ── Discretionary analysis ──────────────────────────────────────────────
        def analyze_discretionary(earn_items, df, reg_earn_col, ot_earn_col, reg_hrs_col, ot_hrs_col):
            results = []
            if not (reg_earn_col and ot_earn_col and reg_hrs_col and ot_hrs_col):
                return results

            for item in earn_items:
                ecol = item['earn_col']
                mask = (
                    df[ot_earn_col].notna() & (df[ot_earn_col] > 0) &
                    df[reg_hrs_col].notna() & (df[ot_hrs_col] > 0) &
                    df[ecol].notna() & (df[ecol] > 0)
                )
                sub = df[mask].copy()
                if len(sub) < 2:
                    results.append({**item, 'verdict': 'Insufficient Data', 'avg_diff': None, 'n_rows': len(sub), 'sample': sub})
                    continue

                sub['base_rate']     = sub[reg_earn_col] / sub[reg_hrs_col]
                sub['actual_ot']     = sub[ot_earn_col]  / sub[ot_hrs_col]
                sub['expected_ot']   = sub['base_rate'] * 1.5
                sub['diff']          = sub['actual_ot'] - sub['expected_ot']
                avg_diff             = sub['diff'].mean()
                median_diff          = sub['diff'].median()

                verdict = 'Non-Discretionary' if (avg_diff > 0.15 and median_diff > 0.05) else 'Discretionary'
                results.append({
                    **item,
                    'verdict':  verdict,
                    'avg_diff': avg_diff,
                    'n_rows':   len(sub),
                    'sample':   sub
                })
            return results

        all_additional = hourly_earnings + flat_earnings
        discr_results  = analyze_discretionary(all_additional, df, reg_earn_col, ot_earn_col, reg_hrs_col, ot_hrs_col)

        # ── Summary metrics ─────────────────────────────────────────────────────
        col1, col2, col3, col4 = st.columns(4)
        total_earn = 2 + len(earning_cols)   # reg + ot + additional
        non_discr  = sum(1 for r in discr_results if r['verdict'] == 'Non-Discretionary')
        discr      = sum(1 for r in discr_results if r['verdict'] == 'Discretionary')

        with col1:
            st.markdown(f"""<div class="card"><div class="card-title">Total Earnings</div>
            <div class="card-value">{total_earn}</div></div>""", unsafe_allow_html=True)
        with col2:
            st.markdown(f"""<div class="card"><div class="card-title">Hourly Earnings</div>
            <div class="card-value" style="color:#00d4aa">{len(hourly_earnings)+2}</div></div>""", unsafe_allow_html=True)
        with col3:
            st.markdown(f"""<div class="card"><div class="card-title">Non-Discretionary</div>
            <div class="card-value" style="color:#a78bfa">{non_discr}</div></div>""", unsafe_allow_html=True)
        with col4:
            st.markdown(f"""<div class="card"><div class="card-title">Discretionary</div>
            <div class="card-value" style="color:#60a5fa">{discr}</div></div>""", unsafe_allow_html=True)

        # ── Section 1: Hourly vs Flat ───────────────────────────────────────────
        st.markdown('<div class="section-header">① HOURLY vs FLAT EARNINGS</div>', unsafe_allow_html=True)

        lc, rc = st.columns(2)
        with lc:
            st.markdown("**✅ Hourly** *(have matching Hours column)*")
            # Always include Regular and OT
            st.markdown('<span class="tag tag-hourly">REG — Regular Earnings</span>', unsafe_allow_html=True)
            st.markdown('<span class="tag tag-hourly">OT — Overtime Earnings</span>', unsafe_allow_html=True)
            for item in hourly_earnings:
                st.markdown(f'<span class="tag tag-hourly">{item["description"]}</span>', unsafe_allow_html=True)

        with rc:
            st.markdown("**💲 Flat / Non-Hourly** *(no hours column)*")
            if flat_earnings:
                for item in flat_earnings:
                    st.markdown(f'<span class="tag tag-flat">{item["description"]}</span>', unsafe_allow_html=True)
            else:
                st.info("No flat earnings found.")

        # ── Section 2: Discretionary ────────────────────────────────────────────
        st.markdown('<div class="section-header">② DISCRETIONARY vs NON-DISCRETIONARY</div>', unsafe_allow_html=True)
        st.caption("Method: If Actual OT Rate > 1.5× Base Hourly Rate when bonus is present → Non-Discretionary")

        non_d = [r for r in discr_results if r['verdict'] == 'Non-Discretionary']
        d     = [r for r in discr_results if r['verdict'] == 'Discretionary']
        insuf = [r for r in discr_results if r['verdict'] == 'Insufficient Data']

        def sample_table(result):
            sub      = result['sample']
            ecol     = result['earn_col']
            reg_col  = reg_earn_col
            ot_col   = ot_earn_col
            rhc      = reg_hrs_col
            ohc      = ot_hrs_col

            sample = sub[[
                'ASSOCIATE ID' if 'ASSOCIATE ID' in sub.columns else sub.columns[0],
                rhc, ohc, reg_col, ot_col, ecol,
                'base_rate', 'actual_ot', 'expected_ot', 'diff'
            ]].head(5).copy()

            sample.columns = [
                'Associate ID', 'Reg Hrs', 'OT Hrs',
                'Reg Earnings', 'OT Earnings', 'Bonus Amt',
                'Base Rate', 'Actual OT Rate', 'Expected OT (1.5x)', 'Diff'
            ]
            for col in ['Reg Earnings','OT Earnings','Bonus Amt','Base Rate','Actual OT Rate','Expected OT (1.5x)','Diff']:
                sample[col] = sample[col].apply(lambda x: f"${x:,.4f}" if pd.notna(x) else '')
            return sample

        if non_d:
            st.markdown("#### 🟣 Non-Discretionary")
            for r in non_d:
                with st.expander(f"**{r['description']}** — avg OT rate diff: +${r['avg_diff']:.4f} | n={r['n_rows']} rows"):
                    st.dataframe(sample_table(r), use_container_width=True, hide_index=True)

        if d:
            st.markdown("#### 🔵 Discretionary")
            for r in d:
                with st.expander(f"**{r['description']}** — avg OT rate diff: ${r['avg_diff']:.4f} | n={r['n_rows']} rows"):
                    st.dataframe(sample_table(r), use_container_width=True, hide_index=True)

        if insuf:
            st.markdown("#### ⚪ Insufficient OT Data to Determine")
            for r in insuf:
                st.markdown(f"- **{r['description']}** ({r['n_rows']} OT rows with this bonus)")

        # ── Section 3: Full summary table ──────────────────────────────────────
        st.markdown('<div class="section-header">③ FULL SUMMARY TABLE</div>', unsafe_allow_html=True)

        rows = []
        rows.append({'Code': 'REG', 'Description': 'Regular Earnings', 'Type': 'Hourly', 'Classification': 'Non-Discretionary', 'Avg OT Diff': '—'})
        rows.append({'Code': 'OT',  'Description': 'Overtime Earnings', 'Type': 'Hourly', 'Classification': 'Non-Discretionary', 'Avg OT Diff': '—'})

        for r in discr_results:
            is_hourly = any(r['code'] == item['code'] for item in hourly_earnings)
            rows.append({
                'Code':           r['code'],
                'Description':    r['description'],
                'Type':           'Hourly' if is_hourly else 'Flat',
                'Classification': r['verdict'],
                'Avg OT Diff':    f"${r['avg_diff']:.4f}" if r['avg_diff'] is not None else '—'
            })

        summary_df = pd.DataFrame(rows)
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

        # Download
        csv = summary_df.to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Download Summary CSV", csv, "earnings_summary.csv", "text/csv")

    else:
        st.markdown("""
        <div class="card" style="text-align:center; padding: 3rem;">
            <div style="font-size:3rem; margin-bottom:1rem;">📂</div>
            <div style="color:#8892a4; font-family:'IBM Plex Mono',monospace;">
                Upload an ADP Prior Payroll .xlsx file to get started
            </div>
            <div style="color:#4a5568; font-size:0.8rem; margin-top:0.8rem;">
                Expects columns: REGULAR EARNINGS, OVERTIME EARNINGS, REGULAR HOURS, OVERTIME HOURS,<br>
                ADDITIONAL EARNINGS : CODE-NAME, ADDITIONAL HOURS : CODE-NAME
            </div>
        </div>
        """, unsafe_allow_html=True)

if __name__ == "__main__":
    st.set_page_config(page_title="ADP Payroll Setup Agent", page_icon="📊", layout="wide")
    render_ui()
