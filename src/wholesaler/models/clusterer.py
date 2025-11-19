"""
Unsupervised clustering for property segmentation.
"""
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from typing import Dict, Any, Tuple
import joblib
import os

class PropertyClusterer:
    """
    Clusters properties based on features to identify segments (e.g. "High Distress", "Stable").
    """
    
    def __init__(self, n_clusters: int = 5):
        self.n_clusters = n_clusters
        self.scaler = StandardScaler()
        self.pca = PCA(n_components=0.95) # Keep 95% variance
        self.kmeans = KMeans(n_clusters=n_clusters, random_state=42)
        self.is_fitted = False
        
    def fit(self, df: pd.DataFrame):
        """Fit the clustering model."""
        X = df.select_dtypes(include=[np.number]).fillna(0)
        
        X_scaled = self.scaler.fit_transform(X)
        X_pca = self.pca.fit_transform(X_scaled)
        self.kmeans.fit(X_pca)
        
        self.is_fitted = True
        
    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Predict cluster labels."""
        if not self.is_fitted:
            raise ValueError("Model not fitted")
            
        X = df.select_dtypes(include=[np.number]).fillna(0)
        X_scaled = self.scaler.transform(X)
        X_pca = self.pca.transform(X_scaled)
        
        return self.kmeans.predict(X_pca)
        
    def save(self, path: str):
        """Save model artifacts."""
        os.makedirs(path, exist_ok=True)
        joblib.dump(self.scaler, f"{path}/scaler.joblib")
        joblib.dump(self.pca, f"{path}/pca.joblib")
        joblib.dump(self.kmeans, f"{path}/kmeans.joblib")
        
    def load(self, path: str):
        """Load model artifacts."""
        self.scaler = joblib.load(f"{path}/scaler.joblib")
        self.pca = joblib.load(f"{path}/pca.joblib")
        self.kmeans = joblib.load(f"{path}/kmeans.joblib")
        self.is_fitted = True
