import streamlit as st
import importlib

# Set Page Config (Must be first)
st.set_page_config(page_title="AI Powered Audit Hub", layout="wide", page_icon="🤖")

# Custom CSS for UI enhancements
st.markdown("""
<style>
    /* Main container styling */
    .main {
        background-color: #f8f9fa;
    }
    
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background-color: #070738; /* Deep navy */
    }
    section[data-testid="stSidebar"] * {
        color: #ffffff !important; /* White text */
    }
    
    /* Headers */
    h1, h2, h3 {
        color: #070738;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    
    /* Buttons */
    .stButton > button {
        background-color: #e74c3c;
        color: white;
        border-radius: 8px;
        font-weight: bold;
        border: none;
    }
    .stButton > button:hover {
        background-color: #c0392b;
        color: white;
    }
    
    /* Radio buttons in sidebar */
    .stRadio > div {
        background-color: transparent;
        margin-bottom: -15px; /* Compact spacing */
    }
    .stRadio label {
        font-size: 15px;
        padding: 4px 10px; /* Reduced padding */
        border-radius: 5px;
        color: #ffffff !important;
        transition: background-color 0.3s;
    }
    .stRadio label:hover {
        background-color: #1a1a4b;
    }
    .stRadio p {
        font-size: 15px; /* Consistent font size */
    }
    
    /* Info box */
    .stAlert {
        border-radius: 8px;
        padding: 0.5rem; /* Compact info box */
    }
    
    /* Style for Provider Headers in Sidebar */
    .provider-header {
        font-size: 1.1rem;
        font-weight: bold;
        color: #e2e8f0;
        margin-top: 0.5rem;
        margin-bottom: 0px;
        border-bottom: 1px solid #4a5568;
    /* AI Title Gradient */
    .ai-title {
        background: linear-gradient(90deg, #4b6cb7 0%, #182848 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: bold;
        font-size: 4.0rem;
        padding-bottom: 10px;
    }
    
    /* Sidebar specific override */
    [data-testid="stSidebar"] .ai-title {
        background: linear-gradient(90deg, #00d2ff 0%, #3a7bd5 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Sidebar Navigation Grouping
# ---------------------------------------------------------
with st.sidebar:
    st.markdown('<div class="ai-title">AI Powered<br>Audit Hub</div>', unsafe_allow_html=True)
    st.markdown("---")
    
    # 1. Select Provider
    provider = st.radio("Select Provider", ["ADP", "Paycom"], index=0)
    
    # 2. Dynamic Tool Selection based on Provider
    tool_option = None
    
    if provider == "ADP":
        st.markdown('<div class="provider-header">ADP Tools</div>', unsafe_allow_html=True)
        tool_option = st.radio("Select ADP Tool", [
            "Deduction Audit", 
            "Prior Payroll Audit",
            "Census Audit",
            "Payment Audit",
            "Emergency Contact Audit",
            "ADP Withholding Audit"
        ], index=0, label_visibility="collapsed")
        
    elif provider == "Paycom":
        st.markdown('<div class="provider-header">Paycom Tools</div>', unsafe_allow_html=True)
        tool_option = st.radio("Select Paycom Tool", [
            "Paycom Census Audit",
            "Paycom Withholding Audit",
            "Paycom Payment Audit",
            "Paycom Deduction Audit"
        ], index=0, label_visibility="collapsed")

    # Footer
    st.markdown("---")
    st.caption(f"Mode: {provider} Audit")
    st.caption("v2.3 | Unified Platform")

# ---------------------------------------------------------
# Router Logic
# ---------------------------------------------------------
if tool_option == "Deduction Audit":
    import deduction_audit_app
    importlib.reload(deduction_audit_app) 
    deduction_audit_app.render_ui()
    
elif tool_option == "Prior Payroll Audit":
    import prior_payroll_audit_app
    importlib.reload(prior_payroll_audit_app)
    prior_payroll_audit_app.render_ui()

elif tool_option == "Census Audit":
    import census_audit_app
    importlib.reload(census_audit_app)
    # Note: This is practically "ADP Census Audit"
    census_audit_app.render_ui()

elif tool_option == "Payment Audit":
    import adp_payment_audit_app
    importlib.reload(adp_payment_audit_app)
    adp_payment_audit_app.render_ui()

elif tool_option == "Emergency Contact Audit":
    import adp_emergency_audit_app
    importlib.reload(adp_emergency_audit_app)
    adp_emergency_audit_app.render_ui()

elif tool_option == "Paycom Census Audit":
    import paycom_census_audit_app
    importlib.reload(paycom_census_audit_app)
    paycom_census_audit_app.render_ui()

elif tool_option == "Paycom Withholding Audit":
    import paycom_withholding_audit_app
    importlib.reload(paycom_withholding_audit_app)
    paycom_withholding_audit_app.render_ui()

elif tool_option == "Paycom Payment Audit":
    import paycom_payment_audit_app
    importlib.reload(paycom_payment_audit_app)
    paycom_payment_audit_app.render_ui()

elif tool_option == "Paycom Deduction Audit":
    import paycom_deduction_audit_app
    importlib.reload(paycom_deduction_audit_app)
    paycom_deduction_audit_app.render_ui()

elif tool_option == "ADP Withholding Audit":
    import adp_withholding_audit_app
    importlib.reload(adp_withholding_audit_app)
    adp_withholding_audit_app.render_ui()
