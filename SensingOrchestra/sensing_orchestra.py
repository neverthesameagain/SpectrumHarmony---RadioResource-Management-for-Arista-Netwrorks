from datetime import datetime
import json
import threading
from SensingOrchestra.channel_info import ChannelInfo
from .DFSTimer import DFSTimerManager
from .utilsSO import APLogsColumns as APLog
from .utilsSO.WiFiBandEnum import WiFiBand
from .utilsSO.CSVParserSO import CSVParserSO
from .MAB import MAB
from ControlLoops.InterferenceGraph import InterferenceGraph
from ControlLoops.EventLoop import EventLoop
import os
import time
import psutil
import os
import logging

logging.basicConfig(filename="output.log", level=logging.DEBUG)
base_dir = os.path.dirname(__file__)


class SensingOrchestra:
    def __init__(self, name):
        self.numChannels_2_4_GHz = 0
        self.channelParameters_2_4_GHz = []
        self.numChannels_5s_GHz = 0
        self.channelParameters_5_GHz = []
        self.channel_2_4_GHz = 0
        self.channelReward_2_4_GHz = 1
        self.channel_5_GHz = 0
        self.channelReward_5_GHz = 1
        self.scanTime = 0.2  # 1 second
        self.serveTime = 5.9  # 59 seconds
        self.startTime = time.time()
        self.isRunning = True
        self.graph = InterferenceGraph()
        self.APname = name
        self.eventLoop = EventLoop()
        # not use DFS channel for 30 minutes after a DFS radar encounter
        self.DFStimer = DFSTimerManager(30 * 60, self.clear_dfs_clients_5_ghz)
        logging.info("Initiating Sensing Orchestra...")

    def start(self):
        self.initiate_channels()
        # file_path = os.path.join(base_dir, "data", "apLogs.csv")  # TODO: should be initialising channels beacons
        # self.simulateRadioInput(file_path)
        self.initialize_mab()
        while (self.isRunning):
            self.startTime = time.time()
            while (time.time() - self.startTime < self.serveTime):
                logging.info("Serving Client Request...")
                # time.sleep(self.serveTime)

            channelTime_2_4_Ghz = self.scanTime * self.channelReward_2_4_GHz
            channelTime_5_Ghz = self.scanTime * self.channelReward_5_GHz
            self.scan_thread_2_4_GHz = threading.Thread(target=self.scan_2_4_GHz)
            self.scan_thread_5_GHz = threading.Thread(target=self.scan_5_GHz)
            self.scan_thread_2_4_GHz.start()
            self.scan_thread_5_GHz.start()
            self.scan_thread_2_4_GHz.join()
            self.scan_thread_5_GHz.join()
            # time.sleep(self.scanTime)

    def scan_5_GHz(self):
        logging.info("Scanning channels...")
        logging.info("For 5GHz...")
        self.channel_5_GHz = self.choose_channel_5_ghz()
        # self.graph.updateChannel_5_Ghz(self.channel_5_GHz)
        logging.info(f"Noisiest 5GHz channel... {self.channel_5_GHz}")
        idx = self.convert_band_to_idx(WiFiBand.BAND_5_GHz, self.channel_5_GHz)
        self.channelParameters_5_GHz[idx].print_channel()
        file_path = os.path.join(base_dir, "data", f"Aplog_5_GHz_{self.channel_5_GHz}.csv")
        self.simulate_radio_input(file_path)  # read the respective channel detail

    def scan_2_4_GHz(self):
        logging.info("Scanning channels...")
        logging.info("For 2_4GHz...")
        self.channel_2_4_GHz = self.choose_channel_2_4_ghz()
        # self.graph.updateChannel_2_4_Ghz(self.channel_2_4_GHz)
        logging.info(f"Noisiest 2_4GHz channel... {self.channel_2_4_GHz}")
        idx = self.convert_band_to_idx(WiFiBand.BAND_2_4_GHz, self.channel_2_4_GHz)
        self.channelParameters_2_4_GHz[idx].print_channel()
        file_path = os.path.join(base_dir, "data", f"Aplog_2_4_GHz_{self.channel_2_4_GHz}.csv")
        self.simulate_radio_input(file_path)  # read the respective channel detail

    def initiate_channels(self):
        self.numChannels_2_4_GHz = 14
        self.channels_2_4_GHz = BAND_2_4_CHANNELS
        self.numChannels_5_GHz = 24
        self.channels_5_GHz = BAND_5_CHANNELS
        self.chanToIdx_5_GHz = {ch: idx for idx, ch in enumerate(BAND_5_CHANNELS)}
        self.idxToChan_5_GHz = {idx: ch for idx, ch in enumerate(BAND_5_CHANNELS)}
        logging.warning("Might implement 6GHz in future...")
        for i in range(self.numChannels_2_4_GHz):
            self.channelParameters_2_4_GHz.append(ChannelInfo(WiFiBand.BAND_2_4_GHz, self.channels_2_4_GHz[i]))
        for i in range(self.numChannels_5_GHz):
            self.channelParameters_5_GHz.append(ChannelInfo(WiFiBand.BAND_5_GHz, self.channels_5_GHz[i]))

    def initialize_mab(self):
        self.MAB_2_4_GHz = MAB(self.numChannels_2_4_GHz)
        rewards_2_4_GHz = []
        for channel in self.channelParameters_2_4_GHz:
            rewards_2_4_GHz.append(channel.reward())
        self.MAB_2_4_GHz.initializeArms(rewards_2_4_GHz)

        self.MAB_5_GHz = MAB(self.numChannels_5_GHz)
        rewards_5_GHz = []
        for channel in self.channelParameters_5_GHz:
            rewards_5_GHz.append(channel.reward())
        self.MAB_5_GHz.initializeArms(rewards_5_GHz)

    def choose_channel_2_4_ghz(self):
        bestChannel = self.MAB_2_4_GHz.selectArm()
        self.channelReward_2_4_GHz = self.channelParameters_2_4_GHz[bestChannel].reward()
        self.MAB_2_4_GHz.updateArm(bestChannel, self.channelReward_2_4_GHz)
        channel = self.convert_idx_to_band(WiFiBand.BAND_2_4_GHz, bestChannel)
        # Might have to call BO and decide the width and send it together
        return channel

    def choose_channel_5_ghz(self):
        bestChannel = self.MAB_5_GHz.selectArm()
        self.channelReward_5_GHz = self.channelParameters_5_GHz[bestChannel].reward()
        self.MAB_5_GHz.updateArm(bestChannel, self.channelReward_5_GHz)
        channel = self.convert_idx_to_band(WiFiBand.BAND_5_GHz, bestChannel)
        # Might have to call BO and decide the width and send it together
        return channel

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

    def convert_idx_to_band(self, band, idx):
        if (band == WiFiBand.BAND_2_4_GHz):
            return idx+1
        elif (band == WiFiBand.BAND_5_GHz):
            return self.idxToChan_5_GHz[idx]
        elif (band == WiFiBand.BAND_6_GHz):
            logging.error("Not yet implemented...")
            return 0
        else:
            logging.error("Not a recognised index...")
        return 0

    def simulate_radio_input(self, file: str):
        parser = CSVParserSO()
        beacons = parser.parseCSV(file)
        print("Sensing Orchestra ", file)
        for beacon in beacons:
            band = beacon[APLog.BAND]
            channel = self.convert_band_to_idx(band, beacon[APLog.CHANNEL])
            client = beacon[APLog.AP_ID]
            # rssi = beacon[APLog.AVG_RSSI_DBM]
            timestamp = str(beacon[APLog.TIMESTAMP])
            snr = float(beacon[APLog.AVG_CLIENT_SNR_DB])
            noiseFloor = float(beacon[APLog.NOISE_FLOOR_DBM])
            nwifi_detected = beacon[APLog.NWIFI_DETECTED].lower() == 'true'
            throughput = float(beacon[APLog.THROUGHPUT_AVG_Mbps])
            qoe = float(beacon[APLog.MEAN_QOE])
            retry = float(beacon[APLog.P95_RETRY_PCT])
            PER = float(beacon[APLog.UL_PER])
            tx_power = float(beacon[APLog.TX_POWER_DBM])
            busy_time = float(beacon[APLog.BUSY_TIME])
            total_time = float(beacon[APLog.TOTAL_TIME])
            nwifi_type = beacon[APLog.NWIFI_TYPE]
            airtime = float(beacon[APLog.AIRTIME_UTILIZATION])
            if (band == WiFiBand.BAND_2_4_GHz):
                self.channelParameters_2_4_GHz[channel].update_channel_2_4_ghz(
                    snr, noiseFloor, throughput, client, qoe, retry, PER, tx_power, busy_time, total_time, nwifi_detected, timestamp)
                self.eventLoop.detect_event_2_4_ghz(timestamp, band, beacon[APLog.CHANNEL], airtime, retry,
                                                    nwifi_detected, nwifi_type, tx_power)
            elif (band == WiFiBand.BAND_5_GHz):
                self.channelParameters_5_GHz[channel].update_channel_5_ghz(
                    snr, noiseFloor, throughput, client, qoe, retry, PER, tx_power, busy_time, total_time, nwifi_type, timestamp)
                self.eventLoop.detect_event_5_ghz(timestamp, band, beacon[APLog.CHANNEL], nwifi_type, airtime, retry
                                                  )
            elif (band == WiFiBand.BAND_6_GHz):
                # self.channelParameters[channel].updateChannel_6_GHz(
                #     rssi, noiseFloor, throughput, client, qoe, tx_power, busy_time, total_time)
                logging.error("Might implement 6GHz in future...")
            else:
                logging.error("Not a recognised band...")
            isDFSPresent = not self.channelParameters_5_GHz[channel].get_dfs_state()  # 1 DFS radar is not present
            if (band == WiFiBand.BAND_5_GHz and isDFSPresent):
                logging.warning(f"DFS detected on channel {channel}...")
                self.DFStimer.start_or_reset(beacon[APLog.CHANNEL])
                break

    def print_channel_parameters_2_4_ghz(self):
        for channel in self.channelParameters_2_4_GHz:
            channel.print_channel()

    def clear_dfs_clients_5_ghz(self, channel):
        print(f"Resetting DFS state for channel: {channel}")
        idx = self.convert_band_to_idx(WiFiBand.BAND_5_GHz, channel)
        self.channelParameters_5_GHz[idx].clear_dfs_clients()

    def print_channel_parameters_5_ghz(self):
        for channel in self.channelParameters_5_GHz:
            channel.print_channel()

    def save_json_metrics(self):
        file = "metrics.json"
        all_metrics = {}

        qoe_sum = avg_retry_sum = per_sum = util_sum = 0.0
        count = 0

        # === 2.4 GHz Channels ===
        if hasattr(self, "channels_2_4_GHz"):
            all_metrics["2.4_GHz"] = {}
            for ch in self.channelParameters_2_4_GHz:
                qoe, avg_retry, PER, utilization = ch.get_channel_metrics()
                all_metrics["2.4_GHz"][f"Channel_{ch.get_channel()}"] = {
                    "QoE": qoe,
                    "Average_Retry": avg_retry,
                    "PER": PER,
                    "Channel_Utilization": utilization
                }
                qoe_sum += qoe
                avg_retry_sum += avg_retry
                per_sum += PER
                util_sum += utilization
                if (qoe != 0):
                    count += 1

        if count > 0:
            all_metrics["2.4_GHz"]["Average"] = {
                "QoE": qoe_sum / count,
                "Average_Retry": avg_retry_sum / count,
                "PER": per_sum / count,
                "Channel_Utilization": util_sum / count
            }

        qoe_sum = avg_retry_sum = per_sum = util_sum = 0.0
        count = 0

        # === 5 GHz Channels ===
        if hasattr(self, "channels_5_GHz"):
            all_metrics["5_GHz"] = {}
            for ch in self.channelParameters_5_GHz:
                qoe, avg_retry, PER, utilization = ch.get_channel_metrics()
                all_metrics["5_GHz"][f"Channel_{ch.get_channel()}"] = {
                    "QoE": qoe,
                    "Average_Retry": avg_retry,
                    "PER": PER,
                    "Channel_Utilization": utilization
                }

                qoe_sum += qoe
                avg_retry_sum += avg_retry
                per_sum += PER
                util_sum += utilization
                if (qoe != 0):
                    count += 1

        if count > 0:
            all_metrics["5_GHz"]["Average"] = {
                "QoE": qoe_sum / count,
                "Average_Retry": avg_retry_sum / count,
                "PER": per_sum / count,
                "Channel_Utilization": util_sum / count
            }

        all_metrics["timestamp"] = datetime.now().isoformat()
        with open(file, "w") as f:
            json.dump(all_metrics, f, indent=4)

        logging.info(f"[INFO] All channel metrics saved to {file}")

    def close_orchestra(self):
        self.print_channel_parameters_2_4_ghz()
        self.print_channel_parameters_5_ghz()
        self.save_json_metrics()
        self.DFStimer.cancel_all()
        self.isRunning = False


def monitor():
    process = psutil.Process(os.getpid())
    avgCPU = 0
    avgRAM = 0
    avgcount = 0
    maxCPU = 0
    maxRAM = 0
    minCPU = 1000
    minRAM = 1000
    while True:
        cpu = process.cpu_percent(interval=1)          # CPU %
        avgCPU += cpu
        maxCPU = max(cpu, maxCPU)
        minCPU = min(cpu, minCPU)
        ram = process.memory_info().rss / (1024**2)    # RAM in MB
        avgRAM += ram
        maxRAM = max(ram, maxRAM)
        minRAM = min(ram, minRAM)
        avgcount += 1
        print(f"[USAGE] CPU={cpu}% avg {avgCPU/avgcount:.2f} max {maxCPU:.2f} min {minCPU:.2f} RAM={ram:.2f} avg {avgRAM/avgcount:.2f} max {maxRAM:.2f} min {minRAM:.2f} MB")


if __name__ == "__main__":
    rrm = SensingOrchestra()
    thread = threading.Thread(target=rrm.start)
    # monitor_thread = threading.Thread(target=monitor, daemon=True)
    # monitor_thread.start()
    try:
        thread.start()
        time.sleep(100)
        raise Exception
    except Exception as ex:
        rrm.close_orchestra()
