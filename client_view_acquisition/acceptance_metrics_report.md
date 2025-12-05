# Mid-Term Deliverable: Acceptance Metrics by Device Class

This report details the effectiveness of RRM steering actions across a simulated environment of **12 APs** and **80 clients**.

## Overall RRM KPI Summary
- **Total Steering Attempts:** 2777
- **Total Successful Steers:** 1045
- **Overall Acceptance Rate:** **37.6%**
- **Average Post-Roam QoE Delta:** **+0.06 points**

## AP-Specific QoE Delta
| AP ID | Average QoE Delta |
| :--- | :---: |
| AP-1 | +0.00 |
| AP-2 | -0.07 |
| AP-3 | -0.07 |
| AP-4 | -0.05 |
| AP-5 | +0.01 |
| AP-6 | +0.13 |
| AP-7 | +0.24 |
| AP-8 | +0.26 |
| AP-9 | +0.47 |
| AP-10 | +0.00 |
| AP-11 | +0.00 |
| AP-12 | +0.00 |

## Steering Success Matrix (by Device Class)

| Device Class (Persona) | OUI | OS Class | 802.11k/v Capable? | Steer Attempts | Steer Successes | Steer Rejects | Acceptance Rate |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| Apple iPhone 15 Pro | `DC:FB:48` | iOS 17 | ✅ Yes | 70 | 32 | 38 | **45.7%** |
| Samsung Galaxy S24 Ultra | `B8:27:EB` | Android 14 | ✅ Yes | 129 | 95 | 34 | **73.6%** |
| Google Pixel 8 | `3C:28:6D` | Android 14 | ✅ Yes | 474 | 406 | 68 | **85.7%** |
| OnePlus 12 | `9C:93:4E` | Android 13 | ✅ Yes | 43 | 7 | 36 | **16.3%** |
| Xiaomi 13T | `A4:77:33` | Android 12 | ✅ Yes | 12 | 1 | 11 | **8.3%** |
| MacBook Pro (M3) | `DC:FB:48` | macOS 14 Sonoma | ✅ Yes | 69 | 35 | 34 | **50.7%** |
| Lenovo ThinkPad X1 | `00:1A:2B` | Windows 11 | ✅ Yes | 58 | 14 | 44 | **24.1%** |
| Dell XPS 13 | `00:1E:67` | Windows 10 | ✅ Yes | 10 | 0 | 10 | **0.0%** |
| HP EliteBook | `A0:9C:9F` | Windows 10 | ✅ Yes | 2 | 0 | 2 | **0.0%** |
| Microsoft Surface Pro 9 | `18:5E:0F` | Windows 11 | ✅ Yes | 21 | 4 | 17 | **19.0%** |
| Lenovo Chromebook | `50:EB:F6` | ChromeOS 120 | ✅ Yes | 418 | 381 | 37 | **91.1%** |
| Apple iPad Air (M2) | `DC:FB:48` | iPadOS 17 | ✅ Yes | 7 | 1 | 6 | **14.3%** |
| Samsung Galaxy Tab S9 | `B8:27:EB` | Android 14 | ✅ Yes | 10 | 1 | 9 | **10.0%** |
| Apple Watch Series 9 | `DC:FB:48` | watchOS 10 | ❌ No | 624 | 0 | 0 | **0.0%** |
| TP-Link Smart Camera | `F4:F2:6D` | Linux IoT | ❌ No | 360 | 0 | 0 | **0.0%** |
| Google Nest Thermostat | `3C:28:6D` | Embedded Linux | ❌ No | 0 | 0 | 0 | **N/A** |
| ESP32 Sensor Node | `24:6F:28` | RTOS (ESP-IDF) | ❌ No | 0 | 0 | 0 | **N/A** |
| Raspberry Pi Camera Node | `B8:27:EB` | Raspbian Linux | ❌ No | 0 | 0 | 0 | **N/A** |
| Amazon Echo Dot | `44:65:0D` | FireOS IoT | ❌ No | 0 | 0 | 0 | **N/A** |
| LG Smart TV | `64:BC:0C` | webOS | ❌ No | 0 | 0 | 0 | **N/A** |
| Roku Streaming Stick | `00:0D:4B` | Linux Embedded | ❌ No | 0 | 0 | 0 | **N/A** |
| Sony PlayStation 5 | `00:26:5D` | OrbisOS | ✅ Yes | 107 | 68 | 39 | **63.6%** |
| HP LaserJet 4000 | `00:08:C1` | Legacy Wi-Fi (802.11g) | ❌ No | 3 | 0 | 0 | **0.0%** |
| Samsung Galaxy S7 | `B8:27:EB` | Android 8 | ❌ No | 0 | 0 | 0 | **N/A** |
| MacBook Air (2015) | `F0:18:98` | macOS Catalina | ❌ No | 0 | 0 | 0 | **N/A** |
| Dell Latitude Win7 | `00:1E:67` | Windows 7 | ❌ No | 360 | 0 | 0 | **0.0%** |