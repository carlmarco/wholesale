"""
Anomaly detection for identifying outliers (potential hidden gems or data errors).
"""
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import joblib
import os

class AnomalyDetector:
    """
    Identifies anomalous properties using Isolation Forest.
    """
    
    def __init__(self, contamination: float = 0.05):
        self.contamination = contamination
        self.scaler = StandardScaler()
        self.model = IsolationForest(contamination=contamination, random_state=42)
        self.is_fitted = False
        
    def fit(self, df: pd.DataFrame):
        """Fit the anomaly detector."""
        X = df.select_dtypes(include=[np.number]).fillna(0)
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled)
        self.is_fitted = True
        
    def score(self, df: pd.DataFrame) -> np.ndarray:
        """
        Return anomaly scores.
        Lower scores = more anomalous.
        """
        if not self.is_fitted:
            raise ValueError("Model not fitted")
            
        X = df.select_dtypes(include=[np.number]).fillna(0)
        X_scaled = self.scaler.transform(X)
        
        # decision_function returns negative for outliers, positive for inliers
        # We invert it so higher = more anomalous for easier interpretation?
        # Standard: negative = anomaly.
        # Let's return raw decision function.
        return self.model.decision_function(X_scaled)
        
    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Return -1 for anomaly, 1 for normal."""
        if not self.is_fitted:
            raise ValueError("Model not fitted")
            
        X = df.select_dtypes(include=[np.number]).fillna(0)
        X_scaled = self.scaler.transform(X)
        return self.model.predict(X_scaled)

    def save(self, path: str):
        os.makedirs(path, exist_ok=True)
        joblib.dump(self.scaler, f"{path}/ad_scaler.joblib")
        joblib.dump(self.model, f"{path}/ad_model.joblib")
        
    def load(self, path: str):
        self.scaler = joblib.load(f"{path}/ad_scaler.joblib")
        self.model = joblib.load(f"{path}/ad_model.joblib")
        self.is_fitted = True
