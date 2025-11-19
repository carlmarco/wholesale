"""
Chart Components

Reusable chart visualizations using Plotly.
"""
import plotly.graph_objects as go
import plotly.express as px
from typing import Dict, List, Any


def create_tier_distribution_chart(tier_counts: Dict[str, int]) -> go.Figure:
    """
    Create pie chart showing tier distribution.

    Args:
        tier_counts: Dictionary mapping tier to count

    Returns:
        Plotly figure
    """
    tiers = ["A", "B", "C", "D"]
    counts = [tier_counts.get(tier, 0) for tier in tiers]
    colors = ["#28a745", "#17a2b8", "#ffc107", "#6c757d"]

    fig = go.Figure(data=[
        go.Pie(
            labels=[f"Tier {tier}" for tier in tiers],
            values=counts,
            marker=dict(colors=colors),
            hole=0.4,
            textinfo="label+percent+value",
            textposition="auto",
        )
    ])

    fig.update_layout(
        title="Lead Distribution by Tier",
        height=400,
        showlegend=True,
    )

    return fig


def create_score_histogram(leads: List[Dict[str, Any]], tier: str = None) -> go.Figure:
    """
    Create histogram of lead scores.

    Args:
        leads: List of lead dictionaries
        tier: Optional tier filter

    Returns:
        Plotly figure
    """
    scores = [lead["total_score"] for lead in leads]

    title = f"Score Distribution - Tier {tier}" if tier else "Overall Score Distribution"

    fig = go.Figure(data=[
        go.Histogram(
            x=scores,
            nbinsx=20,
            marker=dict(color="#17a2b8", line=dict(color="white", width=1)),
        )
    ])

    fig.update_layout(
        title=title,
        xaxis_title="Total Score",
        yaxis_title="Number of Leads",
        height=400,
        showlegend=False,
    )

    return fig


def create_score_trend_chart(history: List[Dict[str, Any]]) -> go.Figure:
    """
    Create line chart showing score history over time.

    Args:
        history: List of historical score snapshots

    Returns:
        Plotly figure
    """
    # Sort by date (oldest first for chart)
    sorted_history = sorted(history, key=lambda x: x["snapshot_date"])

    dates = [h["snapshot_date"] for h in sorted_history]
    total_scores = [h["total_score"] for h in sorted_history]
    distress_scores = [h["distress_score"] for h in sorted_history]
    value_scores = [h["value_score"] for h in sorted_history]
    location_scores = [h["location_score"] for h in sorted_history]
    urgency_scores = [h["urgency_score"] for h in sorted_history]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=dates, y=total_scores,
        mode="lines+markers",
        name="Total Score",
        line=dict(color="#17a2b8", width=3),
    ))

    fig.add_trace(go.Scatter(
        x=dates, y=distress_scores,
        mode="lines",
        name="Distress Score",
        line=dict(color="#dc3545", width=1, dash="dot"),
    ))

    fig.add_trace(go.Scatter(
        x=dates, y=value_scores,
        mode="lines",
        name="Value Score",
        line=dict(color="#28a745", width=1, dash="dot"),
    ))

    fig.add_trace(go.Scatter(
        x=dates, y=location_scores,
        mode="lines",
        name="Location Score",
        line=dict(color="#ffc107", width=1, dash="dot"),
    ))

    fig.add_trace(go.Scatter(
        x=dates, y=urgency_scores,
        mode="lines",
        name="Urgency Score",
        line=dict(color="#6c757d", width=1, dash="dot"),
    ))

    fig.update_layout(
        title="Score History",
        xaxis_title="Date",
        yaxis_title="Score",
        height=400,
        hovermode="x unified",
    )

    return fig


def create_score_breakdown_chart(lead: Dict[str, Any]) -> go.Figure:
    """
    Create horizontal bar chart showing score component breakdown.

    Args:
        lead: Lead dictionary with score components

    Returns:
        Plotly figure
    """
    categories = ["Distress", "Value", "Location", "Urgency"]
    scores = [
        lead["distress_score"],
        lead["value_score"],
        lead["location_score"],
        lead["urgency_score"],
    ]
    colors = ["#dc3545", "#28a745", "#ffc107", "#6c757d"]

    fig = go.Figure(data=[
        go.Bar(
            y=categories,
            x=scores,
            orientation="h",
            marker=dict(color=colors),
            text=[f"{s:.1f}" for s in scores],
            textposition="auto",
        )
    ])

    fig.update_layout(
        title=f"Score Breakdown (Total: {lead['total_score']:.1f})",
        xaxis_title="Score",
        xaxis=dict(range=[0, 100]),
        height=300,
        showlegend=False,
    )

    return fig


def create_avg_score_by_tier_chart(avg_scores: Dict[str, float]) -> go.Figure:
    """
    Create bar chart showing average scores by tier.

    Args:
        avg_scores: Dictionary mapping tier to average score

    Returns:
        Plotly figure
    """
    tiers = ["A", "B", "C", "D"]
    scores = [avg_scores.get(tier, 0) for tier in tiers]
    colors = ["#28a745", "#17a2b8", "#ffc107", "#6c757d"]

    fig = go.Figure(data=[
        go.Bar(
            x=[f"Tier {tier}" for tier in tiers],
            y=scores,
            marker=dict(color=colors),
            text=[f"{s:.1f}" for s in scores],
            textposition="auto",
        )
    ])

    fig.update_layout(
        title="Average Score by Tier",
        xaxis_title="Tier",
        yaxis_title="Average Total Score",
        yaxis=dict(range=[0, 100]),
        height=400,
        showlegend=False,
    )

    return fig
