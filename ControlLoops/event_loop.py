from datetime import datetime
from ControlLoops.utils.CSVParser import CSVParser
from SensingOrchestra.channel_info import BAND_5_CHANNELS
from SensingOrchestra.utilsSO.WiFiBandEnum import WiFiBand
import ControlLoops.utils.APLogsColumns as APLog
import logging
import os

logging.basicConfig(filename="output.log", level=logging.DEBUG)
base_dir = os.path.dirname(__file__)


class EventLoop:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(EventLoop, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        self.noiseBaseline = {}
        self.lastSeen = {
            "microwave": {},
            "dfs": {},
            "exam": {}
        }
        self.timeouts = {
            "microwave": 100,
            "dfs": 100,
            "exam": 100
        }

        self.last_channel = {
            "microwave": None,
            "exam_2_4": None,
            "exam_5": None,
            "dfs": None
        }
        self.chanToIdx_5_GHz = {ch: idx for idx, ch in enumerate(BAND_5_CHANNELS)}
        self.prev_2_4_GHz = ""
        self.prev_5_GHz = ""
        print("Event loop initiated...")

    def start(self):
        file_path = os.path.join(base_dir, "data", "interference_edges.csv")
        self.simulate_radio_input(file_path)

    def update_baseline(self, channel, rxPower):
        if channel not in self.noiseBaseline:
            self.noiseBaseline[channel] = rxPower
        else:
            alpha = 0.1
            self.noiseBaseline[channel] = (1 - alpha) * self.noiseBaseline[channel] + alpha * rxPower

    def get_baseline(self, channel):
        return self.noiseBaseline.get(channel, -90)

    def convert_band_to_idx(self, band, channel):
        if (band == WiFiBand.BAND_2_4_GHz):
            return channel-1
        elif (band == WiFiBand.BAND_5_GHz):
            return self.chanToIdx_5_GHz[channel]
        elif (band == WiFiBand.BAND_6_GHz):
            logging.error("Not yet implemented...")
            return 0
        else:
            logging.error("Not a recognised band...")
        return 0

    def check_timeout(self, kind, key, timestamp):
        timestamp = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
        last = self.lastSeen[kind].get(key, None)

        if last is None:
            self.lastSeen[kind][key] = timestamp
            return False

        delta = (timestamp - last).total_seconds()

        if delta >= self.timeouts[kind]:
            self.lastSeen[kind][key] = timestamp
            return True

        return False

    def detect_microwave(self, band, retryA, nwifiDetectedA, nwifiTypeA, rxPower, baseline):
        if band != WiFiBand.BAND_2_4_GHz:
            return False
        if rxPower - baseline < 0.10:
            print("Failed here..")
            return False
        if retryA < 0.09:
            return False
        if not nwifiDetectedA:
            return False
        if nwifiTypeA not in ["Microwave", "ZigBee", "broadband", "unknown"]:
            return False
        return True

    def detect_dfs_radar(self, band, channelA, nwifiTypeA):
        if band != WiFiBand.BAND_5_GHz:
            return False
        if not (52 <= channelA <= 144):
            return False
        if nwifiTypeA in ["radar", "FHSS"]:
            return True
        return False

    def detect_exam_hall(self, airtimeA, retryA):
        if airtimeA < 0.25:
            return False
        if retryA < 0.15:
            return False
        return True

    def detect_event_2_4_ghz(self, timestamp, band, channel, airtimeA, retryA, nwifiDetectedA, nwifiTypeA, rxPower):
        baseline = self.get_baseline(channel)
        if self.detect_microwave(band, retryA, nwifiDetectedA, nwifiTypeA, rxPower, baseline):
            if self.check_timeout("microwave", (band, channel), timestamp):
                if channel != self.last_channel["microwave"]:
                    print(f"Event : Microwave detected on 2.4 GHz band on channel {channel}")
                    self.last_channel["microwave"] = channel
                    # Push to FastLoop
                    from ControlLoops.fast_loop import FastLoop
                    FastLoop().add_change({"type": "Interference", "value": "Microwave", "channel": channel, "band": "2.4GHz"})

        if self.detect_exam_hall(airtimeA, retryA):
            if self.check_timeout("exam", (band, channel), timestamp):
                if channel != self.last_channel["exam_2_4"]:
                    print(f"Event : Exam hall detected on 2.4 GHz band on channel {channel}")
                    self.last_channel["exam_2_4"] = channel
                    # Push to FastLoop
                    from ControlLoops.fast_loop import FastLoop
                    FastLoop().addChange({"type": "ExamHall", "value": "QuietHours", "channel": channel, "band": "2.4GHz"})

    def detect_event_5_ghz(self, timestamp, band, channel, nwifiTypeA, airtimeA, retryA):
        if self.detect_dfs_radar(band, channel, nwifiTypeA):
            if self.check_timeout("dfs", (band, channel), timestamp):
                if channel != self.last_channel["dfs"]:
                    print(f"Event : DFS radar detected on 5 GHz band on channel {channel}")
                    self.last_channel["dfs"] = channel
                    # Push to FastLoop
                    from ControlLoops.fast_loop import FastLoop
                    FastLoop().addChange({"type": "DFS", "value": "Radar", "channel": channel, "band": "5GHz"})

        if self.detect_exam_hall(airtimeA, retryA):
            if self.check_timeout("exam", (band, channel), timestamp):
                if channel != self.last_channel["exam_5"]:
                    print(f"Event : Exam hall detected on 5 GHz band on channel {channel}")
                    self.last_channel["exam_5"] = channel
                    # Push to FastLoop
                    from ControlLoops.fast_loop import FastLoop
                    FastLoop().addChange({"type": "ExamHall", "value": "QuietHours", "channel": channel, "band": "5GHz"})

    def simulate_radio_input(self, file):
        parser = CSVParser()
        beacons = parser.parseCSV(file)
        print("Event Loop ", file)
        for beacon in beacons:
            band = beacon[APLog.BAND]
            channelA = self.convert_band_to_idx(beacon[APLog.BAND], beacon[APLog.CHANNEL_A])
            airtimeA = beacon[APLog.AIRTIME_A]
            retryA = beacon[APLog.P95_RETRY_A]
            nwifiDetectedA = beacon[APLog.NWIFI_DETECTED_A]
            nwifiTypeA = beacon[APLog.NWIFI_TYPE_A]
            rxPower = beacon[APLog.RX_POWER_EST_NORM]
            radarPenalty = beacon[APLog.RADAR_PENALTY]
            timestamp = beacon[APLog.TIMESTAMP]
            if (band == WiFiBand.BAND_2_4_GHz):
                self.detect_event_2_4_ghz(timestamp, band, beacon[APLog.CHANNEL_A], airtimeA, retryA,
                                          nwifiDetectedA, nwifiTypeA, rxPower)
            elif (band == WiFiBand.BAND_5_GHz):
                self.detect_event_5_ghz(timestamp, band, beacon[APLog.CHANNEL_A], nwifiTypeA,
                                        airtimeA, retryA)


eventLoop = EventLoop()
eventLoop.start()
