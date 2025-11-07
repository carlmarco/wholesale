"""
Deal Analyzer Page

ML-powered deal analysis with ARV estimation, repair costs, and ROI calculator.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

import streamlit as st

from src.wholesaler.frontend.utils import APIClient, format_currency, format_score

# Page configuration
st.set_page_config(
    page_title="Deal Analyzer - Wholesaler",
    page_icon="",
    layout="wide",
)

# Initialize API client
if "api_client" not in st.session_state:
    st.session_state.api_client = APIClient()

# Page header
st.title("Deal Analyzer")
st.markdown("ML-powered property analysis with ARV estimation, repair costs, and ROI calculator.")

# Parcel ID input
parcel_id = st.text_input(
    "Enter Parcel ID",
    placeholder="e.g., 12-34-56-7890-01-001",
    help="Enter the normalized parcel ID to analyze the deal",
)

if parcel_id:
    try:
        with st.spinner("Analyzing deal..."):
            # Fetch analysis from API
            response = st.session_state.api_client.session.get(
                f"{st.session_state.api_client.base_url}/api/v1/analysis/{parcel_id}"
            )
            response.raise_for_status()
            analysis = response.json()

        # Recommendation badge
        rec_colors = {
            "strong_buy": "#28a745",  # Green
            "buy": "#17a2b8",  # Blue
            "hold": "#ffc107",  # Yellow
            "pass": "#dc3545",  # Red
        }

        rec_labels = {
            "strong_buy": "STRONG BUY",
            "buy": "BUY",
            "hold": "HOLD",
            "pass": "PASS",
        }

        rec = analysis["recommendation"]
        rec_color = rec_colors.get(rec, "#6c757d")
        rec_label = rec_labels.get(rec, rec.upper())

        st.markdown(
            f"""
            <div style='
                background-color: {rec_color};
                color: white;
                padding: 1rem;
                border-radius: 0.5rem;
                text-align: center;
                font-size: 2rem;
                font-weight: bold;
                margin-bottom: 1rem;
            '>
                {rec_label}
            </div>
            """,
            unsafe_allow_html=True
        )

        # Key metrics
        st.header("Key Metrics")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                label="Estimated ARV",
                value=format_currency(analysis["estimated_arv"]),
            )

        with col2:
            st.metric(
                label="Repair Costs",
                value=format_currency(analysis["estimated_repair_costs"]),
            )

        with col3:
            st.metric(
                label="Max Offer (70% Rule)",
                value=format_currency(analysis["max_offer_price"]),
            )

        with col4:
            st.metric(
                label="ROI",
                value=f"{analysis['roi_percentage']:.1f}%",
                delta=f"${analysis['potential_profit']:,.0f} profit",
            )

        # Detailed analysis
        st.markdown("---")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Opportunity Factors")

            if analysis["opportunity_factors"]:
                for factor in analysis["opportunity_factors"]:
                    st.success(f"✓ {factor}")
            else:
                st.info("No significant opportunity factors identified")

        with col2:
            st.subheader("Risk Factors")

            if analysis["risk_factors"]:
                for risk in analysis["risk_factors"]:
                    st.warning(f"⚠ {risk}")
            else:
                st.success("No significant risk factors identified")

        # Confidence level
        st.markdown("---")
        st.subheader("Analysis Confidence")

        confidence = analysis["confidence_level"]
        confidence_colors = {
            "high": "#28a745",
            "medium": "#ffc107",
            "low": "#dc3545",
        }

        confidence_labels = {
            "high": "High Confidence",
            "medium": "Medium Confidence",
            "low": "Low Confidence",
        }

        conf_color = confidence_colors.get(confidence, "#6c757d")
        conf_label = confidence_labels.get(confidence, confidence.capitalize())

        col1, col2, col3 = st.columns([1, 2, 1])

        with col2:
            st.markdown(
                f"""
                <div style='
                    background-color: {conf_color};
                    color: white;
                    padding: 0.75rem;
                    border-radius: 0.5rem;
                    text-align: center;
                    font-size: 1.25rem;
                    font-weight: bold;
                '>
                    {conf_label}
                </div>
                """,
                unsafe_allow_html=True
            )

        # Deal breakdown
        st.markdown("---")
        st.subheader("Deal Breakdown")

        st.markdown(f"""
        **After Repair Value (ARV):** {format_currency(analysis['estimated_arv'])}

        **Estimated Repair Costs:** {format_currency(analysis['estimated_repair_costs'])}

        **Max Allowable Offer (70% Rule):** {format_currency(analysis['max_offer_price'])}
        - *Formula: (ARV × 0.70) - Repair Costs*

        **Potential Profit:** {format_currency(analysis['potential_profit'])}

        **Return on Investment:** {analysis['roi_percentage']:.1f}%
        """)

        # Investment strategy notes
        st.markdown("---")
        st.subheader("Investment Strategy Notes")

        st.info("""
        **70% Rule:** A common wholesaling rule where you should pay no more than 70% of the ARV minus repair costs.
        This leaves room for profit margins, holding costs, and buyer expectations.

        **ROI Benchmarks:**
        - 40%+: Excellent deal
        - 25-40%: Good deal
        - 15-25%: Fair deal
        - <15%: Marginal deal
        """)

        # Action buttons
        st.markdown("---")
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("View Lead Detail"):
                st.switch_page("pages/2__Lead_Detail.py")

        with col2:
            if st.button("View All Leads"):
                st.switch_page("pages/1__Leads_List.py")

        with col3:
            if st.button("Refresh Analysis"):
                st.rerun()

    except Exception as e:
        st.error(f"Failed to analyze deal: {str(e)}")

        if "404" in str(e):
            st.warning(f"Lead not found with Parcel ID: {parcel_id}")
            st.info("Please check the Parcel ID and try again.")
        else:
            st.info("Make sure the FastAPI server is running on http://localhost:8000")

else:
    st.info("Enter a Parcel ID above to analyze the deal.")

    st.markdown("---")
    st.markdown("### What is Deal Analysis?")

    st.markdown("""
    Our ML-powered Deal Analyzer helps you make informed investment decisions by providing:

    1. **ARV Estimation**: After Repair Value based on location, property type, and market conditions
    2. **Repair Cost Estimation**: Estimated rehab costs based on distress indicators
    3. **ROI Calculation**: Expected return on investment with the 70% rule
    4. **Risk Assessment**: Identifies potential issues and concerns
    5. **Opportunity Identification**: Highlights positive deal factors

    ### How to Use
    1. Go to the **Leads List** page
    2. Browse or filter leads
    3. Copy the Parcel ID from the table
    4. Paste it in the input field above
    5. Review the comprehensive deal analysis
    """)

    if st.button("Go to Leads List"):
        st.switch_page("pages/1__Leads_List.py")

# Footer
st.markdown("---")
st.markdown("**Note:** ML estimates are based on heuristics and market data. Always perform due diligence before making investment decisions.")
