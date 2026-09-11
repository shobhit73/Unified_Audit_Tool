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
- **No wrapper divs across calls**: `st.markdown("<div class='x'>")` … `st.markdown("</div>")` does NOT wrap what is rendered in between — each `st.markdown` is its own element and the div closes immediately, leaving an empty box. Use `st.container(border=True)`.

## 5. Light and dark theme
Viewers switch Light / Dark / System from Streamlit's ⋮ → Settings menu. `prefers-color-scheme` reports only the OS, and `st.context.theme` can be stale right after a switch — but Streamlit sets `color-scheme` on `.stApp` to the theme actually showing, so CSS `light-dark(<light>, <dark>)` DOES follow the viewer's choice (verified Sep 2026, both themes). Everything else must work on both backgrounds without knowing which one is showing.

- **🔴 NEVER** set a text `color` on generic elements (`p`, `li`, `label`, `h1`–`h6`, expander titles, radio labels). It was done once (`#1b1c1c` body, navy headings) and made the Census Sanity Check title and text invisible in Dark mode.
- **🔴 NEVER** give a card, callout or table cell a solid light background (`#ffffff`, `#fff5f5`, `#FFE5E5`, …). The theme's text colour stays on top of it — white on pale pink in Dark mode.
- **🟢 Tints**: translucent backgrounds — e.g. `rgba(229, 72, 77, 0.10)` for an error box, `rgba(128, 128, 128, 0.06)` for a neutral card.
- **🟢 Accents** (coloured headings, pills): `light-dark(<deep shade>, <bright shade>)` — `_TONES` in `utils/ui_components.py`, e.g. red `light-dark(#ba1a1a, #ff7b72)`; use `_callout()` for a coloured header box. A single mid-tone hex was tried first and fell to 2.8:1 on the light theme.
- **🟢 Secondary text**: `opacity: 0.75`, not a grey hex.
- A self-contained block that paints BOTH its own background and its own text (the navy sidebar, the Payment Audit hero banner) is fine — it looks the same in either theme.
- **Check both themes** before pushing a UI change: ⋮ → Settings → Dark, then Light.

---
> [!IMPORTANT]
> **Before making UI changes**: Run a localized CSS test or use `st.columns` to verify that your change doesn't push elements off-screen or overlap existing buttons.
