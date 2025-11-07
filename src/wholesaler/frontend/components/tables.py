"""
Table Components

Reusable table displays for leads and properties.
"""
import streamlit as st
import pandas as pd
from typing import List, Dict, Any

from src.wholesaler.frontend.utils.formatting import (
    format_score,
    format_date,
    format_currency,
    get_tier_color,
)


def render_leads_table(leads: List[Dict[str, Any]]) -> None:
    """
    Render interactive leads table.

    Args:
        leads: List of lead dictionaries
    """
    if not leads:
        st.info("No leads found matching the selected filters.")
        return

    # Convert to DataFrame
    df_data = []
    for lead in leads:
        property_data = lead.get("property", {})
        df_data.append({
            "Tier": lead["tier"],
            "Score": lead["total_score"],
            "Address": property_data.get("situs_address", "N/A"),
            "City": property_data.get("city", "N/A"),
            "ZIP": property_data.get("zip_code", "N/A"),
            "Distress": lead["distress_score"],
            "Value": lead["value_score"],
            "Location": lead["location_score"],
            "Urgency": lead["urgency_score"],
            "Parcel ID": lead["parcel_id_normalized"],
        })

    df = pd.DataFrame(df_data)

    # Style DataFrame
    def style_tier(val):
        """Style tier cells with color."""
        color = get_tier_color(val)
        return f"background-color: {color}; color: white; font-weight: bold; text-align: center;"

    def style_score(val):
        """Style score cells with gradient."""
        if val >= 80:
            return "background-color: #d4edda; color: #155724;"
        elif val >= 60:
            return "background-color: #d1ecf1; color: #0c5460;"
        elif val >= 40:
            return "background-color: #fff3cd; color: #856404;"
        else:
            return "background-color: #f8d7da; color: #721c24;"

    styled_df = df.style.applymap(
        style_tier,
        subset=["Tier"]
    ).applymap(
        style_score,
        subset=["Score", "Distress", "Value", "Location", "Urgency"]
    ).format({
        "Score": "{:.1f}",
        "Distress": "{:.1f}",
        "Value": "{:.1f}",
        "Location": "{:.1f}",
        "Urgency": "{:.1f}",
    })

    st.dataframe(styled_df, use_container_width=True, height=600)

    # Export button
    csv = df.to_csv(index=False)
    st.download_button(
        label="Download CSV",
        data=csv,
        file_name="leads_export.csv",
        mime="text/csv",
    )


def render_property_details_table(lead: Dict[str, Any]) -> None:
    """
    Render property details table.

    Args:
        lead: Lead dictionary with property info
    """
    property_data = lead.get("property", {})

    details = {
        "Parcel ID": property_data.get("parcel_id_normalized", "N/A"),
        "Original Parcel ID": property_data.get("parcel_id_original", "N/A"),
        "Address": property_data.get("situs_address", "N/A"),
        "City": property_data.get("city", "N/A"),
        "State": property_data.get("state", "N/A"),
        "ZIP Code": property_data.get("zip_code", "N/A"),
        "County": property_data.get("county", "N/A"),
        "Property Use": property_data.get("property_use", "N/A"),
        "Latitude": property_data.get("latitude", "N/A"),
        "Longitude": property_data.get("longitude", "N/A"),
    }

    df = pd.DataFrame(list(details.items()), columns=["Field", "Value"])
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_tax_sale_table(lead: Dict[str, Any]) -> None:
    """
    Render tax sale information table.

    Args:
        lead: Lead dictionary with tax sale info
    """
    tax_sale = lead.get("tax_sale")

    if not tax_sale:
        st.info("No tax sale information available.")
        return

    details = {
        "TDA Number": tax_sale.get("tda_number", "N/A"),
        "Sale Date": format_date(tax_sale.get("sale_date")),
        "Deed Status": tax_sale.get("deed_status", "N/A"),
        "Opening Bid": format_currency(tax_sale.get("opening_bid")),
    }

    df = pd.DataFrame(list(details.items()), columns=["Field", "Value"])
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_foreclosure_table(lead: Dict[str, Any]) -> None:
    """
    Render foreclosure information table.

    Args:
        lead: Lead dictionary with foreclosure info
    """
    foreclosure = lead.get("foreclosure")

    if not foreclosure:
        st.info("No foreclosure information available.")
        return

    details = {
        "Case Number": foreclosure.get("case_number", "N/A"),
        "Filing Date": format_date(foreclosure.get("filing_date")),
        "Auction Date": format_date(foreclosure.get("auction_date")),
        "Judgment Amount": format_currency(foreclosure.get("judgment_amount")),
        "Status": foreclosure.get("foreclosure_status", "N/A"),
    }

    df = pd.DataFrame(list(details.items()), columns=["Field", "Value"])
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_scoring_reasons_table(lead: Dict[str, Any]) -> None:
    """
    Render scoring reasons list.

    Args:
        lead: Lead dictionary with scoring reasons
    """
    reasons = lead.get("scoring_reasons", [])

    if not reasons:
        st.info("No specific scoring reasons recorded.")
        return

    for i, reason in enumerate(reasons, 1):
        st.markdown(f"{i}. {reason}")
