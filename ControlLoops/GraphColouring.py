def graphColouring(G, channels):
    C = {ap: 1 for ap in G.nodes()}  # initial color

    for ap in G.nodes():
        H = {}
        for c in channels:
            # For all neighbors with color c
            conflict_weights = []
            for nb in G.neighbors(ap):
                if C.get(nb) == c:
                    I = 1.0   # interference factor (can be dynamic)
                    W = G[ap][nb]['weight']
                    conflict_weights.append(I * W)
            H[c] = max(conflict_weights) if conflict_weights else 0
        # Choose color with minimum conflict
        best_color = min(H, key=H.get)
        C[ap] = best_color