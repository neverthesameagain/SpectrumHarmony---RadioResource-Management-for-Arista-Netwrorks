import networkx as nx
import ControlLoops.utils.ap_logs_columns as APLog
from sensing_orchestra.channel_info import BAND_5_CHANNELS
from sensing_orchestra.utils_so.wifi_band_enum import WiFiBand
from .utils.csv_parser import CSVParser
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
        self.simulate_radio_input(file_path)

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(InterferenceGraph, cls).__new__(cls)
        return cls._instance

    def update_channel_2_4_ghz(self, channel):
        self.currentChannel_2_4_Ghz = channel

    def update_channel_5_ghz(self, channel):
        self.currentChannel_5_Ghz = channel

    def update_channel_width_2_4_ghz(self, width):
        self.currentChannelWidth_2_4_Ghz = width

    def update_channel_width_5_ghz(self, width):
        self.currentChannelWidth_5_Ghz = width

    def channel_overlap_2_4_GHz(self, c1, w1, c2, w2):
        return not (c1 + w1/2 <= c2 - w2/2 or c2 + w2/2 <= c1 - w1/2)

    def channel_overlap_5_GHz(self, c1, w1, c2, w2):
        return not (c1 + w1/2 <= c2 - w2/2 or c2 + w2/2 <= c1 - w1/2)

    def is_edge_present_2_4_ghz(self, rssi, c1, w1, c2, w2):
        if self.channel_overlap_2_4_GHz(c1, w1, c2, w2) and rssi < self.rssiThreshold:
            return True
        return False

    def is_edge_present_5_ghz(self, rssi, c1, w1, c2, w2):
        if self.channel_overlap_5_GHz(c1, w1, c2, w2) and rssi < self.rssiThreshold:
            return True
        return False

    def get_graph_2_4_ghz(self):
        return self.graph_2_4_Ghz

    def get_graph_5_ghz(self):
        return self.graph_5_Ghz

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

    def simulate_radio_input(self, file):
        parser = CSVParser()
        beacons = parser.parseCSV(file)
        print("Interference Graph ", file)
        for beacon in beacons:
            band = beacon[APLog.BAND]
            channelA = self.convert_band_to_idx(band, beacon[APLog.CHANNEL_A])
            channelB = self.convert_band_to_idx(band, beacon[APLog.CHANNEL_B])
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
        isEdge = self.is_edge_present_2_4_ghz(rssi, c1, w1, c2, w2)
        if (isEdge):
            self.update_graph_2_4_ghz([clientA, clientB, edgeweight])
        elif (self.graph_2_4_Ghz.has_edge(clientA, clientB)):
            self.graph_2_4_Ghz.remove_edge(clientA, clientB)

    def handle_5_GHz(self, rssi, c1, w1, c2, w2, clientA, clientB, edgeweight):
        isEdge = self.is_edge_present_5_ghz(rssi, c1, w1, c2, w2)
        if (isEdge):
            self.update_graph_5_ghz([clientA, clientB, edgeweight])
        elif (self.graph_5_Ghz.has_edge(clientA, clientB)):
            self.graph_5_Ghz.remove_edge(clientA, clientB)

    def update_graph_2_4_ghz(self, edge: list):
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

    def update_graph_5_ghz(self, edge: list):
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