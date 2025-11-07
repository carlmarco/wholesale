"""
Wholesaler Lead Management Dashboard

Main Streamlit application for viewing and managing real estate wholesale leads.
"""
import streamlit as st
from src.wholesaler.frontend.utils import APIClient

# Page configuration
st.set_page_config(
    page_title="Wholesaler Lead Management",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize API client in session state
if "api_client" not in st.session_state:
    st.session_state.api_client = APIClient()

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 1rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
    .tier-a { border-left-color: #28a745; }
    .tier-b { border-left-color: #17a2b8; }
    .tier-c { border-left-color: #ffc107; }
    .tier-d { border-left-color: #6c757d; }
</style>
""", unsafe_allow_html=True)

# Main page content
st.markdown('<div class="main-header">Wholesaler Lead Dashboard</div>', unsafe_allow_html=True)

st.markdown("""
Welcome to the Wholesaler Lead Management System. This dashboard helps you:
- View lead statistics and tier distribution
- Browse and filter real estate leads
- View detailed property information
- Explore leads on an interactive map
- Track score trends over time
""")

# Health check
try:
    health = st.session_state.api_client.health_check()
    if health["status"] == "healthy":
        st.success(f"API Connected - Version {health['version']}")
    else:
        st.warning(f"API Status: {health['status']}")
except Exception as e:
    st.error(f"Failed to connect to API: {str(e)}")
    st.info("Make sure the FastAPI server is running on http://localhost:8000")
    st.code("python -m src.wholesaler.api.main")

# Quick stats overview
st.header("Quick Overview")

try:
    stats = st.session_state.api_client.get_dashboard_stats()

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric(
            label="Total Leads",
            value=stats["total_leads"],
        )

    with col2:
        st.metric(
            label="Tier A Leads",
            value=stats["tier_a_count"],
            delta=f"{stats['recent_tier_a_count']} this week",
        )

    with col3:
        st.metric(
            label="Tier B Leads",
            value=stats["tier_b_count"],
        )

    with col4:
        st.metric(
            label="Tier C Leads",
            value=stats["tier_c_count"],
        )

    with col5:
        st.metric(
            label="Tier D Leads",
            value=stats["tier_d_count"],
        )

    # Second row of metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        avg_a = stats.get("avg_score_tier_a")
        st.metric(
            label="Avg Score (Tier A)",
            value=f"{avg_a:.1f}" if avg_a else "N/A",
        )

    with col2:
        st.metric(
            label="Total Properties",
            value=stats["total_properties"],
        )

    with col3:
        st.metric(
            label="Tax Sales",
            value=stats["properties_with_tax_sales"],
        )

    with col4:
        st.metric(
            label="Foreclosures",
            value=stats["properties_with_foreclosures"],
        )

except Exception as e:
    st.error(f"Failed to load dashboard statistics: {str(e)}")

# Navigation guide
st.header("Navigation")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Leads List")
    st.markdown("""
    Browse all leads with advanced filtering:
    - Filter by tier, score range, location
    - Sort by various criteria
    - Export to CSV
    """)

    st.subheader("Lead Detail")
    st.markdown("""
    View comprehensive lead information:
    - Property details and scoring breakdown
    - Tax sale and foreclosure info
    - Historical score trends
    """)

with col2:
    st.subheader("Map View")
    st.markdown("""
    Explore leads geographically:
    - Interactive map with tier color coding
    - Click on markers for details
    - Filter by location
    """)

    st.subheader("Reports")
    st.markdown("""
    Analyze lead data:
    - Score distribution histograms
    - Tier trend analysis
    - Custom date range reports
    """)

# Footer
st.markdown("---")
st.markdown("**Wholesaler Lead Management System v0.3.0** | Built with Streamlit + FastAPI")
