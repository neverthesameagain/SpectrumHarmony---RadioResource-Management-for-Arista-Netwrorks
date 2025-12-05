import networkx as nx
import ControlLoops.utils.APLogsColumns as APLog
from SensingOrchestra.ChannelInfo import BAND_5_CHANNELS
from SensingOrchestra.utilsSO.WiFiBandEnum import WiFiBand
from .utils.CSVParser import CSVParser
import logging
import os

logging.basicConfig(filename="output.log", level=logging.DEBUG)
base_dir = os.path.dirname(__file__)


class InterferenceGraph():
    _instance = None

    def __init__(self):
        print("Interference graph...")
        self.graph_2_4_Ghz = nx.Graph()
        self.graph_5_Ghz = nx.Graph()
        self.rssiThreshold = 100
        # self.currentChannel_2_4_Ghz = 1
        # self.currentChannel_5_Ghz = 36
        # self.currentChannelWidth_2_4_Ghz = 20
        # self.currentChannelWidth_5_Ghz = 20
        self.chanToIdx_5_GHz = {ch: idx for idx, ch in enumerate(BAND_5_CHANNELS)}

    def start(self):
        file_path = os.path.join(base_dir, "data", "interference_edges_balanced.csv")
        self.simulateRadioInput(file_path)

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(InterferenceGraph, cls).__new__(cls)
        return cls._instance

    def updateChannel_2_4_Ghz(self, channel):
        self.currentChannel_2_4_Ghz = channel

    def updateChannel_5_Ghz(self, channel):
        self.currentChannel_5_Ghz = channel

    def updateChannelWidth_2_4_Ghz(self, width):
        self.currentChannelWidth_2_4_Ghz = width

    def updateChannelWidth_5_Ghz(self, width):
        self.currentChannelWidth_5_Ghz = width

    def channel_overlap_2_4_GHz(self, c1, w1, c2, w2):
        return not (c1 + w1/2 <= c2 - w2/2 or c2 + w2/2 <= c1 - w1/2)

    def channel_overlap_5_GHz(self, c1, w1, c2, w2):
        return not (c1 + w1/2 <= c2 - w2/2 or c2 + w2/2 <= c1 - w1/2)

    def isEdgePresent_2_4_GHz(self, rssi, c1, w1, c2, w2):
        if self.channel_overlap_2_4_GHz(c1, w1, c2, w2) and rssi < self.rssiThreshold:
            return True
        return False

    def isEdgePresent_5_GHz(self, rssi, c1, w1, c2, w2):
        if self.channel_overlap_5_GHz(c1, w1, c2, w2) and rssi < self.rssiThreshold:
            return True
        return False

    def getGraph_2_4_Ghz(self):
        return self.graph_2_4_Ghz

    def getGraph_5_Ghz(self):
        return self.graph_5_Ghz

    def convertbandToIdx(self, band, channel):
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

    def simulateRadioInput(self, file):
        parser = CSVParser()
        beacons = parser.parseCSV(file)
        print("Interference Graph ", file)
        for beacon in beacons:
            band = beacon[APLog.BAND]
            channelA = self.convertbandToIdx(band, beacon[APLog.CHANNEL_A])
            channelB = self.convertbandToIdx(band, beacon[APLog.CHANNEL_B])
            widthA = beacon[APLog.WIDTH_A_MHZ]
            widthB = beacon[APLog.WIDTH_B_MHZ]
            clientA = beacon[APLog.AP_A]
            clientB = beacon[APLog.AP_B]
            distance = beacon[APLog.DIST_M]
            edgeweight = beacon[APLog.EDGE_WEIGHT]

            if (band == WiFiBand.BAND_2_4_GHz):
                self.handle_2_4_GHz(distance, channelA, widthA, channelB, widthB, clientA, clientB, edgeweight)
            elif (band == WiFiBand.BAND_5_GHz):
                self.handle_5_GHz(distance, channelA, widthA, channelB, widthB, clientA, clientB, edgeweight)

    def handle_2_4_GHz(self, rssi, c1, w1, c2, w2, clientA, clientB, edgeweight):
        isEdge = self.isEdgePresent_2_4_GHz(rssi, c1, w1, c2, w2)
        if (isEdge):
            self.updategraph_2_4_GHz([clientA, clientB, edgeweight])
        elif (self.graph_2_4_Ghz.has_edge(clientA, clientB)):
            self.graph_2_4_Ghz.remove_edge(clientA, clientB)

    def handle_5_GHz(self, rssi, c1, w1, c2, w2, clientA, clientB, edgeweight):
        isEdge = self.isEdgePresent_5_GHz(rssi, c1, w1, c2, w2)
        if (isEdge):
            self.updategraph_5_GHz([clientA, clientB, edgeweight])
        elif (self.graph_5_Ghz.has_edge(clientA, clientB)):
            self.graph_5_Ghz.remove_edge(clientA, clientB)

    def updategraph_2_4_GHz(self, edge: list):
        src = edge[0]
        dest = edge[1]
        weight = edge[2]
        if src not in self.graph_2_4_Ghz:
            self.graph_2_4_Ghz.add_node(src)
        if dest not in self.graph_2_4_Ghz:
            self.graph_2_4_Ghz.add_node(dest)
        if self.graph_2_4_Ghz.has_edge(src, dest):
            self.graph_2_4_Ghz[src][dest]['weight'] = weight
        else:
            self.graph_2_4_Ghz.add_edge(src, dest, weight=weight)

    def updategraph_5_GHz(self, edge: list):
        src = edge[0]
        dest = edge[1]
        weight = edge[2]
        if src not in self.graph_5_Ghz:
            self.graph_5_Ghz.add_node(src)
        if dest not in self.graph_5_Ghz:
            self.graph_5_Ghz.add_node(dest)
        if self.graph_5_Ghz.has_edge(src, dest):
            self.graph_5_Ghz[src][dest]['weight'] = weight
        else:
            self.graph_5_Ghz.add_edge(src, dest, weight=weight)