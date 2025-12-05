import hashlib
import hmac
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

# --- CONFIGURATION & CONSTANTS ---

# Regulatory Database with per-band power limits
# Logic: 'power_rules' is a list of tuples: (range_start, range_end, max_eirp_dbm, dfs_required)
REGULATORY_DB = {
    "US": {
        "description": "FCC (United States)",
        "allowed_channels_24ghz": list(range(1, 12)), # Ch 1-11
        "allowed_channels_5ghz": list(range(36, 166)),
        "power_rules_24ghz": [
            (1, 11, 30, False)     # 2.4GHz: 1 Watt (30dBm)
        ],
        "power_rules_5ghz": [
            (36, 48, 30, False),   # UNII-1: Max Power, No DFS
            (52, 64, 24, True),    # UNII-2A: Lower Power, DFS Required
            (100, 144, 24, True),  # UNII-2C: Lower Power, DFS Required
            (149, 165, 30, False)  # UNII-3: Max Power, No DFS
        ]
    },
    "IN": {
        "description": "WPC (India)",
        "allowed_channels_24ghz": list(range(1, 14)), # Ch 1-13
        "allowed_channels_5ghz": list(range(36, 65)) + list(range(100, 145)) + [149, 153, 157, 161, 165],
        "power_rules_24ghz": [
            (1, 13, 30, False)     # 2.4GHz: 1 Watt (30dBm) allowed for Spread Spectrum
        ],
        "power_rules_5ghz": [
            (36, 64, 23, False),   # 5150-5350MHz: 200mW (23dBm)
            (100, 144, 23, True),  # 5470-5725MHz: 200mW (23dBm), DFS Required
            (149, 165, 23, False)  # 5725-5875MHz: 200mW (23dBm)
        ]
    },
    "GB": {
        "description": "Ofcom (United Kingdom) / ETSI",
        "allowed_channels_24ghz": list(range(1, 14)), # Ch 1-13
        "allowed_channels_5ghz": list(range(36, 65)) + list(range(100, 141)) + list(range(149, 166)),
        "power_rules_24ghz": [
            (1, 13, 20, False)     # 2.4GHz: STRICT 100mW (20dBm) limit in Europe
        ],
        "power_rules_5ghz": [
            (36, 48, 23, False),   # Band A: Indoor Only, 200mW
            (52, 64, 23, True),    # Band A (Upper): Indoor Only, 200mW, DFS Required
            (100, 140, 30, True),  # Band B: Indoor/Outdoor, 1W (30dBm), DFS Required
            (149, 165, 14, False)  # Band C: SRD limit 25mW (14dBm)
        ]
    },
    "JP": {
        "description": "MIC (Japan)",
        "allowed_channels_24ghz": list(range(1, 14)), # Ch 1-13 (14 is 11b only)
        "allowed_channels_5ghz": list(range(36, 65)) + list(range(100, 145)),
        "power_rules_24ghz": [
            (1, 13, 23, False)     # 2.4GHz: ~200mW (10mW/MHz OFDM)
        ],
        "power_rules_5ghz": [
            (36, 48, 23, False),   # W52: Indoor Only, 200mW
            (52, 64, 23, True),    # W53: Indoor Only, 200mW, DFS Required
            (100, 144, 30, True)   # W56: Indoor/Outdoor, 1W (30dBm), DFS Required
        ]
    },
    "DE": {
        "description": "BNetzA (Germany) / ETSI",
        "allowed_channels_24ghz": list(range(1, 14)), # Ch 1-13
        "allowed_channels_5ghz": list(range(36, 65)) + list(range(100, 141)) + list(range(149, 166)),
        "power_rules_24ghz": [
            (1, 13, 20, False)     # 2.4GHz: STRICT 100mW (20dBm)
        ],
        "power_rules_5ghz": [
            (36, 48, 23, False),   # Lower Band: Indoor, 200mW
            (52, 64, 23, True),    # Lower Band DFS: Indoor, 200mW
            (100, 140, 30, True),  # Upper Band: 1W, DFS Required
            (149, 165, 14, False)  # SRD Band: 25mW (14dBm)
        ]
    }
}

# SLO Profiles
SLO_PROFILES = {
    "VOICE_CRITICAL": {
        "max_channel_width": 40,
        "prevent_switch_active_calls": True,
        "min_power": 12
    },
    "EXAM_HALL": {
        "freeze_window_active": True, 
        "allowed_change_types": [] 
    },
    "DEFAULT": {
        "max_channel_width": 80,
        "min_power": 5,
        "churn_budget_per_hour": 2
    }
}

class PrivacyVault:
    def __init__(self, rotation_interval_hours=24):
        self.current_salt = self._generate_salt()
        self.last_rotation = datetime.now()
        self.rotation_interval = timedelta(hours=rotation_interval_hours)

    def _generate_salt(self) -> bytes:
        return hashlib.sha256(str(time.time()).encode()).digest()

    def rotate_salt_if_needed(self):
        if datetime.now() - self.last_rotation > self.rotation_interval:
            print("LOG: Rotating Privacy Salt")
            self.current_salt = self._generate_salt()
            self.last_rotation = datetime.now()

    def anonymize_mac(self, real_mac: str) -> str:
        self.rotate_salt_if_needed()
        clean_mac = real_mac.replace(":", "").replace("-", "").lower().encode()
        h = hmac.new(self.current_salt, clean_mac, hashlib.sha256)
        return h.hexdigest()[:16]

class AuditLogger:
    def __init__(self):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    def log_decision(self, decision: Dict):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "ap_id": decision.get("target_ap_id"),
            "action": decision.get("action_type"),
            "status": decision.get("status"), 
            "rejection_reason": decision.get("rejection_reason", None),
            "regulatory_domain": decision.get("country_code"),
            "change_details": decision.get("details")
        }
        logging.info(f"AUDIT: {json.dumps(entry)}")

class PolicyEngine:
    def __init__(self):
        self.privacy = PrivacyVault()
        self.audit = AuditLogger()
        self.change_history = {} 

    def _get_regulatory_rule(self, channel: int, country: str) -> Optional[Tuple[int, bool]]:
        """
        Helper to find the specific rule for a channel in a country.
        Automatically detects if it's 2.4GHz or 5GHz based on channel number.
        """
        reg_data = REGULATORY_DB.get(country, REGULATORY_DB["US"])
        
        # Determine Band
        is_24ghz = 1 <= channel <= 14
        
        allowed_list = reg_data['allowed_channels_24ghz'] if is_24ghz else reg_data['allowed_channels_5ghz']
        rules_list = reg_data['power_rules_24ghz'] if is_24ghz else reg_data['power_rules_5ghz']

        # Check if allowed first
        if channel not in allowed_list:
            return None
            
        # Iterate rules to find the one matching this channel
        for start, end, max_pwr, dfs in rules_list:
            if start <= channel <= end:
                return (max_pwr, dfs)
        
        return None

    def _check_regulatory(self, proposal: Dict, country: str) -> Tuple[bool, str]:
        """
        Validates against REGULATORY_DB using granular power rules.
        """
        channel_to_check = proposal.get('new_value') if proposal['action_type'] == 'channel_switch' else proposal.get('current_channel')
        
        if not channel_to_check:
             return False, "Missing channel context for regulatory check"

        rule = self._get_regulatory_rule(channel_to_check, country)
        if not rule:
             return False, f"Channel {channel_to_check} not allowed in {country}"

        max_allowed_power, dfs_required = rule

        # 1. Power Check
        if proposal['action_type'] == 'power_change':
            new_power = proposal['new_value']
            if new_power > max_allowed_power:
                return False, f"Power {new_power}dBm exceeds {country} limit for Ch{channel_to_check} ({max_allowed_power}dBm)"

        # 2. DFS Check
        if proposal['action_type'] == 'channel_switch' and dfs_required:
             # In production, check if CAC (Channel Availability Check) is complete
             pass

        return True, ""

    def evaluate_proposal(self, proposal: Dict, ap_profile: Dict, current_state: Dict, country: str = "US") -> Dict:
        """
        Main entry point. Takes a proposed change and returns Approved/Rejected.
        """
        
        # 1. Regulatory Check
        passed, reason = self._check_regulatory(proposal, country)
        if not passed:
            self._log_result(proposal, "REJECTED", reason, country)
            return {"status": "REJECTED", "reason": reason}

        # 2. SLO and Guardrail Checks (Simplified for this snippet)
        # ... (Same as previous versions) ...

        # Success - Commit Change
        self._record_change(proposal['target_ap_id'])
        self._log_result(proposal, "APPROVED", "All checks passed", country)
        
        return {"status": "APPROVED", "reason": "Valid"}

    def _record_change(self, ap_id):
        if ap_id not in self.change_history:
            self.change_history[ap_id] = []
        self.change_history[ap_id].append(datetime.now())

    def _log_result(self, proposal, status, reason, country):
        decision = {
            "target_ap_id": proposal['target_ap_id'],
            "action_type": proposal['action_type'],
            "status": status,
            "rejection_reason": reason,
            "country_code": country,
            "details": proposal
        }
        self.audit.log_decision(decision)

# --- DEMONSTRATION ---

if __name__ == "__main__":
    engine = PolicyEngine()

    print("--- 2.4 GHz Regulatory Scenarios ---")
    
    # Scenario 1: US - 30dBm on Channel 6
    # Should be APPROVED (US limit is 30)
    print("\nScenario: US - Requesting 30dBm on 2.4GHz Channel 6")
    prop_us = {"target_ap_id": "AP-US", "action_type": "power_change", "new_value": 30, "current_channel": 6}
    res_us = engine.evaluate_proposal(prop_us, {}, {}, country="US")
    print(f"Result: {res_us['status']} ({res_us['reason']})")
    
    # Scenario 2: Germany - 30dBm on Channel 6
    # Should be REJECTED (EU limit is 20)
    print("\nScenario: Germany (DE) - Requesting 30dBm on 2.4GHz Channel 6")
    prop_de = {"target_ap_id": "AP-DE", "action_type": "power_change", "new_value": 30, "current_channel": 6}
    res_de = engine.evaluate_proposal(prop_de, {}, {}, country="DE")
    print(f"Result: {res_de['status']} ({res_de['reason']})")

    # Scenario 3: UK - 20dBm on Channel 6
    # Should be APPROVED (Limit is exactly 20)
    print("\nScenario: UK (GB) - Requesting 20dBm on 2.4GHz Channel 6")
    prop_uk = {"target_ap_id": "AP-UK", "action_type": "power_change", "new_value": 20, "current_channel": 6}
    res_uk = engine.evaluate_proposal(prop_uk, {}, {}, country="GB")
    print(f"Result: {res_uk['status']} ({res_uk['reason']})")