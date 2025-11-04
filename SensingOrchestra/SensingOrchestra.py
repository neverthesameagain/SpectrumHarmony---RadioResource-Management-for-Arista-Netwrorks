from ChannelInfo import *
import utils.APLogsColumns as APLog
from utils.WiFiBandEnum import WiFiBand
from utils.CSVParser import CSVParser
from MAB import MAB
import os

base_dir = os.path.dirname(__file__)


class SensingOrchestra:
    def __init__(self, band):
        self.band = band
        self.numChannels_2_4_GHz = 0
        self.channelParameters_2_4_GHz = []
        self.numChannels_5s_GHz = 0
        self.channelParameters_5_GHz = []
        print("Initiating Sensing Orchestra...")

    def initiateChannels(self):
        self.numChannels_2_4_GHz = 14
        self.channels_2_4_GHz = BAND_2_4_CHANNELS
        self.numChannels_5_GHz = 24
        self.channels_5_GHz = BAND_5_CHANNELS
        self.chanToIdx_5_GHz = {ch: idx for idx, ch in enumerate(BAND_5_CHANNELS)}
        self.idxToChan_5_GHz = {idx: ch for idx, ch in enumerate(BAND_5_CHANNELS)}
        print("Might implement 6GHz in future...")
        for i in range(self.numChannels_2_4_GHz):
            self.channelParameters_2_4_GHz.append(ChannelInfo(WiFiBand.BAND_2_4_GHz, self.channels_2_4_GHz[i]))
        for i in range(self.numChannels_5_GHz):
            self.channelParameters_5_GHz.append(ChannelInfo(WiFiBand.BAND_5_GHz, self.channels_5_GHz[i]))

    def initializeMAB(self):
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

    def chooseChannel_2_4_GHz(self):
        bestChannel = self.MAB_2_4_GHz.selectArm()
        channelReward = self.channelParameters_2_4_GHz[bestChannel].reward()
        self.MAB_2_4_GHz.updateArm(bestChannel, channelReward)
        channel = self.convertIdxToBand(WiFiBand.BAND_2_4_GHz, bestChannel)
        # Might have to call BO and decide the width and send it together
        return channel

    def chooseChannel_5_GHz(self):
        bestChannel = self.MAB_5_GHz.selectArm()
        channelReward = self.channelParameters_5_GHz[bestChannel].reward()
        self.MAB_5_GHz.updateArm(bestChannel, channelReward)
        channel = self.convertIdxToBand(WiFiBand.BAND_5_GHz, bestChannel)
        # Might have to call BO and decide the width and send it together
        return channel

    def convertbandToIdx(self, band, channel):
        if (band == WiFiBand.BAND_2_4_GHz):
            return channel-1
        elif (band == WiFiBand.BAND_5_GHz):
            return self.chanToIdx_5_GHz[channel]-1
        elif (band == WiFiBand.BAND_6_GHz):
            print("Not yet implemented...")
            return 0
        else:
            print("Not a recognised band...")
        return 0

    def convertIdxToBand(self, band, idx):
        if (band == WiFiBand.BAND_2_4_GHz):
            return idx+1
        elif (band == WiFiBand.BAND_5_GHz):
            return self.idxToChan_5_GHz[idx+1]
        elif (band == WiFiBand.BAND_6_GHz):
            print("Not yet implemented...")
            return 0
        else:
            print("Not a recognised index...")
        return 0

    def simulateRadioInput(self, file: str):
        parser = CSVParser()
        beacons = parser.parseCSV(file)
        for beacon in beacons:
            band = beacon[APLog.BAND]
            channel = self.convertbandToIdx(band, beacon[APLog.CHANNEL])
            client = beacon[APLog.AP_ID]
            # rssi = beacon[APLog.AVG_RSSI_DBM]
            snr = float(beacon[APLog.AVG_CLIENT_SNR_DB])
            noiseFloor = float(beacon[APLog.NOISE_FLOOR_DBM])
            nwifi_detected = beacon[APLog.NWIFI_DETECTED].lower() == 'true'
            throughput = float(beacon[APLog.THROUGHPUT_AVG_Mbps])
            qoe = float(beacon[APLog.MEAN_QOE])
            tx_power = float(beacon[APLog.TX_POWER_DBM])
            busy_time = float(beacon[APLog.BUSY_TIME])
            total_time = float(beacon[APLog.TOTAL_TIME])
            if (band == WiFiBand.BAND_2_4_GHz):
                self.channelParameters_2_4_GHz[channel].updateChannel_2_4_GHz(
                    snr, noiseFloor, throughput, client, qoe, tx_power, busy_time, total_time, nwifi_detected)
            elif (band == WiFiBand.BAND_5_GHz):
                self.channelParameters_5_GHz[channel].updateChannel_5_GHz(
                    snr, noiseFloor, throughput, client, qoe, tx_power, busy_time, total_time)
            elif (band == WiFiBand.BAND_6_GHz):
                # self.channelParameters[channel].updateChannel_6_GHz(
                #     rssi, noiseFloor, throughput, client, qoe, tx_power, busy_time, total_time)
                print("Might implement 6GHz in future...")
            else:
                print("Not a recognised band...")

    def printChannelParameters_2_4_GHz(self):
        for channel in self.channelParameters_2_4_GHz:
            channel.printChannel()

    def printChannelParameters_5_GHz(self):
        for channel in self.channelParameters_5_GHz:
            channel.printChannel()


if __name__ == "__main__":
    rrm = SensingOrchestra(WiFiBand.BAND_5_GHz)
    rrm.initiateChannels()
    file_path = os.path.join(base_dir, "data", "apLogs.csv")
    rrm.simulateRadioInput(file_path)
    rrm.initializeMAB()
    # rrm.simulateRadioInput(file_path)
    print("For 5GHz...")
    rrm.printChannelParameters_5_GHz()
    channel_5GHz = rrm.chooseChannel_5_GHz()

    print("For 2.4GHz...")
    rrm.printChannelParameters_2_4_GHz()
    channel_2_4_GHz = rrm.chooseChannel_2_4_GHz()
    print("Best 5GHz channel...", channel_5GHz)
    print("Best 2.4GHz channel...", channel_2_4_GHz)
