import networkx as nx


class InterferenceGraph():
    def __init__(self):
        print("Interference graph...")
        self.graph = nx.Graph()
    
    def overlapScore():
        pass

    def updategraph(self, edges: list):
        for edge in edges:
            src = edge[0]
            dest = edge[1]
            weight = edge[2]
            if src not in self.graph:
                self.graph.add_node(src)
            if dest not in self.graph:
                self.graph.add_node(dest)
            if self.graph.has_edge(src, dest):
                self.graph[src][dest]['weight'] = weight
            else:
                self.graph.add_edge(src, dest, weight=weight)
