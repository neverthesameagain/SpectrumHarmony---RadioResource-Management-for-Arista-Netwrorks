import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
import os
import logging

class CausalAnalysis:
    def __init__(self, data_path="causal_inference_data.csv"):
        self.data_path = data_path
        self.model_tau = None
        self.is_trained = False
        
    def load_data(self):
        if not os.path.exists(self.data_path):
            print(f"Warning: Data file {self.data_path} not found.")
            return None
        return pd.read_csv(self.data_path)

    def train_uplift_model(self):
        """
        Trains a T-Learner (Two-Model) approach for CATE estimation.
        Treatment: RRM Intervention (binary proxy or continuous)
        Outcome: QoE Improvement
        """
        df = self.load_data()
        if df is None or len(df) < 50:
            print("Insufficient data for causal inference training.")
            return

        # Preprocessing (Simplified for demo)
        # Assuming 'treatment' column exists (1 if RRM changed config, 0 otherwise)
        # If not, we infer it from config changes
        if 'treatment' not in df.columns:
            # Synthetic treatment for demo if missing
            df['treatment'] = np.random.randint(0, 2, size=len(df))
            
        # Features
        feature_cols = ['rssi', 'snr', 'load_pct', 'interference_level']
        # Ensure cols exist
        for c in feature_cols:
            if c not in df.columns:
                df[c] = 0.0
                
        X = df[feature_cols]
        y = df['qoe'] # Outcome
        t = df['treatment']

        # T-Learner: Train two models
        # Model 0: Control group (t=0)
        # Model 1: Treatment group (t=1)
        
        X0 = X[t == 0]
        y0 = y[t == 0]
        X1 = X[t == 1]
        y1 = y[t == 1]
        
        if len(X0) < 10 or len(X1) < 10:
             print("Insufficient treatment/control samples.")
             return

        self.m0 = RandomForestRegressor(n_estimators=50, max_depth=5)
        self.m0.fit(X0, y0)
        
        self.m1 = RandomForestRegressor(n_estimators=50, max_depth=5)
        self.m1.fit(X1, y1)
        
        self.is_trained = True
        print("Causal Uplift Model Trained (T-Learner).")

    def estimate_uplift(self, context_dict):
        """
        Estimates the CATE (Conditional Average Treatment Effect) for a given context.
        Returns: Predicted QoE improvement if intervention is applied.
        """
        if not self.is_trained:
            return 0.0 # Default neutral
            
        # Convert context to dataframe row
        X_new = pd.DataFrame([context_dict])
        
        # Predict outcome under treatment and control
        y1_pred = self.m1.predict(X_new)[0]
        y0_pred = self.m0.predict(X_new)[0]
        
        uplift = y1_pred - y0_pred
        return uplift

    def get_confidence_score(self, context_dict):
        """
        Returns a confidence score (0-1) for applying RRM intervention.
        """
        uplift = self.estimate_uplift(context_dict)
        # Sigmoid-like mapping: if uplift > 0.5 (e.g. 0.5 QoE points), high confidence
        confidence = 1 / (1 + np.exp(-(uplift - 0.2) * 5))
        return float(confidence)
