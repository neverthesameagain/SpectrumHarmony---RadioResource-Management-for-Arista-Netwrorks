
# RRM+ Telemetry Schema (Mid-Term Deliverable)

This document defines the telemetry schema for the "Client-View Acquisition" phase, as required by the Arista RRM-Plus problem statement. The schema is divided into three main data tables/streams.

## 1. `rrm_steering_events`

This is the primary event log used to track all RRM steering actions (both active and passive) and their outcomes.

| Field Name | Data Type | Units | Description |
| :--- | :--- | :--- | :--- |
| `timestamp` | `Timestamp` | `ISO 8601` | The UTC timestamp when the steering event was *initiated*. |
| `client_id_hash` | `String` | `SHA-256` | Hashed client MAC address to ensure privacy. |
| `client_oui` | `String` | `Hex` | The OUI (first 3 bytes) of the client MAC, for device classification. |
| `client_os_class` | `String` | `Enum` | The inferred OS of the client (e.g., "iOS", "Windows", "IoT/Legacy"). |
| `origin_ap_id` | `String` | - | The ID/BSSID of the AP *initiating* the steer (the "old" AP). |
| `target_ap_id` | `String` | - | The ID/BSSID of the AP the client was *steered to*. |
| `steer_type` | `String` | `Enum` | The method used: `ACTIVE_802_11V` or `PASSIVE_DISASSOC`. |
| `steer_status` | `String` | `Enum` | The outcome: `SUCCESS` (roamed to target), `REJECT` (client refused 802.11v), `REJOIN` (client rejoined old AP). |
| `pre_roam_qoe` | `Float` | `0.0-5.0` | The client's calculated QoE *before* the steering attempt. |
| `post_roam_qoe` | `Float` | `0.0-5.0` | The client's QoE on the *new* AP, logged upon successful association. |
| `qoe_delta` | `Float` | `+/- 5.0` | The calculated `post_roam_qoe - pre_roam_qoe`. |

## 2. `client_view_reports` (Active 802.11k Data)

This table stores the raw "client-view" data received from 802.11k-capable clients.

| Field Name | Data Type | Units | Description |
| :--- | :--- | :--- | :--- |
| `timestamp` | `Timestamp` | `ISO 8601` | The UTC timestamp when the report was *received* by the AP. |
| `reporting_client_hash` | `String` | `SHA-256` | The client that sent this 802.11k report. |
| `reporting_ap_id` | `String` | - | The AP that *requested* and received this report. |
| `neighbor_bssid` | `String` | `MAC` | The BSSID of the neighbor AP the client "saw". |
| `neighbor_rssi` | `Float` | `dBm` | The signal strength (RSSI) *from the client's perspective*. |
| `neighbor_snr` | `Float` | `dB` | The signal-to-noise ratio (SNR) *from the client's perspective*. |
| `neighbor_channel` | `Integer` | - | The channel of the neighbor AP. |

## 3. `passive_inference_logs` (Passive Data)

This table stores the periodic, passively-observed metrics for all connected clients, used by the RRM for inference.

| Field Name | Data Type | Units | Description |
| :--- | :--- | :--- | :--- |
| `timestamp` | `Timestamp` | `ISO 8601` | The UTC timestamp of the observation. |
| `client_id_hash` | `String` | `SHA-256` | The client being observed. |
| `connected_ap_id` | `String` | - | The AP the client is connected to. |
| `downlink_mcs_index` | `Integer` | `0-11` | (Inferred) The AP's MCS index *to* the client. |
| `downlink_retry_pct` | `Float` | `%` | (Inferred) The AP's retry rate *to* the client. |
| `uplink_mcs_index` | `Integer` | `0-11` | (Inferred) The client's MCS index *to* the AP. |
| `uplink_retry_pct` | `Float` | `%` | (Inferred) The client's retry rate *to* the AP. |
| `ack_variance_ms` | `Float` | `ms` | (Inferred) The calculated jitter/variance in the client's ACK frame responses. |
| `hidden_node_suspicion` | `Integer` | `0-3` | The AP's calculated suspicion score (0-3) of a hidden node. |
