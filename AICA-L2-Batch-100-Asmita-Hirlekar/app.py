import streamlit as st
import pandas as pd
import numpy as np

# Page Configuration
st.set_page_config(
    page_title="Financial Health & Credit Assessment",
    page_icon="💳",
    layout="wide"
)

# Custom Styling
st.markdown("""
    <style>
    .main-header { font-size: 2.2rem; font-weight: 700; color: #1E3A8A; }
    .sub-header { font-size: 1.2rem; color: #4B5563; }
    .metric-card { background-color: #F3F4F6; padding: 20px; border-radius: 10px; text-align: center; }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">💳 Financial Health & Credit Assessment App</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Evaluate your credit readiness, debt-to-income ratio, and get personalized financial advice.</div>', unsafe_allow_html=True)
st.write("---")

# Sidebar for User Inputs
st.sidebar.header("📊 Input Your Financial Profile")

monthly_income = st.sidebar.number_input("Monthly Gross Income ($)", min_value=0, value=5500, step=200)
monthly_debt = st.sidebar.number_input("Total Monthly Debt Payments ($)", min_value=0, value=1200, step=100)
total_credit_limit = st.sidebar.number_input("Total Credit Card Limit ($)", min_value=0, value=15000, step=500)
total_credit_used = st.sidebar.number_input("Total Credit Card Balance Used ($)", min_value=0, value=3500, step=100)
missed_payments = st.sidebar.slider("Missed Payments in Last 12 Months", min_value=0, value=0, max_value=12)
account_age_years = st.sidebar.slider("Average Age of Accounts (Years)", min_value=0.1, value=5.0, max_value=30.0, step=0.5)

# Calculations
# 1. Debt-to-Income (DTI) Ratio
dti_ratio = (monthly_debt / monthly_income * 100) if monthly_income > 0 else 0

# 2. Credit Utilization Ratio
credit_utilization = (total_credit_used / total_credit_limit * 100) if total_credit_limit > 0 else 0

# 3. Estimated Credit Score Calculation (Weighted Mock Model)
# Base score: 850
base_score = 850
util_penalty = min(200, (credit_utilization / 100) * 180)
missed_penalty = missed_payments * 50
age_bonus = min(50, account_age_years * 3)

estimated_score = int(max(300, min(850, base_score - util_penalty - missed_penalty + age_bonus)))

# Determine Credit Rating Category
if estimated_score >= 800:
    credit_rating, badge_color = "Exceptional", "🟢"
elif estimated_score >= 740:
    credit_rating, badge_color = "Very Good", "🔵"
elif estimated_score >= 670:
    credit_rating, badge_color = "Good", "🟡"
elif estimated_score >= 580:
    credit_rating, badge_color = "Fair", "🟠"
else:
    credit_rating, badge_color = "Poor", "🔴"

# Main Layout Dashboard
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(label="Estimated Credit Score", value=f"{estimated_score}", delta=f"{badge_color} {credit_rating}")

with col2:
    dti_status = "Healthy" if dti_ratio <= 36 else ("Warning" if dti_ratio <= 43 else "High Risk")
    st.metric(label="Debt-to-Income (DTI) Ratio", value=f"{dti_ratio:.1f}%", delta=dti_status, delta_color="inverse")

with col3:
    util_status = "Optimal" if credit_utilization <= 30 else "High"
    st.metric(label="Credit Utilization", value=f"{credit_utilization:.1f}%", delta=util_status, delta_color="inverse")

st.write("---")

# Detailed Breakdown Section
st.subheader("🔍 Assessment & Health Breakdown")

col_a, col_b = st.columns(2)

with col_a:
    st.markdown("### Key Factor Analysis")
    
    # DTI Evaluation
    if dti_ratio <= 36:
        st.success("✅ **DTI Ratio is Excellent**: Lenders prefer a DTI under 36%. You are in a strong borrowing position.")
    elif dti_ratio <= 43:
        st.warning("⚠️ **DTI Ratio is Acceptable**: Your debt load is manageable, but lenders may scrutinize larger loans.")
    else:
        st.error("🚨 **DTI Ratio is High**: Your monthly debt payments consume a major share of your income. Focus on debt reduction.")

    # Utilization Evaluation
    if credit_utilization <= 30:
        st.success("✅ **Credit Utilization is Great**: Keeping your balance under 30% helps maximize your score.")
    else:
        st.error("🚨 **Credit Utilization is High**: Try paying down credit card balances to drop below 30%.")

with col_b:
    st.markdown("### 📋 Personalized Action Plan")
    actions = []
    
    if credit_utilization > 30:
        target_paydown = total_credit_used - (total_credit_limit * 0.3)
        actions.append(f"💡 Pay down **${target_paydown:.2f}** on your credit cards to reach the ideal 30% utilization threshold.")
    if missed_payments > 0:
        actions.append("💡 Set up **automatic minimum payments** to prevent future missed payment penalties.")
    if dti_ratio > 40:
        actions.append("💡 Look into **debt consolidation** or refinancing options to lower monthly interest obligations.")
    if not actions:
        actions.append("🎉 Your financial health metrics look stellar! Continue your current savings and repayment habits.")
        
    for action in actions:
        st.markdown(action)

st.write("---")

# Visual Data Table
st.subheader("📊 Profile Summary Table")
summary_data = {
    "Financial Metric": ["Monthly Gross Income", "Monthly Debt Obligations", "Total Credit Limit", "Credit Balance Used", "Missed Payments (12m)", "Account Age"],
    "Your Value": [f"${monthly_income:,.2f}", f"${monthly_debt:,.2f}", f"${total_credit_limit:,.2f}", f"${total_credit_used:,.2f}", f"{missed_payments}", f"{account_age_years} Years"]
}
st.dataframe(pd.DataFrame(summary_data), width="stretch")