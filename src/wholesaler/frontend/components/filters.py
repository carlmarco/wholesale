"""
Filter Components

Reusable filter widgets for lead filtering.
"""
import streamlit as st
from typing import Dict, Any


def render_lead_filters() -> Dict[str, Any]:
    """
    Render lead filter sidebar.

    Returns:
        Dictionary of selected filter values
    """
    st.sidebar.header("Filters")

    filters = {}

    # Tier filter
    tier_options = ["All", "A", "B", "C", "D"]
    selected_tier = st.sidebar.selectbox("Tier", tier_options, index=0)
    if selected_tier != "All":
        filters["tier"] = selected_tier

    # Score range filter
    st.sidebar.subheader("Score Range")
    score_range = st.sidebar.slider(
        "Total Score",
        min_value=0.0,
        max_value=100.0,
        value=(0.0, 100.0),
        step=5.0,
    )
    if score_range != (0.0, 100.0):
        filters["min_score"] = score_range[0]
        filters["max_score"] = score_range[1]

    # Location filters
    st.sidebar.subheader("Location")
    city = st.sidebar.text_input("City", "")
    if city:
        filters["city"] = city

    zip_code = st.sidebar.text_input("ZIP Code", "")
    if zip_code:
        filters["zip_code"] = zip_code

    # View toggle
    st.sidebar.subheader("Scoring View")
    view_option = st.sidebar.radio(
        "Select score view",
        options=[
            "Hybrid + Priority (recommended)",
            "Legacy heuristic only",
        ],
        index=0,
    )
    filters["view"] = "hybrid" if view_option.startswith("Hybrid") else "legacy"

    # Sort options
    st.sidebar.subheader("Sort By")
    sort_options = {
        "Total Score (High to Low)": ("total_score", "desc"),
        "Total Score (Low to High)": ("total_score", "asc"),
        "Date Scored (Newest First)": ("scored_at", "desc"),
        "Date Scored (Oldest First)": ("scored_at", "asc"),
        "Address (A-Z)": ("situs_address", "asc"),
        "Address (Z-A)": ("situs_address", "desc"),
    }
    selected_sort = st.sidebar.selectbox(
        "Sort",
        list(sort_options.keys()),
        index=0,
    )
    filters["sort_by"], filters["sort_order"] = sort_options[selected_sort]

    return filters


def render_pagination_controls(total_count: int, page_size: int = 50) -> Dict[str, int]:
    """
    Render pagination controls.

    Args:
        total_count: Total number of items
        page_size: Items per page

    Returns:
        Dictionary with limit and offset values
    """
    total_pages = (total_count + page_size - 1) // page_size

    if total_pages <= 1:
        return {"limit": page_size, "offset": 0}

    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        if st.button(" Previous", disabled=st.session_state.get("current_page", 1) == 1):
            st.session_state.current_page = max(1, st.session_state.get("current_page", 1) - 1)

    with col2:
        current_page = st.number_input(
            f"Page (1-{total_pages})",
            min_value=1,
            max_value=total_pages,
            value=st.session_state.get("current_page", 1),
            key="page_input",
        )
        st.session_state.current_page = current_page

    with col3:
        if st.button("Next ", disabled=st.session_state.get("current_page", 1) == total_pages):
            st.session_state.current_page = min(total_pages, st.session_state.get("current_page", 1) + 1)

    offset = (st.session_state.get("current_page", 1) - 1) * page_size

    return {"limit": page_size, "offset": offset}
