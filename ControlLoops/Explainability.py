import json
import logging
from datetime import datetime
import os

# Ensure logs directory exists
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Configure structured logger
logger = logging.getLogger("RRM_Explainability")
logger.setLevel(logging.INFO)
handler = logging.FileHandler(os.path.join(LOG_DIR, "decision_audit_trail.jsonl"))
formatter = logging.Formatter('%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

class ExplainabilityLayer:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ExplainabilityLayer, cls).__new__(cls)
        return cls._instance

    def log_decision(self, component, trigger, decision, reason_code, details=None, confidence=None):
        """
        Logs a decision with structured data for explainability.
        
        Args:
            component (str): "FastLoop", "SlowLoop", "PolicyEngine", etc.
            trigger (str): What triggered this decision (e.g., "InterferenceSpike", "PeriodicOptimization").
            decision (str): Summary of the action taken (e.g., "Switch Channel 6->11").
            reason_code (str): A short code or phrase explaining why (e.g., "HighInterference", "RL_Policy_Optimization").
            details (dict): Detailed context (e.g., {"old_channel": 6, "new_channel": 11, "interference_level": 0.8}).
            confidence (float): Model confidence score if applicable.
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "component": component,
            "trigger": trigger,
            "decision": decision,
            "reason_code": reason_code,
            "details": details or {},
            "confidence": confidence
        }
        
        # Log to file
        logger.info(json.dumps(entry))
        
        # Also print to console for demo purposes
        print(f"[{component}] {decision} | Reason: {reason_code} | Conf: {confidence}")

    def get_recent_logs(self, n=10):
        """Reads the last n lines from the log file."""
        logs = []
        try:
            with open(os.path.join(LOG_DIR, "decision_audit_trail.jsonl"), "r") as f:
                lines = f.readlines()
                for line in lines[-n:]:
                    logs.append(json.loads(line))
        except FileNotFoundError:
            pass
        return logs
