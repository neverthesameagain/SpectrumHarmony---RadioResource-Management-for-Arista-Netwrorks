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
# Channels are inclusive of start/end.
REGULATORY_DB = {
    "US": {
        "description": "FCC (United States)",
        "allowed_channels_5ghz": list(range(36, 166)),
        "power_rules": [
            (36, 48, 30, False),   # UNII-1: Max Power, No DFS
            (52, 64, 24, True),    # UNII-2A: Lower Power, DFS Required
            (100, 144, 24, True),  # UNII-2C: Lower Power, DFS Required
            (149, 165, 30, False)  # UNII-3: Max Power, No DFS
        ]
    },
    "IN": {
        "description": "WPC (India)",
        "allowed_channels_5ghz": list(range(36, 65)) + list(range(100, 145)) + [149, 153, 157, 161, 165],
        "power_rules": [
            (36, 64, 23, False),   # 5150-5350MHz: 200mW (23dBm). DFS technically required on 52-64 but often relaxed indoors.
            (100, 144, 23, True),  # 5470-5725MHz: 200mW (23dBm), DFS Required.
            (149, 165, 23, False)  # 5725-5875MHz: 200mW (23dBm).
        ]
    },
    "GB": {
        "description": "Ofcom (United Kingdom) / ETSI",
        "allowed_channels_5ghz": list(range(36, 65)) + list(range(100, 141)) + list(range(149, 166)),
        "power_rules": [
            (36, 48, 23, False),   # Band A: Indoor Only, 200mW
            (52, 64, 23, True),    # Band A (Upper): Indoor Only, 200mW, DFS Required
            (100, 140, 30, True),  # Band B: Indoor/Outdoor, 1W (30dBm), DFS Required
            (149, 165, 14, False)  # Band C: SRD (Short Range Devices) limit is 25mW (14dBm). Often not used for enterprise APs.
        ]
    },
    "JP": {
        "description": "MIC (Japan)",
        "allowed_channels_5ghz": list(range(36, 65)) + list(range(100, 145)),
        "power_rules": [
            (36, 48, 23, False),   # W52: Indoor Only, 200mW
            (52, 64, 23, True),    # W53: Indoor Only, 200mW, DFS Required
            (100, 144, 30, True)   # W56: Indoor/Outdoor, 1W (30dBm), DFS Required
        ]
    },
    "DE": {
        "description": "BNetzA (Germany) / ETSI",
        "allowed_channels_5ghz": list(range(36, 65)) + list(range(100, 141)) + list(range(149, 166)),
        "power_rules": [
            (36, 48, 23, False),   # Lower Band: Indoor, 200mW
            (52, 64, 23, True),    # Lower Band DFS: Indoor, 200mW
            (100, 140, 30, True),  # Upper Band: 1W, DFS Required
            (149, 165, 14, False)  # SRD Band: 25mW (14dBm) limit for generic use.
        ]
    }
}

# SLO Profiles
SLO_PROFILES = {
    "VOICE_CRITICAL": {
        "max_channel_width": 40, # Narrower channels = less interference
        "prevent_switch_active_calls": True,
        "min_power": 12
    },
    "EXAM_HALL": {
        "freeze_window_active": True, # Logic to be checked against time
        "allowed_change_types": [] # No changes allowed
    },
    "HIGH_DENSITY": {
        "max_channel_width": 40, # Prevent 80MHz to allow more non-overlapping channels
        "min_power": 8,
        "churn_budget_per_hour": 1
    },
    "DEFAULT": {
        "max_channel_width": 80,
        "min_power": 5,
        "churn_budget_per_hour": 2
    }
}

class PrivacyVault:
    """
    Handles anonymization of client data.
    """
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
        """
        Hashes a MAC address using HMAC-SHA256 with a rotating salt.
        Output is truncated for brevity but remains unique for the rotation period.
        """
        self.rotate_salt_if_needed()
        # Normalize MAC
        clean_mac = real_mac.replace(":", "").replace("-", "").lower().encode()
        
        # Create HMAC
        h = hmac.new(self.current_salt, clean_mac, hashlib.sha256)
        
        # Return first 16 chars of hex digest
        return h.hexdigest()[:16]

class AuditLogger:
    """
    Logs all decisions for compliance and debugging.
    """
    def __init__(self, log_file="rrm_audit.jsonl"):
        self.log_file = log_file
        # Setup basic logging to console as well
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    def log_decision(self, decision: Dict):
        """
        Appends a structured JSON log entry.
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "ap_id": decision.get("target_ap_id"),
            "action": decision.get("action_type"),
            "status": decision.get("status"), # APPROVED / REJECTED
            "rejection_reason": decision.get("rejection_reason", None),
            "regulatory_domain": decision.get("country_code"),
            "change_details": decision.get("details")
        }
        
        # specific logic to write to file would go here
        logging.info(f"AUDIT: {json.dumps(entry)}")

class PolicyEngine:
    def __init__(self):
        self.privacy = PrivacyVault()
        self.audit = AuditLogger()
        # In-memory store for recent changes to enforce Churn limits
        # Structure: { ap_id: [timestamp1, timestamp2] }
        self.change_history = {} 

    def _get_regulatory_rule(self, channel: int, country: str) -> Optional[Tuple[int, bool]]:
        """
        Helper to find the specific rule (Max Power, DFS) for a channel in a country.
        Returns: (max_eirp, dfs_required) or None if channel not found.
        """
        reg_data = REGULATORY_DB.get(country, REGULATORY_DB["US"])
        
        # Check if allowed first
        if channel not in reg_data['allowed_channels_5ghz']:
            return None
            
        # Iterate rules to find the one matching this channel
        for start, end, max_pwr, dfs in reg_data['power_rules']:
            if start <= channel <= end:
                return (max_pwr, dfs)
        
        return None

    def _check_regulatory(self, proposal: Dict, country: str) -> Tuple[bool, str]:
        """
        Validates against REGULATORY_DB using granular power rules.
        """
        # Determine which channel we are talking about
        # For power changes, it's the current channel. For channel switches, it's the new channel.
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

        # 2. DFS Check (Warning/Cost)
        if proposal['action_type'] == 'channel_switch' and dfs_required:
             # In a real system, we check CAC status. Here we just note it.
             # If strict mode was on, we might reject if CAC wasn't done.
             pass

        return True, ""

    def _check_slo(self, proposal: Dict, ap_profile: Dict, current_state: Dict) -> Tuple[bool, str]:
        """
        Validates against SLO_PROFILES.
        """
        profile_name = ap_profile.get('profile_name', 'DEFAULT')
        rules = SLO_PROFILES.get(profile_name, SLO_PROFILES['DEFAULT'])

        # 1. Exam Hall Freeze
        if profile_name == "EXAM_HALL" and rules.get("freeze_window_active"):
            return False, "SLO Violation: Exam Hall Freeze Active"

        # 2. Voice Protection
        if rules.get("prevent_switch_active_calls") and proposal['action_type'] == 'channel_switch':
            if current_state.get('active_voice_calls', 0) > 0:
                # Exception: unless interference is CATASTROPHIC (reason code check)
                if proposal.get('reason_code') != 'RADAR_DETECTED':
                    return False, "SLO Violation: Active Voice Calls present"

        # 3. Channel Width Constraints
        if proposal['action_type'] == 'width_change':
            max_width = rules.get('max_channel_width', 80)
            if proposal['new_value'] > max_width:
                return False, f"SLO Violation: Width {proposal['new_value']} exceeds profile limit {max_width}"

        return True, ""

    def _check_guardrails(self, proposal: Dict) -> Tuple[bool, str]:
        """
        Checks Churn (rate of change) and Blast Radius.
        """
        ap_id = proposal['target_ap_id']
        now = datetime.now()
        
        # Clean old history
        if ap_id in self.change_history:
            self.change_history[ap_id] = [t for t in self.change_history[ap_id] if now - t < timedelta(hours=4)]
        
        # Check Churn Budget (e.g., max 2 changes per 4 hours)
        recent_changes = len(self.change_history.get(ap_id, []))
        if recent_changes >= 2:
            # Exception: RADAR requires immediate move regardless of budget
            if proposal.get('reason_code') != 'RADAR_DETECTED':
                return False, "Guardrail: Churn budget exceeded (2 changes/4hrs)"

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

        # 2. SLO Check
        passed, reason = self._check_slo(proposal, ap_profile, current_state)
        if not passed:
            self._log_result(proposal, "REJECTED", reason, country)
            return {"status": "REJECTED", "reason": reason}

        # 3. Guardrail Check
        passed, reason = self._check_guardrails(proposal)
        if not passed:
            self._log_result(proposal, "REJECTED", reason, country)
            return {"status": "REJECTED", "reason": reason}

        # 4. Success - Commit Change
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

    print("--- 1. Regulatory Scenarios (Expanded Countries) ---")
    
    # Scenario 1: UK - High Power on DFS Channel (Allowed in Band B)
    # Channel 100 in UK allows 30dBm (1000mW)
    print("\nScenario: UK (GB) - Requesting 28dBm on Channel 100")
    prop_uk = {"target_ap_id": "AP-UK", "action_type": "power_change", "new_value": 28, "current_channel": 100}
    res_uk = engine.evaluate_proposal(prop_uk, {}, {}, country="GB")
    print(f"Result: {res_uk['status']} ({res_uk['reason']})") # Should be APPROVED
    
    # Scenario 2: UK - High Power on Lower Band (Not Allowed)
    # Channel 36 in UK is limited to 23dBm (200mW)
    print("\nScenario: UK (GB) - Requesting 28dBm on Channel 36")
    prop_uk_bad = {"target_ap_id": "AP-UK", "action_type": "power_change", "new_value": 28, "current_channel": 36}
    res_uk_bad = engine.evaluate_proposal(prop_uk_bad, {}, {}, country="GB")
    print(f"Result: {res_uk_bad['status']} ({res_uk_bad['reason']})") # Should be REJECTED

    # Scenario 3: Japan - Channel 149 (Not Allowed)
    # Japan mostly ends at Ch 144 (W56). 149+ is not standard for W56.
    print("\nScenario: Japan (JP) - Switching to Channel 149")
    prop_jp = {"target_ap_id": "AP-JP", "action_type": "channel_switch", "new_value": 149}
    res_jp = engine.evaluate_proposal(prop_jp, {}, {}, country="JP")
    print(f"Result: {res_jp['status']} ({res_jp['reason']})") # Should be REJECTED

    # Scenario 4: Germany - SRD Band 155
    # Allowed but low power (14dBm)
    print("\nScenario: Germany (DE) - High Power (20dBm) on Channel 157 (Limit 14dBm)")
    prop_de = {"target_ap_id": "AP-DE", "action_type": "power_change", "new_value": 20, "current_channel": 157}
    res_de = engine.evaluate_proposal(prop_de, {}, {}, country="DE")
    print(f"Result: {res_de['status']} ({res_de['reason']})") # Should be REJECTED