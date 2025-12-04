import matplotlib.pyplot as plt
import time
from ControlLoops.InterferenceGraph import InterferenceGraph
import networkx as nx
import matplotlib
matplotlib.use("Agg")


class SlowLoop:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(SlowLoop, cls).__new__(cls)
        return cls._instance

    def __init__(self, interval=3600):
        self.graph = InterferenceGraph()
        self.interval = interval
        self.isRunning = True
        self.colouring_2_4_GHz = {}
        self.colouring_5_GHz = {}
        self.counter = 0

    def start(self):
        while (self.isRunning):
            time.sleep(self.interval)
            self.colourGraph_2_4_GHz()
            self.colourGraph_5_GHz()

    def colourGraph_2_4_GHz(self):
        self.graph_2_4_GHz = self.graph.getGraph_2_4_Ghz()
        colors = nx.coloring.greedy_color(self.graph_2_4_GHz, strategy="smallest_last")
        color_map = [colors[node] for node in self.graph_2_4_GHz.nodes()]
        self.colouring_2_4_GHz = color_map
        print("SLOWLOOP", color_map, "2.4 GHz")
        pos = nx.spring_layout(self.graph_2_4_GHz)
        nx.draw(
            self.graph_2_4_GHz,
            pos,
            with_labels=True,
            node_color=color_map,
            cmap=plt.cm.Set3
        )
        plt.savefig(f"graphs/graph_2_4_{self.counter}_GHz.png", dpi=300, bbox_inches="tight")
        plt.close()

    def colourGraph_5_GHz(self):
        self.graph_5_GHz = self.graph.getGraph_5_Ghz()
        colors = nx.coloring.greedy_color(self.graph_5_GHz, strategy="smallest_last")
        color_map = [colors[node] for node in self.graph_5_GHz.nodes()]
        self.colouring_5_GHz = color_map
        print("SLOWLOOP", color_map, "5 GHz")
        pos = nx.spring_layout(self.graph_5_GHz)
        nx.draw(
            self.graph_5_GHz,
            pos,
            with_labels=True,
            node_color=color_map,
            cmap=plt.cm.Set3
        )
        plt.savefig(f"graphs/graph_5_{self.counter}_GHz.png", dpi=300, bbox_inches="tight")
        plt.close()
        self.counter += 1

    def getColours_2_4_GHz(self):
        return self.colouring_2_4_GHz

    def getColours_5_GHz(self):
        return self.colouring_5_GHz
