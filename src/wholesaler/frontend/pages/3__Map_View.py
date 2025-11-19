"""
Map View Page

Interactive map visualization of leads with tier-based color coding.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

import streamlit as st
import pandas as pd
import pydeck as pdk

from src.wholesaler.frontend.utils import APIClient, get_tier_color
from src.wholesaler.frontend.components.filters import render_lead_filters

# Page configuration
st.set_page_config(
    page_title="Map View - Wholesaler",
    page_icon="",
    layout="wide",
)

# Initialize API client
if "api_client" not in st.session_state:
    st.session_state.api_client = APIClient()

# Page header
st.title(" Map View")
st.markdown("Explore leads geographically with interactive map visualization.")

# Render filters in sidebar
filters = render_lead_filters()

# Map settings
st.sidebar.markdown("---")
st.sidebar.subheader("Map Settings")
show_labels = st.sidebar.checkbox("Show Address Labels", value=False)
map_style = st.sidebar.selectbox(
    "Map Style",
    ["mapbox://styles/mapbox/streets-v11", "mapbox://styles/mapbox/satellite-streets-v11", "mapbox://styles/mapbox/light-v10", "mapbox://styles/mapbox/dark-v10"],
    index=0,
)

# Fetch leads
try:
    with st.spinner("Loading leads..."):
        # Get more leads for map view (up to 500)
        leads = st.session_state.api_client.list_leads(
            **filters,
            limit=500,
            offset=0,
        )

    # Filter leads with valid coordinates
    leads_with_coords = [
        lead for lead in leads
        if lead.get("property", {}).get("latitude") and lead.get("property", {}).get("longitude")
    ]

    st.info(f"Showing {len(leads_with_coords)} leads on map (out of {len(leads)} total)")

    if not leads_with_coords:
        st.warning("No leads with valid coordinates found. Adjust filters or check data quality.")
    else:
        # Prepare data for map
        map_data = []
        for lead in leads_with_coords:
            property_data = lead.get("property", {})

            # Get tier color (convert hex to RGB)
            tier = lead["tier"]
            hex_color = get_tier_color(tier).lstrip("#")
            rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

            map_data.append({
                "parcel_id": lead["parcel_id_normalized"],
                "latitude": property_data["latitude"],
                "longitude": property_data["longitude"],
                "address": property_data.get("situs_address", "N/A"),
                "city": property_data.get("city", "N/A"),
                "tier": tier,
                "score": lead["total_score"],
                "color": list(rgb) + [200],  # Add alpha channel
            })

        df = pd.DataFrame(map_data)

        # Calculate center point
        center_lat = df["latitude"].mean()
        center_lon = df["longitude"].mean()

        # Create pydeck layer
        layer = pdk.Layer(
            "ScatterplotLayer",
            data=df,
            get_position=["longitude", "latitude"],
            get_color="color",
            get_radius=100,
            pickable=True,
            opacity=0.8,
            stroked=True,
            filled=True,
            radius_scale=1,
            radius_min_pixels=5,
            radius_max_pixels=30,
            line_width_min_pixels=1,
        )

        # Set tooltip
        tooltip = {
            "html": "<b>{address}</b><br/>"
                    "{city}<br/>"
                    "Tier: <b>{tier}</b><br/>"
                    "Score: <b>{score:.1f}</b><br/>"
                    "Parcel ID: {parcel_id}",
            "style": {
                "backgroundColor": "steelblue",
                "color": "white",
                "fontSize": "14px",
                "padding": "10px",
            }
        }

        # Create deck
        view_state = pdk.ViewState(
            latitude=center_lat,
            longitude=center_lon,
            zoom=11,
            pitch=0,
        )

        deck = pdk.Deck(
            layers=[layer],
            initial_view_state=view_state,
            tooltip=tooltip,
            map_style=map_style,
        )

        # Render map
        st.pydeck_chart(deck)

        # Legend
        st.markdown("---")
        st.subheader(" Legend")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.markdown(
                f"""
                <div style='background-color: {get_tier_color('A')};
                            color: white;
                            padding: 0.5rem;
                            border-radius: 0.25rem;
                            text-align: center;'>
                    <b>Tier A</b><br/>Highest Priority
                </div>
                """,
                unsafe_allow_html=True
            )

        with col2:
            st.markdown(
                f"""
                <div style='background-color: {get_tier_color('B')};
                            color: white;
                            padding: 0.5rem;
                            border-radius: 0.25rem;
                            text-align: center;'>
                    <b>Tier B</b><br/>High Priority
                </div>
                """,
                unsafe_allow_html=True
            )

        with col3:
            st.markdown(
                f"""
                <div style='background-color: {get_tier_color('C')};
                            color: white;
                            padding: 0.5rem;
                            border-radius: 0.25rem;
                            text-align: center;'>
                    <b>Tier C</b><br/>Medium Priority
                </div>
                """,
                unsafe_allow_html=True
            )

        with col4:
            st.markdown(
                f"""
                <div style='background-color: {get_tier_color('D')};
                            color: white;
                            padding: 0.5rem;
                            border-radius: 0.25rem;
                            text-align: center;'>
                    <b>Tier D</b><br/>Low Priority
                </div>
                """,
                unsafe_allow_html=True
            )

        # Summary statistics by tier
        st.markdown("---")
        st.subheader(" Geographic Distribution")

        tier_counts = df["tier"].value_counts().to_dict()

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Tier A on Map", tier_counts.get("A", 0))

        with col2:
            st.metric("Tier B on Map", tier_counts.get("B", 0))

        with col3:
            st.metric("Tier C on Map", tier_counts.get("C", 0))

        with col4:
            st.metric("Tier D on Map", tier_counts.get("D", 0))

except Exception as e:
    st.error(f"Failed to load map data: {str(e)}")
    st.info("Make sure the FastAPI server is running on http://localhost:8000")

# Footer
st.markdown("---")
st.markdown(" **Tip:** Click on map markers to see lead details. Use filters in the sidebar to focus on specific areas or tiers.")
