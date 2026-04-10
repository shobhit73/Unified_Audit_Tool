# Census Sanity UI Constitution (frontend.md)

This document defines the core principles to maintain the **High-Fidelity "Editorial Ledger" UI** without causing regressions or app crashes. **Future agents must read and follow these rules strictly.**

---

## 1. CSS Scoping (Stability First) ⭐
Streamlit's internal components (sidebar, expanders, icons) are sensitive to CSS overrides. 

- **🔴 NEVER USE**: `* { font-family: ... }` or `html, body { ... }`. This strips functional SVG icons (expanders, arrows).
- **🟢 ALWAYS USE**: Specific selectors to limit the "blast radius."
  - Typography: `.stMarkdown p, .stMarkdown span, .stMarkdown li { font-family: "Outfit", sans-serif; }`
  - Buttons: `.stButton button { border-radius: 8px !important; ... }`
- **Icon Protection**: If applying a global font, ensure you exclude SVGs:
  ```css
  :not(svg):not(i) { font-family: 'Outfit', sans-serif !important; }
  ```

## 2. Audit "Action Center" Logic
Audit results must be **Actionable** and **Clean**.

- **Vertical Height Control**: Always wrap high-volume lists (Date Mismatches, Zip Errors) in a fixed-height scroll container:
  ```python
  with st.container(height=400, border=True):
      # columns and results go here
  ```
- **Consolidation (No Repeats)**: Use Regex to sanitize error messages for grouping. 
  - *Goal*: Don't show "Date mismatch (Jan 1)" and "Date mismatch (Jan 2)" as separate lines. 
  - *Pattern*: `clean_issue = re.sub(r'\(.*?\)', '', original_issue)` to group by the core problem.
- **Employee ID Mapping**: Every error must be linked to the affected **Employee IDs** (e.g., `Issue Name: [IDs: A001, B002]`).

## 3. Premium Aesthetics
- **Core Button Style**: Dark Blue Gradient (`linear-gradient(135deg, #1e3a8a, #3b82f6)`).
- **Text Contrast**: Use `!important` to force white text on primary buttons:
  ```css
  .stButton button p { color: #ffffff !important; }
  ```
- **Spacing**: Use `st.markdown("<br>", unsafe_allow_html=True)` sparingly to prevent text overlap.

## 4. Crash Prevention
- **Streamlit Version**: Ensure compatibility with `v1.30+` for `st.container(height=...)`.
- **Minified HTML**: When using `render_finding_card` (custom utils), ensure the HTML string is minified (no literal newlines) to prevent rendering breaks.

---
> [!IMPORTANT]
> **Before making UI changes**: Run a localized CSS test or use `st.columns` to verify that your change doesn't push elements off-screen or overlap existing buttons.
