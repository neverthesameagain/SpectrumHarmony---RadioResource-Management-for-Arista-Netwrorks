from utils.WiFiBandEnum import DFSState

BAND_2_4_CHANNELS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
BAND_5_CHANNELS = [36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112,
                   116, 120, 124, 128, 132, 136, 140, 144, 149, 153, 157, 161, 165]
BAND_6_CHANNELS = [1,   5,   9,  13,  17,  21,  25,  29,  33,  37,  41,  45, 49,  53,  57,  61,  65,  69,  73,  77,  81,  85,  89,  93, 97, 101, 105, 109,
                   113, 117, 121, 125, 129, 133, 137, 141, 145, 149, 153, 157, 161, 165, 169, 173, 177, 181, 185, 189, 193, 197, 201, 205, 209, 213, 217, 221, 225, 229, 233]

BAND_5_DFS_CHANNELS = [52, 56, 60, 64, 100, 104, 108, 112,
                       116, 120, 124, 128, 132, 136, 140, 144]


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
        self.tx_power = 0
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
        print("Creating band:", band, "channel:", channel)

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
                     0.1 * interference_penalty +
                     0.1 * (1 - noise_score) +
                     0.05 * (1 - client_penalty))
        return estReward

    def updateEWMA(self, prev_value, new_value, alpha):
        return alpha * new_value + (1 - alpha) * prev_value

    def getAlpha(self):
        N = self.avgCount
        return min(0.3, 2 / (N + 1))

    def detect_change(self, name, new_value, avg_value, threshold=0.2):
        if avg_value != 0 and abs(new_value - avg_value) / abs(avg_value) > threshold:
            print(f"[ALERT] Sudden change detected in {name}: {new_value:.2f} (avg={avg_value:.2f})")

    def cusum_update(self, name, new_value, mean):
        if name not in self.cusum_pos:
            self.cusum_pos[name] = 0
            self.cusum_neg[name] = 0

        deviation = new_value - mean

        self.cusum_pos[name] = max(0, self.cusum_pos[name] + deviation - self.cusum_k)
        self.cusum_neg[name] = max(0, self.cusum_neg[name] - deviation - self.cusum_k)

        if self.cusum_pos[name] > self.cusum_threshold:
            print(f"[CUSUM ALERT] {name} increasing shift detected! deviation={deviation:.2f}")
            self.cusum_pos[name] = 0
        elif self.cusum_neg[name] > self.cusum_threshold:
            print(f"[CUSUM ALERT] {name} decreasing shift detected! deviation={deviation:.2f}")
            self.cusum_neg[name] = 0

    def updateChannel_2_4_GHz(self, snr, noiseFloor, throughput, client, qoe, tx_power, busy_time, total_time, nwifi_detected):
        self.avgCount += 1
        self.clients.add(client)
        self.alpha = self.getAlpha()
        self.noiseFloor = self.updateEWMA(self.noiseFloor, noiseFloor, self.alpha)
        self.avgClientSNR = self.updateEWMA(self.avgClientSNR, snr, self.alpha)
        self.avgThroughput = self.updateEWMA(self.avgThroughput, throughput, self.alpha)
        self.qoe = self.updateEWMA(self.qoe, qoe, self.alpha)
        self.channelUtilization = self.updateEWMA(self.channelUtilization, busy_time / total_time, self.alpha)
        if nwifi_detected:
            self.interference += self.inteferenceWeight  # add a value for this

        self.detect_change("SNR", snr, self.avgClientSNR)
        self.detect_change("Throughput", throughput, self.avgThroughput)
        self.detect_change("NoiseFloor", noiseFloor, self.noiseFloor)
        self.detect_change("QoE", qoe, self.qoe)

        self.cusum_update("SNR", snr, self.avgClientSNR)
        self.cusum_update("Throughput", throughput, self.avgThroughput)
        self.cusum_update("NoiseFloor", noiseFloor, self.noiseFloor)
        self.cusum_update("QoE", qoe, self.qoe)

    def updateChannel_5_GHz(self, snr, noiseFloor, throughput, client, qoe, tx_power, busy_time, total_time, nwifi_type):
        if (self.DFSState == DFSState.NOT_AVAILABLE):
            return
        if (self.DFS and nwifi_type == "Radar"):
            self.DFSClients.add(client)
            self.DFSState = DFSState.NOT_AVAILABLE
            print("DFS Radar detected...")
            return
        self.avgCount += 1
        self.clients.add(client)
        self.alpha = self.getAlpha()
        self.noiseFloor = self.updateEWMA(self.noiseFloor, noiseFloor, self.alpha)
        self.avgClientSNR = self.updateEWMA(self.avgClientSNR, snr, self.alpha)
        self.avgThroughput = self.updateEWMA(self.avgThroughput, throughput, self.alpha)
        self.qoe = self.updateEWMA(self.qoe, qoe, self.alpha)
        self.channelUtilization = self.updateEWMA(self.channelUtilization, busy_time / total_time, self.alpha)

        self.detect_change("SNR", snr, self.avgClientSNR)
        self.detect_change("Throughput", throughput, self.avgThroughput)
        self.detect_change("NoiseFloor", noiseFloor, self.noiseFloor)
        self.detect_change("QoE", qoe, self.qoe)

        self.cusum_update("SNR", snr, self.avgClientSNR)
        self.cusum_update("Throughput", throughput, self.avgThroughput)
        self.cusum_update("NoiseFloor", noiseFloor, self.noiseFloor)
        self.cusum_update("QoE", qoe, self.qoe)

    def clearDFSClients(self):
        self.DFSClients = set()
        self.DFSState = DFSState.AVAILABLE

    def getDFSState(self):
        return self.DFSState.value # 1 means no dfs radar present

    def updateChannel_6_GHz(self, snr, noiseFloor, throughput, client, qoe, tx_power, busy_time, total_time):
        self.avgCount += 1
        self.clients.add(client)
        self.alpha = self.getAlpha()
        self.noiseFloor = self.updateEWMA(self.noiseFloor, noiseFloor, self.alpha)
        self.avgClientSNR = self.updateEWMA(self.avgClientSNR, snr, self.alpha)
        self.avgThroughput = self.updateEWMA(self.avgThroughput, throughput, self.alpha)
        self.qoe = self.updateEWMA(self.qoe, qoe, self.alpha)
        self.channelUtilization = self.updateEWMA(self.channelUtilization, busy_time / total_time, self.alpha)

        self.detect_change("SNR", snr, self.avgClientSNR)
        self.detect_change("Throughput", throughput, self.avgThroughput)
        self.detect_change("NoiseFloor", noiseFloor, self.noiseFloor)
        self.detect_change("QoE", qoe, self.qoe)

        self.cusum_update("SNR", snr, self.avgClientSNR)
        self.cusum_update("Throughput", throughput, self.avgThroughput)
        self.cusum_update("NoiseFloor", noiseFloor, self.noiseFloor)
        self.cusum_update("QoE", qoe, self.qoe)

    def printChannel(self):
        print("--------------------------------\n")
        print(f"{self.band}  {'BAND:':25} {self.band}")
        print(f"{self.band}  {'CHANNEL:':25} {self.channel}")
        print(f"{self.band}  {'NOISE FLOOR (dBm):':25} {self.noiseFloor}")
        print(f"{self.band}  {'AVG CLIENT SNR (dB):':25} {self.avgClientSNR}")
        print(f"{self.band}  {'AVG COUNT:':25} {self.avgCount}")
        print(f"{self.band}  {'AVG THROUGHPUT (Mbps):':25} {self.avgThroughput}")
        print(f"{self.band}  {'CHANNEL UTILIZATION:':25} {self.channelUtilization}")
        print(f"{self.band}  {'INTERFERENCE:':25} {self.interference}")
        print(f"{self.band}  {'CLIENTS:':25} {self.clients}")
        print(f"{self.band}  {'QOE:':25} {self.qoe}")
        print(f"{self.band}  {'TX POWER (dBm):':25} {self.tx_power}")
        print(f"{self.band}  {'CHANNEL WIDTH (MHz):':25} {self.channel_width}")
        print(f"{self.band}  {'INTERFERENCE WEIGHT:':25} {self.inteferenceWeight}")
        print(f"{self.band}  {'DFS:':25} {self.DFS}")
        print()
