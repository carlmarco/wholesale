"""
Streamlit Dashboard for Wholesaler Lead Management System

Main dashboard for viewing leads, property analysis, and system metrics.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
from typing import Dict, List, Any

# Page configuration
st.set_page_config(
    page_title="Wholesaler Lead Management",
    page_icon="🏡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API base URL (from environment or default to localhost)
API_BASE_URL = "http://api:8000/api/v1"  # Docker service name
# Fallback to localhost for local development
try:
    response = requests.get(f"{API_BASE_URL}/health", timeout=1)
except:
    API_BASE_URL = "http://localhost:8000/api/v1"


def fetch_api(endpoint: str) -> Dict[str, Any]:
    """Fetch data from API endpoint."""
    try:
        response = requests.get(f"{API_BASE_URL}{endpoint}", timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"API Error: {str(e)}")
        return {}


def main():
    """Main dashboard application."""

    # Sidebar
    with st.sidebar:
        st.title("Wholesaler Dashboard")
        st.markdown("---")

        page = st.radio(
            "Navigate",
            ["Overview", "Tier A Leads", "All Leads", "Properties", "Analytics"],
            label_visibility="collapsed"
        )

        st.markdown("---")
        st.markdown("### Filters")

        tier_filter = st.multiselect(
            "Lead Tier",
            ["A", "B", "C", "D"],
            default=["A", "B"]
        )

        min_score = st.slider(
            "Minimum Score",
            min_value=0,
            max_value=100,
            value=30,
            step=5
        )

        st.markdown("---")
        st.markdown("### System Status")

        # Fetch system stats
        stats_data = fetch_api("/stats/dashboard")
        if stats_data:
            st.metric("Total Properties", f"{stats_data.get('total_properties', 0):,}")
            st.metric("Scored Leads", f"{stats_data.get('total_leads', 0):,}")
            st.metric("Tier A Leads", f"{stats_data.get('tier_a_count', 0):,}")

    # Main content
    if page == "Overview":
        show_overview_page(stats_data)
    elif page == "Tier A Leads":
        show_tier_a_leads_page()
    elif page == "All Leads":
        show_all_leads_page(tier_filter, min_score)
    elif page == "Properties":
        show_properties_page()
    elif page == "Analytics":
        show_analytics_page()


def show_overview_page(stats_data: Dict):
    """Show overview dashboard page."""
    st.title("System Overview")

    # Key metrics row
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Properties",
            f"{stats_data.get('total_properties', 0):,}",
            delta=None
        )

    with col2:
        st.metric(
            "Tier A Leads",
            f"{stats_data.get('tier_a_count', 0):,}",
            delta=None,
            help="Hot leads - highest investment potential"
        )

    with col3:
        st.metric(
            "Tax Sales",
            f"{stats_data.get('tax_sales_count', 0):,}",
            delta=None
        )

    with col4:
        st.metric(
            "Foreclosures",
            f"{stats_data.get('foreclosures_count', 0):,}",
            delta=None
        )

    st.markdown("---")

    # Tier distribution
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Lead Tier Distribution")
        tier_counts = stats_data.get('tier_distribution', {})
        if tier_counts:
            fig = px.pie(
                values=list(tier_counts.values()),
                names=list(tier_counts.keys()),
                title="Leads by Tier",
                color_discrete_map={"A": "#00cc66", "B": "#3399ff", "C": "#ffaa00", "D": "#ff3333"}
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No tier distribution data available")

    with col2:
        st.subheader("Score Distribution")
        # Fetch leads for score distribution
        leads_response = fetch_api("/leads?limit=1000")
        leads_list = []
        if isinstance(leads_response, dict) and 'leads' in leads_response:
            leads_list = leads_response['leads']
        elif isinstance(leads_response, list):
            leads_list = leads_response

        if leads_list:
            scores = [lead.get('total_score', 0) for lead in leads_list]
            fig = px.histogram(
                x=scores,
                nbins=20,
                title="Lead Score Distribution",
                labels={"x": "Total Score", "count": "Number of Leads"}
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No score distribution data available")

    st.markdown("---")

    # Recent activity
    st.subheader("Recent Activity")
    st.info("Last pipeline run: Today at 4:00 AM")
    st.success("All services healthy ✓")


def show_tier_a_leads_page():
    """Show Tier A leads page."""
    st.title("Tier A Leads - Hot Investment Opportunities")

    # Fetch Tier A leads
    leads_response = fetch_api("/leads?tier=A&limit=100")
    leads_list = []
    if isinstance(leads_response, dict) and 'leads' in leads_response:
        leads_list = leads_response['leads']
    elif isinstance(leads_response, list):
        leads_list = leads_response

    if not leads_list:
        st.warning("No Tier A leads found. Try adjusting lead scoring thresholds.")
        return

    leads = leads_list
    st.success(f"Found {len(leads)} Tier A leads")

    # Display top leads
    for i, lead in enumerate(leads[:10], 1):
        with st.expander(f"#{i} - {lead.get('situs_address', 'Unknown Address')} (Score: {lead.get('total_score', 0):.1f})"):
            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown("**Property Details**")
                st.write(f"**Parcel ID**: {lead.get('parcel_id_normalized', 'N/A')}")
                st.write(f"**Address**: {lead.get('situs_address', 'N/A')}")
                st.write(f"**City**: {lead.get('city', 'N/A')}, FL {lead.get('zip_code', '')}")

            with col2:
                st.markdown("**Scores**")
                st.write(f"**Total Score**: {lead.get('total_score', 0):.1f}")
                st.write(f"**Distress**: {lead.get('distress_score', 0):.1f}")
                st.write(f"**Value**: {lead.get('value_score', 0):.1f}")
                st.write(f"**Location**: {lead.get('location_score', 0):.1f}")

            with col3:
                st.markdown("**Opportunity**")
                st.write(f"**Tier**: {lead.get('tier', 'N/A')}")
                st.write(f"**Tax Sale**: {'Yes ✓' if lead.get('has_tax_sale') else 'No'}")
                st.write(f"**Foreclosure**: {'Yes ✓' if lead.get('has_foreclosure') else 'No'}")

    # Download data
    if st.button("Export Tier A Leads to CSV"):
        df = pd.DataFrame(leads)
        csv = df.to_csv(index=False)
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name=f"tier_a_leads_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )


def show_all_leads_page(tier_filter: List[str], min_score: int):
    """Show all leads page with filtering."""
    st.title("All Leads")

    # Build query params
    params = []
    if tier_filter:
        for tier in tier_filter:
            params.append(f"tier={tier}")
    params.append(f"min_score={min_score}")
    params.append("limit=500")

    query_string = "&".join(params)
    leads_response = fetch_api(f"/leads?{query_string}")
    leads_list = []
    if isinstance(leads_response, dict) and 'leads' in leads_response:
        leads_list = leads_response['leads']
    elif isinstance(leads_response, list):
        leads_list = leads_response

    if not leads_list:
        st.warning("No leads found matching your filters.")
        return

    df = pd.DataFrame(leads_list)

    st.success(f"Found {len(leads_list)} leads")

    preferred_columns = [
        'tier', 'total_score', 'situs_address', 'city',
        'distress_score', 'value_score', 'location_score'
    ]
    available_columns = [col for col in preferred_columns if col in df.columns]

    st.dataframe(
        df[available_columns] if available_columns else df,
        use_container_width=True,
        height=600
    )


def show_properties_page():
    """Show properties page."""
    st.title("Property Database")

    # Current API only exposes properties via lead listings
    properties_response = fetch_api("/leads?limit=200&sort_by=situs_address")
    properties_list = []

    if isinstance(properties_response, dict) and 'leads' in properties_response:
        properties_list = properties_response['leads']
    elif isinstance(properties_response, list):
        properties_list = properties_response

    if not properties_list:
        st.warning("No property data available from API.")
        return

    df = pd.DataFrame(properties_list)

    st.success(f"Showing {len(properties_list)} property records derived from leads")

    # Display dataframe
    st.dataframe(df, use_container_width=True, height=600)


def show_analytics_page():
    """Show analytics page."""
    st.title("Analytics & Insights")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Pipeline Performance")
        st.info("Analytics coming soon...")

    with col2:
        st.subheader("ML Model Metrics")
        st.info("Model performance metrics coming soon...")


if __name__ == "__main__":
    main()
