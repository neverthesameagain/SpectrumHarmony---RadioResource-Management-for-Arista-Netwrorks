import threading
import time
from ControlLoops.FastLoop import FastLoop
from ControlLoops.SlowLoop import SlowLoop
from ControlLoops.EventLoop import EventLoop
from ControlLoops.Explainability import ExplainabilityLayer
from ControlLoops.InterferenceGraph import InterferenceGraph
from SensingOrchestra.SensingOrchestra import SensingOrchestra
from ControlLoops.GNN_Training import run_pipeline

class LoopManager:
    def __init__(self):
        print("[LoopManager] Initializing...")
        self.orchestra = SensingOrchestra("AP24_1")
        self.fastLoop = FastLoop()
        self.slowLoop = SlowLoop(orchestra=self.orchestra)
        self.eventLoop = EventLoop()
        self.explainer = ExplainabilityLayer()
        self.graph = InterferenceGraph()
        
        self.fastLoopThread = threading.Thread(target=self.fastLoop.start)
        self.slowLoopThread = threading.Thread(target=self.slowLoop.start)
        self.eventLoopThread = threading.Thread(target=self.eventLoop.start)
        self.orchestraThread = threading.Thread(target=self.orchestra.start)
        # Assuming graph.start exists and is needed based on original code
        self.graphThread = threading.Thread(target=self.graph.start)
        
        # GNN Learning Loop (Background Thread)
        self.gnnThread = threading.Thread(target=self.run_gnn_loop)

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
        
        self.fastLoopThread.join()
        self.slowLoopThread.join()
        self.eventLoopThread.join()
        self.orchestraThread.join()
        self.graphThread.join()
        self.gnnThread.join()

if __name__ == "__main__":
    manager = LoopManager()
    manager.start()
time.sleep(sleepTime)
