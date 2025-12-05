from collections import deque
import time
import torch
import numpy as np
from ControlLoops.Explainability import ExplainabilityLayer
from Safe_RL.CQL_Training import QNetwork
from Safe_RL.Testing import greedy_action_from_q
import os

class FastLoop():
    def __init__(self, interval=5):
        self.interval = interval
        self.queue = deque()
        self.isRunning = True
        self.explainer = ExplainabilityLayer()
        
        # Load Safe RL Model (Lightweight usage)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.q_net = QNetwork(state_dim=14, action_dim=9).to(self.device)
        
        model_path = os.path.join("Safe RL", "cql_q1.pt")
        if os.path.exists(model_path):
            try:
                self.q_net.load_state_dict(torch.load(model_path, map_location=self.device))
                self.q_net.eval()
                print("[FastLoop] Safe RL Model Loaded.")
            except Exception as e:
                print(f"[FastLoop] Failed to load RL model: {e}")
        else:
            print(f"[FastLoop] Warning: RL model not found at {model_path}")

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(FastLoop, cls).__new__(cls)
        return cls._instance

    def start(self):
        while (self.isRunning):
            time.sleep(self.interval)
            self.processChange()

    def addChange(self, change):
        self.queue.append(change)

    def processChange(self):
        while self.queue:
            change = self.queue.popleft()
            change_type = change.get("type")
            value = change.get("value")
            
            print(f"[FASTLOOP] Processing Change: {change_type} Value: {value}")
            
            # Reactive Logic
            if change_type == "SNR" and value < 10:
                self.handle_snr_drop(change)
            elif change_type == "Interference" or change_type == "NWIFI_DETECTED":
                self.handle_interference(change)
            elif change_type == "DFS":
                self.handle_dfs(change)
            else:
                # Log generic event
                 self.explainer.log_decision(
                    component="FastLoop",
                    trigger=f"Event_{change_type}",
                    decision="Monitor",
                    reason_code="Threshold_Not_Met",
                    details=change
                )

    def handle_snr_drop(self, change):
        # Query RL for quick fix (e.g., increase power)
        # Dummy state
        state = np.random.rand(14).astype(np.float32)
        action, q_val = greedy_action_from_q(self.q_net, state, n_samples=100)
        
        self.explainer.log_decision(
            component="FastLoop",
            trigger="LowSNR",
            decision="Increase_Tx_Power",
            reason_code="RL_Policy_Reactive",
            details={"new_config": action.tolist(), "q_val": q_val},
            confidence=0.85
        )

    def handle_interference(self, change):
        # Heuristic: Switch channel or narrow width
        self.explainer.log_decision(
            component="FastLoop",
            trigger="InterferenceSpike",
            decision="Narrow_Bandwidth",
            reason_code="Interference_Mitigation",
            details=change
        )

    def handle_dfs(self, change):
        # Regulatory requirement: Must switch immediately
        self.explainer.log_decision(
            component="FastLoop",
            trigger="DFS_Radar",
            decision="Switch_Channel_Immediately",
            reason_code="Regulatory_Compliance",
            details=change
        )
