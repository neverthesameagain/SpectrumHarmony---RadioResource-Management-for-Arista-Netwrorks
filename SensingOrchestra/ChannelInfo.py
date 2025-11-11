from datetime import datetime
import math
import time
import logging
from utils.WiFiBandEnum import DFSState

BAND_2_4_CHANNELS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
BAND_5_CHANNELS = [36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112,
                   116, 120, 124, 128, 132, 136, 140, 144, 149, 153, 157, 161, 165]
BAND_6_CHANNELS = [1,   5,   9,  13,  17,  21,  25,  29,  33,  37,  41,  45, 49,  53,  57,  61,  65,  69,  73,  77,  81,  85,  89,  93, 97, 101, 105, 109,
                   113, 117, 121, 125, 129, 133, 137, 141, 145, 149, 153, 157, 161, 165, 169, 173, 177, 181, 185, 189, 193, 197, 201, 205, 209, 213, 217, 221, 225, 229, 233]

BAND_5_DFS_CHANNELS = [52, 56, 60, 64, 100, 104, 108, 112,
                       116, 120, 124, 128, 132, 136, 140, 144]

logger = logging.getLogger()
logging.basicConfig(filename="output.log", level=logging.DEBUG)
file_handler = logging.FileHandler("events.log")
file_handler.setLevel(logging.WARNING)
logger.addHandler(file_handler)


class ChannelInfo:
    def __init__(self, band, channel):
        self.band = band
        self.channel = channel
        self.noiseFloor = -95  # Change it if required
        self.avgClientSNR = 0
        self.avgCount = 0
        self.avgThroughput = 0
        self.channelUtilization = 0
        self.interference = 0
        self.clients = set()
        self.qoe = 0
        self.avg_retry = 0
        self.avg_PER = 0
        self.avg_tx_power = 0
        self.max_tx = 1
        self.channel_width = 0
        self.inteferenceWeight = 1
        self.DFS = 1 if self.channel in BAND_5_DFS_CHANNELS else 0
        self.DFSState = DFSState.AVAILABLE
        self.DFSClients = set()
        self.alpha = self.getAlpha()
        self.threshold = 0.2

        self.cusum_pos = {}
        self.cusum_neg = {}
        self.cusum_threshold = 5.0
        self.cusum_k = 0.7
        self.alert_cooldown = 5.0
        self.last_alert_time = {}
        logging.info(f"Creating band: {band} channel : {channel}")

    def getChannel(self):
        return self.channel

    # Define reward function based on channel parameters
    def reward(self):
        if (not self.DFSState.value):
            return 0
        snr_score = max(0, min(self.avgClientSNR / 50, 1))
        throughput_score = max(0, min(self.avgThroughput / 100, 1))
        utilization_penalty = 1 - min(self.channelUtilization, 1)
        interference_penalty = 1 - min(self.interference, 1)
        qoe_score = self.qoe / 5.0
        noise_score = max(0, min((-self.noiseFloor - 80) / 20, 1))
        client_penalty = 1 / (1 + len(self.clients))
        estReward = (0.25 * (1 - throughput_score) +
                     0.2 * (1 - snr_score) +
                     0.15 * (1 - qoe_score) +
                     0.15 * utilization_penalty +
                     0.05 * interference_penalty +
                     0.05 * (self.avg_tx_power / self.max_tx) +
                     0.1 * (1 - noise_score) +
                     0.05 * (1 - client_penalty))
        return estReward

    def updateEWMA(self, prev_value, new_value, alpha):
        return alpha * new_value + (1 - alpha) * prev_value

    def getAlpha(self):
        N = self.avgCount
        return min(0.3, 2 / (N + 1))

    def detect_change(self, name, new_value, avg_value, threshold=0.2):
        if avg_value == 0:
            return

        deviation_ratio = abs(new_value - avg_value) / abs(avg_value)

        if deviation_ratio > threshold:
            now = time.time()
            last_time = self.last_alert_time.get(name, 0)

            if now - last_time > self.alert_cooldown:
                logging.warning(
                    f"[ALERT][{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}][Channel {self.channel}] Sudden change in {name}: {new_value:.2f} (avg={avg_value:.2f}, dev={deviation_ratio*100:.1f}%)")
                self.last_alert_time[name] = now

    def cusum_update(self, name, new_value, mean):
        if name not in self.cusum_pos:
            self.cusum_pos[name] = 0
            self.cusum_neg[name] = 0
            self.last_alert_time[name] = 0

        deviation = new_value - mean

        self.cusum_pos[name] = max(0, self.cusum_pos[name] + deviation - self.cusum_k)
        self.cusum_neg[name] = max(0, self.cusum_neg[name] - deviation - self.cusum_k)

        now = time.time()
        if self.cusum_pos[name] > self.cusum_threshold:
            if now - self.last_alert_time[name] > self.alert_cooldown:
                logging.warning(
                    f"[CUSUM ALERT][{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}][Channel {self.channel}] {name} ↑ shift detected! deviation={deviation:.2f}")
                self.last_alert_time[name] = now
            self.cusum_pos[name] = 0

        elif self.cusum_neg[name] > self.cusum_threshold:
            if now - self.last_alert_time[name] > self.alert_cooldown:
                logging.warning(
                    f"[CUSUM ALERT][{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}][Channel {self.channel}] {name} ↓ shift detected! deviation={deviation:.2f}")
                self.last_alert_time[name] = now
            self.cusum_neg[name] = 0

    def updateChannel_2_4_GHz(self, snr, noiseFloor, throughput, client, qoe, retry, PER, tx_power, busy_time, total_time, nwifi_detected):
        self.avgCount += 1
        self.clients.add(client)
        self.alpha = self.getAlpha()
        self.noiseFloor = self.updateEWMA(self.noiseFloor, noiseFloor, self.alpha)
        self.avgClientSNR = self.updateEWMA(self.avgClientSNR, snr, self.alpha)
        self.avgThroughput = self.updateEWMA(self.avgThroughput, throughput, self.alpha)
        self.max_tx = max(self.max_tx, tx_power)
        self.avg_tx_power = self.updateEWMA(self.avg_tx_power, tx_power, self.alpha)
        self.qoe = self.updateEWMA(self.qoe, qoe, self.alpha)
        self.avg_retry = self.updateEWMA(self.avg_retry, retry, self.alpha)
        self.avg_PER = self.updateEWMA(self.avg_PER, PER, self.alpha)
        self.channelUtilization = self.updateEWMA(self.channelUtilization, busy_time / total_time, self.alpha)
        if nwifi_detected:
            self.interference += self.inteferenceWeight  # add a value for this

        self.detect_change("SNR", snr, self.avgClientSNR)
        self.detect_change("TX_power", tx_power, self.avg_tx_power)
        self.detect_change("Throughput", throughput, self.avgThroughput)
        self.detect_change("NoiseFloor", noiseFloor, self.noiseFloor)
        self.detect_change("QoE", qoe, self.qoe)
        self.detect_change("P95_retry", retry, self.avg_retry)
        self.detect_change("P95_PER", PER, self.avg_PER)

        self.cusum_update("SNR", snr, self.avgClientSNR)
        self.cusum_update("TX_power", tx_power, self.avg_tx_power)
        self.cusum_update("Throughput", throughput, self.avgThroughput)
        self.cusum_update("NoiseFloor", noiseFloor, self.noiseFloor)
        self.cusum_update("QoE", qoe, self.qoe)
        self.cusum_update("P95_retry", retry, self.avg_retry)
        self.cusum_update("P95_PER", PER, self.avg_PER)

    def updateChannel_5_GHz(self, snr, noiseFloor, throughput, client, qoe, retry, PER, tx_power, busy_time, total_time, nwifi_type):
        # TODO: call afunction to check radar present or not
        if (self.DFSState == DFSState.NOT_AVAILABLE):
            return
        if (self.DFS and nwifi_type == "Radar"):
            self.DFSClients.add(client)
            self.DFSState = DFSState.NOT_AVAILABLE
            logging.warning("DFS Radar detected...")
            return
        self.avgCount += 1
        self.clients.add(client)
        self.alpha = self.getAlpha()
        self.noiseFloor = self.updateEWMA(self.noiseFloor, noiseFloor, self.alpha)
        self.avgClientSNR = self.updateEWMA(self.avgClientSNR, snr, self.alpha)
        self.avgThroughput = self.updateEWMA(self.avgThroughput, throughput, self.alpha)
        self.max_tx = max(self.max_tx, tx_power)
        self.avg_tx_power = self.updateEWMA(self.avg_tx_power, tx_power, self.alpha)
        self.qoe = self.updateEWMA(self.qoe, qoe, self.alpha)
        self.avg_retry = self.updateEWMA(self.avg_retry, retry, self.alpha)
        self.avg_PER = self.updateEWMA(self.avg_PER, PER, self.alpha)
        self.channelUtilization = self.updateEWMA(self.channelUtilization, busy_time / total_time, self.alpha)

        self.detect_change("SNR", snr, self.avgClientSNR)
        self.detect_change("TX_power", tx_power, self.avg_tx_power)
        self.detect_change("Throughput", throughput, self.avgThroughput)
        self.detect_change("NoiseFloor", noiseFloor, self.noiseFloor)
        self.detect_change("QoE", qoe, self.qoe)
        self.detect_change("P95_retry", retry, self.avg_retry)
        self.detect_change("P95_PER", PER, self.avg_PER)

        self.cusum_update("SNR", snr, self.avgClientSNR)
        self.cusum_update("TX_power", tx_power, self.avg_tx_power)
        self.cusum_update("Throughput", throughput, self.avgThroughput)
        self.cusum_update("NoiseFloor", noiseFloor, self.noiseFloor)
        self.cusum_update("QoE", qoe, self.qoe)
        self.cusum_update("P95_retry", retry, self.avg_retry)
        self.cusum_update("P95_PER", PER, self.avg_PER)

    def clearDFSClients(self):
        self.DFSClients = set()
        self.DFSState = DFSState.AVAILABLE

    def getDFSState(self):
        return self.DFSState.value  # 1 means no dfs radar present

    def updateChannel_6_GHz(self, snr, noiseFloor, throughput, client, qoe, retry, PER, tx_power, busy_time, total_time):
        self.avgCount += 1
        self.clients.add(client)
        self.alpha = self.getAlpha()
        self.noiseFloor = self.updateEWMA(self.noiseFloor, noiseFloor, self.alpha)
        self.avgClientSNR = self.updateEWMA(self.avgClientSNR, snr, self.alpha)
        self.avgThroughput = self.updateEWMA(self.avgThroughput, throughput, self.alpha)
        self.max_tx = max(self.max_tx, tx_power)
        self.avg_tx_power = self.updateEWMA(self.avg_tx_power, tx_power, self.alpha)
        self.qoe = self.updateEWMA(self.qoe, qoe, self.alpha)
        self.avg_retry = self.updateEWMA(self.avg_retry, retry, self.alpha)
        self.avg_PER = self.updateEWMA(self.avg_PER, PER, self.alpha)
        self.channelUtilization = self.updateEWMA(self.channelUtilization, busy_time / total_time, self.alpha)

        self.detect_change("SNR", snr, self.avgClientSNR)
        self.detect_change("TX_power", tx_power, self.avg_tx_power)
        self.detect_change("Throughput", throughput, self.avgThroughput)
        self.detect_change("NoiseFloor", noiseFloor, self.noiseFloor)
        self.detect_change("QoE", qoe, self.qoe)
        self.detect_change("P95_retry", retry, self.avg_retry)
        self.detect_change("P95_PER", PER, self.avg_PER)

        self.cusum_update("SNR", snr, self.avgClientSNR)
        self.cusum_update("TX_power", tx_power, self.avg_tx_power)
        self.cusum_update("Throughput", throughput, self.avgThroughput)
        self.cusum_update("NoiseFloor", noiseFloor, self.noiseFloor)
        self.cusum_update("QoE", qoe, self.qoe)
        self.cusum_update("P95_retry", retry, self.avg_retry)
        self.cusum_update("P95_PER", PER, self.avg_PER)

    def getChannelMetrics(self):
        return self.qoe, self.avg_retry, self.avg_PER, self.channelUtilization

    def printChannel(self):
        logging.info("--------------------------------\n")
        logging.info(f"[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {self.band}  {'BAND:':25} {self.band}")
        logging.info(f"[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {self.band}  {'CHANNEL:':25} {self.channel}")
        logging.info(
            f"[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {self.band}  {'NOISE FLOOR (dBm):':25} {self.noiseFloor}")
        logging.info(
            f"[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {self.band}  {'AVG CLIENT SNR (dB):':25} {self.avgClientSNR}")
        logging.info(f"[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {self.band}  {'AVG COUNT:':25} {self.avgCount}")
        logging.info(
            f"[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {self.band}  {'AVG THROUGHPUT (Mbps):':25} {self.avgThroughput}")
        logging.info(
            f"[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {self.band}  {'CHANNEL UTILIZATION:':25} {self.channelUtilization}")
        logging.info(f"[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {self.band}  {'INTERFERENCE:':25} {self.interference}")
        logging.info(f"[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {self.band}  {'CLIENTS:':25} {self.clients}")
        logging.info(f"[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {self.band}  {'QOE:':25} {self.qoe}")
        logging.info(
            f"[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {self.band}  {'TX POWER (dBm):':25} {self.avg_tx_power}")
        logging.info(
            f"[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {self.band}  {'CHANNEL WIDTH (MHz):':25} {self.channel_width}")
        logging.info(
            f"[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {self.band}  {'INTERFERENCE WEIGHT:':25} {self.inteferenceWeight}")
        logging.info(f"[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {self.band}  {'DFS:':25} {self.DFS}")
        logging.info("")
