"""
Lead Detail Page

View comprehensive information about a specific lead including property details,
scoring breakdown, tax sale/foreclosure info, and historical trends.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

import streamlit as st

from src.wholesaler.frontend.utils import APIClient, get_tier_color, get_tier_label
from src.wholesaler.frontend.components.tables import (
    render_property_details_table,
    render_tax_sale_table,
    render_foreclosure_table,
    render_scoring_reasons_table,
)
from src.wholesaler.frontend.components.charts import (
    create_score_breakdown_chart,
    create_score_trend_chart,
)

# Page configuration
st.set_page_config(
    page_title="Lead Detail - Wholesaler",
    page_icon="",
    layout="wide",
)

# Initialize API client
if "api_client" not in st.session_state:
    st.session_state.api_client = APIClient()

# Page header
st.title(" Lead Detail")

# Parcel ID input
parcel_id = st.text_input(
    "Enter Parcel ID",
    placeholder="e.g., 12-34-56-7890-01-001",
    help="Enter the normalized parcel ID to view lead details",
)

if parcel_id:
    try:
        with st.spinner("Loading lead details..."):
            lead = st.session_state.api_client.get_lead_detail(parcel_id)

        # Header with tier badge
        col1, col2 = st.columns([3, 1])

        with col1:
            property_data = lead.get("property", {})
            address = property_data.get("situs_address", "N/A")
            city = property_data.get("city", "")
            state = property_data.get("state", "")
            location = f"{city}, {state}" if city and state else city or state or ""

            st.header(f"{address}")
            if location:
                st.subheader(location)

        with col2:
            tier = lead["tier"]
            tier_color = get_tier_color(tier)
            st.markdown(
                f"""
                <div style='
                    background-color: {tier_color};
                    color: white;
                    padding: 1rem;
                    border-radius: 0.5rem;
                    text-align: center;
                    font-size: 1.5rem;
                    font-weight: bold;
                '>
                    {get_tier_label(tier)}
                </div>
                """,
                unsafe_allow_html=True
            )

        # Score overview
        st.markdown("---")
        st.subheader(" Score Overview")

        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            st.metric(
                label="Total Score",
                value=f"{lead['total_score']:.1f}",
            )

        with col2:
            st.metric(
                label="Distress Score",
                value=f"{lead['distress_score']:.1f}",
            )

        with col3:
            st.metric(
                label="Value Score",
                value=f"{lead['value_score']:.1f}",
            )

        with col4:
            st.metric(
                label="Location Score",
                value=f"{lead['location_score']:.1f}",
            )

        with col5:
            st.metric(
                label="Urgency Score",
                value=f"{lead['urgency_score']:.1f}",
            )

        # Hybrid / priority metrics
        if lead.get("hybrid_score") is not None or lead.get("priority_score") is not None:
            st.subheader(" Hybrid & ML Signals")
            col1, col2, col3 = st.columns(3)

            with col1:
                if lead.get("hybrid_score") is not None:
                    st.metric("Hybrid Score", f"{lead['hybrid_score']:.1f}", help="Bucketed score from hybrid rules")
                if lead.get("hybrid_tier"):
                    st.metric("Hybrid Tier", lead["hybrid_tier"])

            with col2:
                if lead.get("logistic_probability") is not None:
                    st.metric(
                        "Sell Probability",
                        f"{lead['logistic_probability']*100:.1f}%",
                        help="Logistic opportunity model",
                    )

            with col3:
                if lead.get("priority_score") is not None:
                    st.metric("Priority Score", f"{lead['priority_score']:.1f}")

        # Profitability Section (Phase 3.6)
        if lead.get("profitability_details") or lead.get("profitability_score"):
            st.subheader("💰 Profitability Analysis")
            p_col1, p_col2, p_col3, p_col4 = st.columns(4)
            
            details = lead.get("profitability_details") or {}
            
            with p_col1:
                if lead.get("profitability_score"):
                    st.metric("Profitability Score", f"{lead['profitability_score']:.1f}")
            
            with p_col2:
                if "projected_profit" in details:
                    st.metric("Projected Profit", f"${details['projected_profit']:,.2f}")
                    
            with p_col3:
                if "roi_percent" in details:
                    st.metric("Est. ROI", f"{details['roi_percent']:.1f}%")
                    
            with p_col4:
                if "is_profitable" in details:
                    is_prof = details["is_profitable"]
                    st.metric("Buy Box", "✅ PASS" if is_prof else "❌ FAIL")

        # ML Risk Section (Phase 3.7)
        if lead.get("ml_risk_score") is not None:
            st.subheader("🤖 Label-Free ML Risk")
            ml_col1, ml_col2, ml_col3, ml_col4 = st.columns(4)
            
            with ml_col1:
                st.metric("Composite Risk", f"{lead['ml_risk_score']:.4f}")
                
            with ml_col2:
                if lead.get("ml_risk_tier"):
                    st.metric("Risk Tier", lead["ml_risk_tier"])
                    
            with ml_col3:
                if lead.get("ml_cluster_id") is not None:
                    st.metric("Cluster ID", str(lead["ml_cluster_id"]))
                    
            with ml_col4:
                if lead.get("ml_anomaly_score") is not None:
                    st.metric("Anomaly Score", f"{lead['ml_anomaly_score']:.4f}")

        # Score breakdown chart
        fig = create_score_breakdown_chart(lead)
        st.plotly_chart(fig, use_container_width=True)

        # Scoring reasons
        st.subheader(" Scoring Reasons")
        render_scoring_reasons_table(lead)

        # Property Valuation Section (NEW - shows appraiser data)
        st.markdown("---")
        st.subheader("🏠 Property Valuation")
        
        # Try to get property appraiser data from the property record
        # This data comes from the enrichment pipeline
        property_data = lead.get("property", {})
        
        # Check if we have enriched property data
        # The API should expose this from property_record or enriched_seed data
        has_appraiser_data = False
        market_value = None
        assessed_value = None
        year_built = None
        living_area = None
        
        # TODO: API needs to expose property_record data in lead detail response
        # For now, check if these fields exist in property_data
        if property_data.get("market_value"):
            has_appraiser_data = True
            market_value = property_data.get("market_value")
            assessed_value = property_data.get("assessed_value")
            year_built = property_data.get("year_built")
            living_area = property_data.get("living_area")
        
        val_col1, val_col2, val_col3, val_col4 = st.columns(4)
        
        with val_col1:
            if market_value:
                st.metric("Market Value", f"${market_value:,.0f}", help="From Orange County Property Appraiser")
            else:
                st.metric("Market Value", "Not Available", help="Property appraiser data not found")
        
        with val_col2:
            if assessed_value:
                st.metric("Assessed Value", f"${assessed_value:,.0f}", help="Tax assessed value")
            else:
                st.metric("Assessed Value", "Not Available")
        
        with val_col3:
            if year_built:
                st.metric("Year Built", str(year_built))
            else:
                st.metric("Year Built", "N/A")
        
        with val_col4:
            if living_area:
                st.metric("Living Area", f"{living_area:,.0f} sqft")
            else:
                st.metric("Living Area", "N/A")
        
        # Data source indicator
        if has_appraiser_data:
            st.success("✅ Property appraiser data available - profitability calculations use actual values")
        else:
            st.warning("⚠️ Property appraiser data not available - profitability estimates may use heuristics")

        # Property details
        st.markdown("---")
        st.subheader(" Property Details")
        render_property_details_table(lead)

        # Tax sale and foreclosure info
        st.markdown("---")
        col1, col2 = st.columns(2)

        with col1:
            st.subheader(" Tax Sale Information")
            render_tax_sale_table(lead)

        with col2:
            st.subheader(" Foreclosure Information")
            render_foreclosure_table(lead)

        # Historical trends
        st.markdown("---")
        st.subheader(" Score History")

        try:
            with st.spinner("Loading historical data..."):
                history = st.session_state.api_client.get_lead_history(parcel_id, limit=30)

            if history:
                fig = create_score_trend_chart(history)
                st.plotly_chart(fig, use_container_width=True)

                st.info(f"Showing {len(history)} historical snapshots")
            else:
                st.info("No historical score data available for this lead.")

        except Exception as e:
            st.warning(f"Could not load score history: {str(e)}")

        # Map view (if coordinates available)
        if property_data.get("latitude") and property_data.get("longitude"):
            st.markdown("---")
            st.subheader(" Location")

            map_data = {
                "lat": [property_data["latitude"]],
                "lon": [property_data["longitude"]],
            }

            st.map(map_data, zoom=15)

        # Action buttons
        st.markdown("---")
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button(" View All Leads"):
                st.switch_page("pages/1__Leads_List.py")

        with col2:
            if st.button(" View on Map"):
                st.switch_page("pages/3__Map_View.py")

        with col3:
            if st.button(" Refresh"):
                st.rerun()

    except Exception as e:
        st.error(f"Failed to load lead details: {str(e)}")

        if "404" in str(e):
            st.warning(f"Lead not found with Parcel ID: {parcel_id}")
            st.info("Please check the Parcel ID and try again.")
        else:
            st.info("Make sure the FastAPI server is running on http://localhost:8000")

else:
    st.info(" Enter a Parcel ID above to view lead details.")

    st.markdown("---")
    st.markdown("### How to find a Parcel ID:")
    st.markdown("""
    1. Go to the **Leads List** page
    2. Browse or filter leads
    3. Copy the Parcel ID from the table
    4. Paste it in the input field above
    """)

    if st.button(" Go to Leads List"):
        st.switch_page("pages/1__Leads_List.py")

# Footer
st.markdown("---")
st.markdown(" **Tip:** Bookmark this page with a Parcel ID parameter for quick access to specific leads.")
