BAND_2_4_CHANNELS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
BAND_5_CHANNELS = [36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112,
                   116, 120, 124, 128, 132, 136, 140, 144, 149, 153, 157, 161, 165]
BAND_6_CHANNELS = [1,   5,   9,  13,  17,  21,  25,  29,  33,  37,  41,  45, 49,  53,  57,  61,  65,  69,  73,  77,  81,  85,  89,  93, 97, 101, 105, 109,
                   113, 117, 121, 125, 129, 133, 137, 141, 145, 149, 153, 157, 161, 165, 169, 173, 177, 181, 185, 189, 193, 197, 201, 205, 209, 213, 217, 221, 225, 229, 233]


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
        self.DFS = 0  # TODO: Update all channels which lie in DFS as 1
        print("Creating band:", band, "channel:", channel)

    # Define reward function based on channel parameters
    def reward(self):
        snr_score = max(0, min(self.avgClientSNR / 50, 1))
        throughput_score = max(0, min(self.avgThroughput / 100, 1))
        utilization_penalty = 1 - min(self.channelUtilization, 1)
        interference_penalty = 1 - min(self.interference, 1)
        qoe_score = self.qoe / 5.0
        noise_score = max(0, min((-self.noiseFloor - 80) / 20, 1))
        client_penalty = 1 / (1 + len(self.clients))
        estReward = (0.25 * throughput_score +
                     0.2 * snr_score +
                     0.15 * qoe_score +
                     0.15 * utilization_penalty +
                     0.1 * interference_penalty +
                     0.1 * noise_score +
                     0.05 * client_penalty)
        return estReward

    def updateChannel_2_4_GHz(self, rssi, noiseFloor, throughput, client, qoe, tx_power, busy_time, total_time, nwifi_detected):
        self.avgCount += 1
        SNR = rssi - noiseFloor
        self.noiseFloor = noiseFloor
        self.avgClientSNR = ((self.avgCount-1)*self.avgClientSNR+SNR)/self.avgCount
        self.avgThroughput = ((self.avgCount-1)*self.avgThroughput+throughput)/self.avgCount
        self.clients.add(client)
        self.qoe = ((self.avgCount-1)*self.qoe+qoe)/self.avgCount
        self.channelUtilization = ((self.avgCount-1)*self.channelUtilization+(busy_time/total_time))/self.avgCount
        if nwifi_detected:
            self.interference += self.inteferenceWeight  # add a value for this

    def updateChannel_5_GHz(self, rssi, noiseFloor, throughput, client, qoe, tx_power, busy_time, total_time):
        self.avgCount += 1
        SNR = rssi - noiseFloor
        self.noiseFloor = noiseFloor
        self.avgClientSNR = ((self.avgCount-1)*self.avgClientSNR+SNR)/self.avgCount
        self.avgThroughput = ((self.avgCount-1)*self.avgThroughput+throughput)/self.avgCount
        self.clients.add(client)
        self.qoe = ((self.avgCount-1)*self.qoe+qoe)/self.avgCount
        self.channelUtilization = ((self.avgCount-1)*self.channelUtilization+(busy_time/total_time))/self.avgCount

    def updateChannel_6_GHz(self, rssi, noiseFloor, throughput, client, qoe, tx_power, busy_time, total_time):
        self.avgCount += 1
        SNR = rssi - noiseFloor
        self.noiseFloor = noiseFloor
        self.avgClientSNR = ((self.avgCount-1)*self.avgClientSNR+SNR)/self.avgCount
        self.avgThroughput = ((self.avgCount-1)*self.avgThroughput+throughput)/self.avgCount
        self.clients.add(client)
        self.qoe = ((self.avgCount-1)*self.qoe+qoe)/self.avgCount
        self.channelUtilization = ((self.avgCount-1)*self.channelUtilization+(busy_time/total_time))/self.avgCount

    def printChannel(self):
        print("--------------------------------\n")
        print(f"{'BAND:':25} {self.band}")
        print(f"{'CHANNEL:':25} {self.channel}")
        print(f"{'NOISE FLOOR (dBm):':25} {self.noiseFloor}")
        print(f"{'AVG CLIENT SNR (dB):':25} {self.avgClientSNR}")
        print(f"{'AVG COUNT:':25} {self.avgCount}")
        print(f"{'AVG THROUGHPUT (Mbps):':25} {self.avgThroughput}")
        print(f"{'CHANNEL UTILIZATION:':25} {self.channelUtilization}")
        print(f"{'INTERFERENCE:':25} {self.interference}")
        print(f"{'CLIENTS:':25} {self.clients}")
        print(f"{'QOE:':25} {self.qoe}")
        print(f"{'TX POWER (dBm):':25} {self.tx_power}")
        print(f"{'CHANNEL WIDTH (MHz):':25} {self.channel_width}")
        print(f"{'INTERFERENCE WEIGHT:':25} {self.inteferenceWeight}")
        print(f"{'DFS:':25} {self.DFS}")
        print()
