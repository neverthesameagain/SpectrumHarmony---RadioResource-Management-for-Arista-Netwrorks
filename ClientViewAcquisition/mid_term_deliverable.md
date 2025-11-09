# Mid-Term Deliverable: Client-View Acquisition Policies

This document outlines the **Privacy Posture** and **MDM Guidance** for the Arista RRM-Plus **Client-View Acquisition** feature, as required by the Mid-Term deliverables.
### 1. Privacy Posture
This policy defines the data handling principles for all client-side telemetry. The guiding principle is _Privacy by Design_, ensuring that RRM+ improves network performance without compromising user privacy.

**Guiding Principles**
1. **Purpose-Driven**: We collect only the minimum data required to measure client-side QoE and make intelligent RRM decisions.
2. **Anonymization First**: All personally identifiable information (PII) is anonymized at the edge (on the AP) before it is ever stored or aggregated.
3. **No User-Data Inspection**: At no point do we perform Deep Packet Inspection (DPI) or analyze the content of a user's network traffic.

**What We Collect (and Why)**
Our data collection is defined by the `telemetry_schema.md` and is limited to three categories:
1. **Anonymized Identifiers** (from `rrm_steering_events`)
	- Data: `client_id_hash` (a one-way SHA-256 hash of the client's MAC address).
	- Why: To track a single client's QoE journey over time (e.g., calculate qoe_delta upon roaming) without ever storing the actual MAC address.
2. **Device Classification Data** (from `rrm_steering_events`)
	- Data: `client_oui` (e.g., DC:FB:48 for Apple) and `client_os_class` (e.g., "iOS", "Windows").
	- Why: This is essential for the _Acceptance metrics by device class_ deliverable. As our simulation (`client_personas.py`) proves, a _Sticky Laptop (Windows)"_ behaves differently from an _Eager Phone (iOS)_. We must collect this **non-PII** data to build RRM policies that are effective for all device types.
3. **Radio & Performance Metadata** (from `client_view_reports` & `passive_inference_logs`)
	- Active (802.11k): `neighbor_rssi`, `neighbor_snr`. This is purely radio-level data from the client's perspective.
	- Passive (Inference): `uplink_mcs_index`, `uplink_retry_pct`, `ack_variance_ms`. This is metadata observed by the AP about the client's transmissions.

**What We Do Not Collect**
- **No PII**: We do not collect or store unhashed MAC addresses, usernames, device names, or any other PII.
- **No Payload Data**: We do not inspect the content of network packets (e.g., web browsing history, application usage, DNS queries, messages).

**Data Handling & Retention**
1. **Hashing at the Edge**: Client MAC addresses are hashed on the Access Point before being written to the `rrm_steering_events` log.
2. **Data Retention**:
	- Raw Logs (`client_view_reports`, `passive_inference_logs`) are treated as ephemeral and are aggregated. Raw logs are purged after 72 hours.
	- Aggregated Metrics (e.g., "hourly average QoE for client_os_class = 'iOS'") are retained for long-term trend analysis for up to 1 year.
	- Steering Event Logs (`rrm_steering_events`) are retained for 30 days for troubleshooting and KPI reporting.
3. **Administrator Controls**: The entire Client-View Acquisition feature (both active 802.11k probes and passive inference) can be disabled by the network administrator on a per-SSID basis (e.g., for a guest or "BYOD" network).

### 2. MDM Guidance (no agent mandated)
This guidance is for network administrators of corporate-managed environments.

**Guiding Principle: "No Agent Mandated"**
The Arista RRM+ system is designed to work _out of the box_ using open 802.11 standards and agent-less passive inference. No special software or agent is required on the client device.

However, in corporate environments where devices are managed via MDM (Mobile Device Management), administrators can optionally push configuration profiles to optimize RRM+ performance. These settings help solve the _client diversity_ problem demonstrated in our simulation.

**Primary Goal: Enable 802.11k/v Support**

The RRM+'s most effective tool is 802.11v BSS-TM steering. This provides a seamless, _polite_ roam. Our simulation shows that devices in the `legacy_device` persona (supports_80211v: False) must be steered using a "passive" (forced disassociation) method, which is disruptive.
- **Problem:** Some older corporate devices (e.g., our simulated "Windows 7" or "MacBook Air (2015)" personas) may have 802.11k/v support disabled or have buggy drivers.
- **Guidance (Windows):** Use GPO or Microsoft Intune to ensure modern Wi-Fi drivers are installed. For Intel drivers, ensure the "Fast Roaming" (or 802.11k/v) setting is enabled in the driver's Advanced properties.
- **Guidance (macOS/iOS):** No action is typically needed. As shown in our simulation ("iphone_15_pro", "macbook_pro_m3"), Apple devices fully support 802.11k/v.

**Secondary Goal: Optimize Roaming Hysteresis ("Stickiness")**

- **Problem:** The most significant challenge in client diversity is roaming behavior. Our simulation models this with the "sticky_laptop" persona (qoe_hysteresis: 1.5), which will REJECT a valid 802.11v steering command if the new AP isn't significantly better than its current one. This defeats the RRM's attempt to load-balance the client to a healthier AP.
- **Guidance (Windows):** Many corporate Wi-Fi drivers have a "Roaming Aggressiveness" or "Roaming Tendency" setting.
	- **Lowest/Low:** This corresponds to our "sticky" persona. The client will not roam until the signal is almost gone.
	- **Highest/High:** This can cause the client to "flap" between APs.
	- **Recommendation:** Use MDM to set "Roaming Aggressiveness" to "Medium" across the managed device fleet. This value provides the best balance, allowing the client to be stable but still "listen" to and accept the RRM+'s intelligent 802.11v steering suggestions.

**Tertiary Goal: A/B Testing & Phased Rollout**

The Arista PDF (Page 5) requires an "A/B toggle" for a safe-change planner. MDM is the ideal tool for this.
- **Guidance:** We recommend administrators use their MDM to create device groups for a phased rollout.
	- **Phase 1 (Pilot):** Create an "IT Department" device group. Push the new Wi-Fi profile (with 802.11k/v enabled) only to this group. Monitor the RRM+ steering metrics for this client_os_class.
	- **Phase 2 (Expanded Pilot):** Expand the profile to a "Finance" or "Sales" group.
	- **Phase 3 (Full Rollout):** Push the profile to the entire organization.
- **Why:** This MDM-based approach allows the administrator to validate the "Acceptance Metrics" and "QoE Delta" KPIs on a small, controlled group before deploying network-wide, fulfilling the "safe-change" requirement.