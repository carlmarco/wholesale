"""
Graph feature builder for property relationships.
"""
import networkx as nx
import pandas as pd
from typing import Dict, List

class PropertyGraphBuilder:
    """
    Builds a graph where nodes are properties and edges represent relationships
    (Same Owner, Geographic Proximity).
    """
    
    def __init__(self):
        self.graph = nx.Graph()
        
    def build_graph(self, properties: List[Dict]):
        """
        Build graph from list of property records.
        """
        # Add nodes
        for p in properties:
            pid = p.get("parcel_id_normalized")
            if pid:
                self.graph.add_node(pid, **p)
                
        # Add edges: Same Owner
        # This is O(N^2) naively, need optimization for large datasets.
        # Better: Group by owner, then connect all in group.
        df = pd.DataFrame(properties)
        if "owner_name" in df.columns:
            owner_groups = df.groupby("owner_name")
            for owner, group in owner_groups:
                if len(group) > 1:
                    # Connect all to a virtual owner node or clique?
                    # Clique is expensive. Let's just add a 'portfolio_size' feature to nodes instead of explicit edges?
                    # Or connect them linearly.
                    # For now, let's just compute portfolio metrics directly.
                    pass
                    
    def compute_graph_features(self, properties: List[Dict]) -> pd.DataFrame:
        """
        Compute graph-based features without fully materializing the graph if possible.
        """
        df = pd.DataFrame(properties)
        features = pd.DataFrame(index=df.index)
        
        if "owner_name" in df.columns:
            # Portfolio Size
            portfolio_sizes = df["owner_name"].value_counts()
            features["owner_portfolio_size"] = df["owner_name"].map(portfolio_sizes).fillna(1)
            
            # Portfolio Distress Rate
            # If any property in portfolio has violation, does it taint others?
            if "violation_count" in df.columns:
                df["has_violation"] = df["violation_count"] > 0
                owner_distress = df.groupby("owner_name")["has_violation"].mean()
                features["owner_portfolio_distress_rate"] = df["owner_name"].map(owner_distress).fillna(0)
                
        return features
