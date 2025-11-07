"""
Leads List Page

Browse and filter lead scores with advanced filtering options.
"""
import streamlit as st

from src.wholesaler.frontend.utils import APIClient
from src.wholesaler.frontend.components.filters import render_lead_filters
from src.wholesaler.frontend.components.tables import render_leads_table
from src.wholesaler.frontend.components.charts import create_tier_distribution_chart

# Page configuration
st.set_page_config(
    page_title="Leads List - Wholesaler",
    page_icon="",
    layout="wide",
)

# Initialize API client
if "api_client" not in st.session_state:
    st.session_state.api_client = APIClient()

# Page header
st.title(" Leads List")
st.markdown("Browse and filter real estate wholesale leads by tier, score, and location.")

# Render filters in sidebar
filters = render_lead_filters()

# Pagination settings
PAGE_SIZE = 50
if "current_page" not in st.session_state:
    st.session_state.current_page = 1

# Calculate offset
offset = (st.session_state.current_page - 1) * PAGE_SIZE

# Fetch leads
try:
    with st.spinner("Loading leads..."):
        leads = st.session_state.api_client.list_leads(
            **filters,
            limit=PAGE_SIZE,
            offset=offset,
        )

    # Display summary
    col1, col2 = st.columns([3, 1])

    with col1:
        st.subheader(f"Found {len(leads)} leads")
        if filters:
            active_filters = []
            if "tier" in filters:
                active_filters.append(f"Tier: {filters['tier']}")
            if "min_score" in filters or "max_score" in filters:
                min_s = filters.get("min_score", 0)
                max_s = filters.get("max_score", 100)
                active_filters.append(f"Score: {min_s}-{max_s}")
            if "city" in filters:
                active_filters.append(f"City: {filters['city']}")
            if "zip_code" in filters:
                active_filters.append(f"ZIP: {filters['zip_code']}")

            if active_filters:
                st.info("Active filters: " + " | ".join(active_filters))

    with col2:
        if st.button(" Refresh"):
            st.rerun()

    # Display leads table
    if leads:
        # Tier distribution chart for current results
        tier_counts = {}
        for lead in leads:
            tier = lead["tier"]
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

        with st.expander(" View Tier Distribution for Current Results", expanded=False):
            fig = create_tier_distribution_chart(tier_counts)
            st.plotly_chart(fig, use_container_width=True)

        # Render table
        render_leads_table(leads)

        # Pagination info
        st.markdown(f"**Page {st.session_state.current_page}** | Showing {len(leads)} leads")

        # Pagination controls
        col1, col2, col3 = st.columns([1, 2, 1])

        with col1:
            if st.button(" Previous", disabled=st.session_state.current_page == 1):
                st.session_state.current_page -= 1
                st.rerun()

        with col2:
            st.markdown(f"<div style='text-align: center;'>Page {st.session_state.current_page}</div>", unsafe_allow_html=True)

        with col3:
            if st.button("Next ", disabled=len(leads) < PAGE_SIZE):
                st.session_state.current_page += 1
                st.rerun()

    else:
        st.info("No leads found matching the selected filters. Try adjusting your filter criteria.")

        # Reset filters button
        if st.button("Clear All Filters"):
            st.session_state.current_page = 1
            st.rerun()

except Exception as e:
    st.error(f"Failed to load leads: {str(e)}")
    st.info("Make sure the FastAPI server is running on http://localhost:8000")

# Footer
st.markdown("---")
st.markdown(" **Tip:** Use the sidebar to filter leads by tier, score range, or location.")
