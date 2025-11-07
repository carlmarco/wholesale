"""
Reports Page

Analyze lead data with various charts and reports.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

import streamlit as st

from src.wholesaler.frontend.utils import APIClient
from src.wholesaler.frontend.components.charts import (
    create_tier_distribution_chart,
    create_score_histogram,
    create_avg_score_by_tier_chart,
)

# Page configuration
st.set_page_config(
    page_title="Reports - Wholesaler",
    page_icon="",
    layout="wide",
)

# Initialize API client
if "api_client" not in st.session_state:
    st.session_state.api_client = APIClient()

# Page header
st.title(" Reports & Analytics")
st.markdown("Analyze lead data with interactive charts and statistics.")

# Fetch dashboard stats
try:
    with st.spinner("Loading statistics..."):
        stats = st.session_state.api_client.get_dashboard_stats()

    # Overview metrics
    st.header(" Overview")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="Total Leads",
            value=stats["total_leads"],
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

    # Tier distribution
    st.markdown("---")
    st.header(" Tier Distribution")

    tier_counts = {
        "A": stats["tier_a_count"],
        "B": stats["tier_b_count"],
        "C": stats["tier_c_count"],
        "D": stats["tier_d_count"],
    }

    col1, col2 = st.columns([2, 1])

    with col1:
        fig = create_tier_distribution_chart(tier_counts)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Tier Breakdown")

        total = sum(tier_counts.values())
        if total > 0:
            for tier, count in tier_counts.items():
                percentage = (count / total) * 100
                st.metric(
                    label=f"Tier {tier}",
                    value=count,
                    delta=f"{percentage:.1f}%",
                )
        else:
            st.info("No leads available for analysis.")

    # Average scores by tier
    st.markdown("---")
    st.header(" Average Scores by Tier")

    avg_scores = {}
    if stats.get("avg_score_tier_a"):
        avg_scores["A"] = stats["avg_score_tier_a"]
    if stats.get("avg_score_tier_b"):
        avg_scores["B"] = stats["avg_score_tier_b"]
    if stats.get("avg_score_tier_c"):
        avg_scores["C"] = stats["avg_score_tier_c"]
    if stats.get("avg_score_tier_d"):
        avg_scores["D"] = stats["avg_score_tier_d"]

    if avg_scores:
        col1, col2 = st.columns([2, 1])

        with col1:
            fig = create_avg_score_by_tier_chart(avg_scores)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.subheader("Score Details")

            for tier, avg_score in avg_scores.items():
                st.metric(
                    label=f"Tier {tier} Average",
                    value=f"{avg_score:.1f}",
                )

    # Score distribution by tier
    st.markdown("---")
    st.header(" Score Distribution Analysis")

    selected_tier = st.selectbox(
        "Select Tier for Score Distribution",
        ["All Tiers", "Tier A", "Tier B", "Tier C", "Tier D"],
    )

    tier_filter = None
    if selected_tier != "All Tiers":
        tier_filter = selected_tier.split()[-1]  # Extract "A", "B", etc.

    try:
        with st.spinner("Loading lead data..."):
            if tier_filter:
                leads = st.session_state.api_client.list_leads(tier=tier_filter, limit=1000)
            else:
                leads = st.session_state.api_client.list_leads(limit=1000)

        if leads:
            fig = create_score_histogram(leads, tier=tier_filter)
            st.plotly_chart(fig, use_container_width=True)

            # Statistical summary
            col1, col2, col3, col4 = st.columns(4)

            scores = [lead["total_score"] for lead in leads]
            import statistics

            with col1:
                st.metric("Count", len(scores))

            with col2:
                st.metric("Mean", f"{statistics.mean(scores):.1f}")

            with col3:
                st.metric("Median", f"{statistics.median(scores):.1f}")

            with col4:
                st.metric("Std Dev", f"{statistics.stdev(scores) if len(scores) > 1 else 0:.1f}")

        else:
            st.info(f"No leads found for {selected_tier}")

    except Exception as e:
        st.error(f"Failed to load score distribution: {str(e)}")

    # Recent activity
    st.markdown("---")
    st.header(" Recent Activity")

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            label="New Tier A Leads (Last 7 Days)",
            value=stats["recent_tier_a_count"],
        )

    with col2:
        if stats["tier_a_count"] > 0:
            percentage = (stats["recent_tier_a_count"] / stats["tier_a_count"]) * 100
            st.metric(
                label="% of Total Tier A",
                value=f"{percentage:.1f}%",
            )

    # Data quality metrics
    st.markdown("---")
    st.header(" Data Quality Metrics")

    col1, col2, col3 = st.columns(3)

    with col1:
        if stats["total_properties"] > 0:
            tax_sale_percentage = (stats["properties_with_tax_sales"] / stats["total_properties"]) * 100
            st.metric(
                label="Properties with Tax Sales",
                value=f"{tax_sale_percentage:.1f}%",
                delta=f"{stats['properties_with_tax_sales']} total",
            )

    with col2:
        if stats["total_properties"] > 0:
            foreclosure_percentage = (stats["properties_with_foreclosures"] / stats["total_properties"]) * 100
            st.metric(
                label="Properties with Foreclosures",
                value=f"{foreclosure_percentage:.1f}%",
                delta=f"{stats['properties_with_foreclosures']} total",
            )

    with col3:
        if stats["total_properties"] > 0:
            scored_percentage = (stats["total_leads"] / stats["total_properties"]) * 100
            st.metric(
                label="Properties Scored",
                value=f"{scored_percentage:.1f}%",
                delta=f"{stats['total_leads']} total",
            )

    # Action buttons
    st.markdown("---")
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button(" View Leads List"):
            st.switch_page("pages/1__Leads_List.py")

    with col2:
        if st.button(" View Map"):
            st.switch_page("pages/3__Map_View.py")

    with col3:
        if st.button(" Refresh Data"):
            st.rerun()

except Exception as e:
    st.error(f"Failed to load reports: {str(e)}")
    st.info("Make sure the FastAPI server is running on http://localhost:8000")

# Footer
st.markdown("---")
st.markdown(" **Tip:** Use these reports to identify trends and prioritize high-value leads.")
