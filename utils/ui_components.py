import streamlit as st

def inject_premium_styles():
    """Injects global 'Editorial Ledger' CSS and Typography (Manrope/Inter)."""
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@200;400;700;800&family=Inter:wght@300;400;600&display=swap');

        /* Global Typography Override */
        html, body, [class*="st-"] {
            font-family: 'Inter', sans-serif;
            color: #1b1c1c;
        }

        h1, h2, h3, h4, h5, h6 {
            font-family: 'Manrope', sans-serif !important;
            font-weight: 700 !important;
            color: #050e39 !important;
            letter-spacing: -0.02em;
        }

        /* The Editorial Card Surface */
        .premium-card {
            background-color: #ffffff;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: 0 4px 24px rgba(0, 0, 0, 0.04);
            border: 1px solid rgba(198, 197, 208, 0.2);
        }

        /* Action Hub: Critical Info (Soft Rose) */
        .action-hub-error {
            background: linear-gradient(145deg, #fff5f5, #ffffff);
            border-left: 5px solid #ba1a1a;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 16px;
        }
        .action-hub-error h5 { color: #93000a !important; margin-top: 0 !important; }

        /* Action Hub: Mapping Suggestions (Soft Amber) */
        .action-hub-warning {
            background: linear-gradient(145deg, #fffaf3, #ffffff);
            border-left: 5px solid #e8881f;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 16px;
        }
        .action-hub-warning h5 { color: #673700 !important; margin-top: 0 !important; }

        /* Glossy Primary Button */
        div.stButton > button:first-child {
            background: linear-gradient(135deg, #050e39 0%, #1c244e 100%) !important;
            color: white !important;
            border: none !important;
            border-radius: 8px !important;
            padding: 12px 32px !important;
            font-weight: 700 !important;
            font-family: 'Manrope', sans-serif !important;
            transition: all 0.3s ease !important;
            box-shadow: 0 4px 12px rgba(5, 14, 57, 0.2) !important;
        }
        div.stButton > button:hover {
            transform: translateY(-2px) !important;
            box-shadow: 0 6px 18px rgba(5, 14, 57, 0.3) !important;
            background: linear-gradient(135deg, #1c244e 0%, #050e39 100%) !important;
        }

        /* Refined Expander (Drawer Style) */
        .stExpander {
            border: none !important;
            background-color: #f5f3f3 !important;
            border-radius: 12px !important;
            margin-bottom: 12px !important;
        }
        .stExpander summary {
            font-family: 'Manrope', sans-serif !important;
            font-weight: 700 !important;
            font-size: 1.1rem !important;
            color: #050e39 !important;
            padding: 12px !important;
        }

        /* Pill Badges */
        .pill-error {
            background-color: #ffdad6;
            color: #ba1a1a;
            padding: 2px 10px;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 600;
        }
        .pill-warning {
            background-color: #ffdcc1;
            color: #6c3a00;
            padding: 2px 10px;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 600;
        }
        </style>
    """, unsafe_allow_html=True)

def render_premium_header(title, subtitle=None):
    """Renders a styled header for content sections."""
    st.markdown(f"### {title}")
    if subtitle:
        st.markdown(f"<p style='color: #46464f; margin-top: -10px; margin-bottom: 20px;'>{subtitle}</p>", unsafe_allow_html=True)

def action_hub_container(type='error'):
    """Context manager for rendering audit findings in styled containers."""
    css_class = 'action-hub-error' if type == 'error' else 'action-hub-warning'
    return st.container() # In Streamlit, styling full containers requires CSS injection based on nesting or IDs, but for this MVP we'll use markdown blocks inside.

def render_finding_card(title, data_dict, type='error'):
    """Renders a high-fidelity card for audit findings."""
    bg_color = "#fff5f5" if type == 'error' else "#fffaf3"
    border_color = "#ba1a1a" if type == 'error' else "#e8881f"
    text_color = "#93000a" if type == 'error' else "#673700"
    pill_class = 'pill-error' if type == 'error' else 'pill-warning'
    
    html = f"""
    <div style="background: {bg_color}; border-left: 5px solid {border_color}; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <h5 style="color: {text_color} !important; border: none !important; padding: 0 !important; margin: 0 !important;">{title}</h5>
        </div>
        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-top: 12px;">
    """
    
    for label, value in data_dict.items():
        html += f"""
        <div>
            <p style="font-size: 0.75rem; color: #46464f; margin: 0;">{label}</p>
            <p style="font-size: 1rem; font-weight: 600; color: {text_color}; margin: 0;">{value}</p>
        </div>
        """
        
    html += "</div></div>"
    st.markdown(html, unsafe_allow_html=True)
