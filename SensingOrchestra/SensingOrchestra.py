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
        self.numChannels = 0
        self.channelParameters = []
        print("Initiating Sensing Orchestra...")

    def initiateChannels(self):
        if (self.band == WiFiBand.BAND_2_4_GHz):
            self.numChannels = 14
            self.channels = BAND_2_4_CHANNELS
        elif (self.band == WiFiBand.BAND_5_GHz):
            self.numChannels = 24
            self.channels = BAND_5_CHANNELS
        elif (self.band == WiFiBand.BAND_6_GHz):
            print("Might implement 6GHz in future...")
        else:
            print("Not a recognised band...")
        for i in range(self.numChannels):
            self.channelParameters.append(ChannelInfo(self.band, self.channels[i]))

    def initializeMAB(self):
        self.MAB = MAB(self.numChannels)
        rewards = []
        for channel in self.channelParameters:
            rewards.append(channel.reward())
        self.MAB.initializeArms(rewards)

    def chooseChannel(self):
        bestChannel = self.MAB.selectArm()
        channelReward = self.channelParameters[bestChannel].reward()
        self.MAB.updateArm(bestChannel, channelReward)
        channel = self.convertIdxToBand(bestChannel)
        # Might have to call BO and decide the width and send it together
        return channel

    def convertbandToIdx(self, channel):
        if (self.band == WiFiBand.BAND_2_4_GHz):
            return channel
        elif (self.band == WiFiBand.BAND_5_GHz):
            return int((channel - 36)/4)
        elif (self.band == WiFiBand.BAND_6_GHz):
            return int((channel - 1) / 4)
        else:
            print("Not a recognised band...")
        return 0

    def convertIdxToBand(self, channel):
        if (self.band == WiFiBand.BAND_2_4_GHz):
            return channel
        elif (self.band == WiFiBand.BAND_5_GHz):
            return 4*channel + 36
        elif (self.band == WiFiBand.BAND_6_GHz):
            return 4*channel + 1
        else:
            print("Not a recognised band...")
        return 0

    def simulateRadioInput(self, file: str):
        parser = CSVParser()
        beacons = parser.parseCSV(file)
        for beacon in beacons:
            channel = self.convertbandToIdx(beacon[APLog.CHANNEL])
            client = beacon[APLog.AP_ID]
            rssi = beacon[APLog.AVG_RSSI_DBM]
            noiseFloor = float(beacon[APLog.NOISE_FLOOR_DBM])
            nwifi_detected = beacon[APLog.NWIFI_DETECTED].lower() == 'true'
            throughput = float(beacon[APLog.THROUGHPUT_AVG_Mbps])
            qoe = float(beacon[APLog.MEAN_QOE])
            tx_power = float(beacon[APLog.TX_POWER_DBM])
            busy_time = float(beacon[APLog.BUSY_TIME])
            total_time = float(beacon[APLog.TOTAL_TIME])
            if (self.band == WiFiBand.BAND_2_4_GHz):
                self.channelParameters[channel].updateChannel_2_4_GHz(
                    rssi, noiseFloor, throughput, client, qoe, tx_power, busy_time, total_time, nwifi_detected)
            elif (self.band == WiFiBand.BAND_5_GHz):
                self.channelParameters[channel].updateChannel_5_GHz(
                    rssi, noiseFloor, throughput, client, qoe, tx_power, busy_time, total_time)
            elif (self.band == WiFiBand.BAND_6_GHz):
                self.channelParameters[channel].updateChannel_6_GHz(
                    rssi, noiseFloor, throughput, client, qoe, tx_power, busy_time, total_time)
                print("Might implement 6GHz in future...")
            else:
                print("Not a recognised band...")

    def printChannelParameters(self):
        for channel in self.channelParameters:
            channel.printChannel()


if __name__ == "__main__":
    rrm = SensingOrchestra(WiFiBand.BAND_5_GHz)
    rrm.initiateChannels()
    rrm.initializeMAB()
    file_path = os.path.join(base_dir, "data", "ap_logs_5GHz.csv")
    rrm.simulateRadioInput(file_path)
    rrm.printChannelParameters()
    channel = rrm.chooseChannel()
    print(channel)
