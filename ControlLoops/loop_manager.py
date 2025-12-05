import threading
import time
from ControlLoops.fast_loop import FastLoop
from ControlLoops.slow_loop import SlowLoop
from ControlLoops.event_loop import EventLoop
from ControlLoops.explainability import ExplainabilityLayer
from ControlLoops.interference_graph import InterferenceGraph
from sensing_orchestra.sensing_orchestra import SensingOrchestra
from ControlLoops.gnn_training import run_pipeline

class LoopManager:
    def __init__(self):
        print("[LoopManager] Initializing...")
        self.orchestra = SensingOrchestra("AP24_1")
        self.fastLoop = FastLoop()
        self.slowLoop = SlowLoop(orchestra=self.orchestra)
        self.eventLoop = EventLoop()
        self.explainer = ExplainabilityLayer()
        self.graph = InterferenceGraph()
        
        self.fastLoopThread = threading.Thread(target=self.fastLoop.start, daemon=True)
        self.slowLoopThread = threading.Thread(target=self.slowLoop.start, daemon=True)
        self.eventLoopThread = threading.Thread(target=self.eventLoop.start, daemon=True)
        self.orchestraThread = threading.Thread(target=self.orchestra.start, daemon=True)
        # Assuming graph.start exists and is needed based on original code
        self.graphThread = threading.Thread(target=self.graph.start, daemon=True)
        
        # GNN Learning Loop (Background Thread)
        self.gnnThread = threading.Thread(target=self.run_gnn_loop, daemon=True)

    def run_gnn_loop(self):
        """Periodically runs the GNN training pipeline."""
        while True:
            print("[LoopManager] Starting GNN Learning Cycle...")
            try:
                # Run GNN pipeline (Training & Inference)
                run_pipeline(use_ensemble=True)
                self.explainer.log_decision("GNN_Loop", "Periodic_Training", "Model_Updated", "Graph_Learning_Complete")
            except Exception as e:
                print(f"[LoopManager] GNN Pipeline Failed: {e}")
                self.explainer.log_decision("GNN_Loop", "Periodic_Training", "Failed", str(e))
            
            # Sleep for a long interval (e.g., 1 hour)
            # For demo purposes, we might keep it shorter or use a config
            time.sleep(3600) 

    def start(self):
        print("[LoopManager] Starting RRM-Plus Integrated Controller...")
        self.explainer.log_decision("LoopManager", "Startup", "Start_All_Loops", "System_Init")
        
        # Start Graph first as in original code (assuming it initializes something)
        # Note: Original code joined it immediately, implying it might be a setup step.
        # We will start it as a thread to be safe.
        self.graphThread.start()
        
        self.fastLoopThread.start()
        self.slowLoopThread.start()
        self.eventLoopThread.start()
        self.orchestraThread.start()
        self.gnnThread.start() # Start GNN Loop
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[LoopManager] Stopping RRM-Plus Controller...")

if __name__ == "__main__":
    manager = LoopManager()
    manager.start()
