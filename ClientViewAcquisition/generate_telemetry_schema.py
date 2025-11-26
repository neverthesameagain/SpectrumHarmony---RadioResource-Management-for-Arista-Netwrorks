# -*- coding: utf-8 -*-
"""
This module generates the telemetry schema for the RRM+ project.

UPDATES (End-Term):
- Added `client_transport_qoe` table definition.
- Added `client_rtt_measurements` table definition.
"""


def generate_telemetry_schema():
    """
    Generates the telemetry schema and writes it to a Markdown file.
    """
    telemetry_schema_content = """
# RRM+ Telemetry Schema (End-Term Deliverable)

This document defines the comprehensive telemetry schema for the "Client-View Acquisition" phase, including End-Term requirements for Transport Layer QoE and 802.11mc RTT.

## 1. `rrm_steering_events` (Control Plane)
Tracks all active/passive steering actions and outcomes.

| Field Name | Data Type | Units | Description |
| :--- | :--- | :--- | :--- |
| `timestamp` | `Timestamp` | `ISO 8601` | Time of steering initiation. |
| `client_id_hash` | `String` | `SHA-256` | Privacy-preserving ID. |
| `origin_ap_id` | `String` | - | "Old" AP. |
| `target_ap_id` | `String` | - | "New" AP. |
| `steer_type` | `String` | `Enum` | `ACTIVE_802_11V` or `PASSIVE_DISASSOC`. |
| `steer_status` | `String` | `Enum` | `SUCCESS`, `REJECT`, `REJOIN`. |
| `qoe_delta` | `Float` | `+/- 5.0` | `post_roam_qoe - pre_roam_qoe`. |

## 2. `client_view_reports` (802.11k Data)
Raw neighbor reports from clients.

| Field Name | Data Type | Units | Description |
| :--- | :--- | :--- | :--- |
| `timestamp` | `Timestamp` | `ISO 8601` | Time report received. |
| `client_id_hash` | `String` | `SHA-256` | Client ID. |
| `neighbor_bssid` | `String` | `MAC` | Neighbor AP BSSID. |
| `neighbor_rssi` | `Float` | `dBm` | RSSI seen by client. |
| `neighbor_snr` | `Float` | `dB` | SNR seen by client. |

## 3. `client_transport_qoe` (End-Term: Layer 4) 
[cite_start]Passive monitoring of TCP/QUIC performance to detect congestion/bufferbloat[cite: 104].

| Field Name | Data Type | Units | Description |
| :--- | :--- | :--- | :--- |
| `timestamp` | `Timestamp` | `ISO 8601` | Observation time. |
| `client_id_hash` | `String` | `SHA-256` | Client ID. |
| `connected_ap_id` | `String` | - | Current AP. |
| `tcp_rtt_ms` | `Float` | `ms` | Round Trip Time to app server (detects bufferbloat). |
| `tcp_retransmits_pct` | `Float` | `%` | Percentage of retransmitted packets (detects loss). |
| `jitter_ms` | `Float` | `ms` | Variance in RTT (stability metric). |

## 4. `client_rtt_measurements` (End-Term: 802.11mc) 
[cite_start]Fine Timing Measurement (FTM) data for location-aware interference mapping[cite: 103].

| Field Name | Data Type | Units | Description |
| :--- | :--- | :--- | :--- |
| `timestamp` | `Timestamp` | `ISO 8601` | Time of measurement. |
| `client_id_hash` | `String` | `SHA-256` | Client ID. |
| `target_ap_id` | `String` | - | The AP being measured against. |
| `distance_meters` | `Float` | `m` | Calculated distance (Speed of Light * RTT / 2). |
| `distance_std_dev` | `Float` | `m` | Error estimate/variance of the burst. |
"""
    with open("telemetry_schema.md", "w") as f:
        f.write(telemetry_schema_content)
    print("\n✅ Successfully generated 'telemetry_schema.md' (End-Term Version)")


if __name__ == "__main__":
    generate_telemetry_schema()
