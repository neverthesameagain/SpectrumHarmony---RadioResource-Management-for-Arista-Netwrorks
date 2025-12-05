import threading
import time
from ControlLoops.FastLoop import FastLoop
from ControlLoops.SlowLoop import SlowLoop
from ControlLoops.EventLoop import EventLoop
from ControlLoops.Explainability import ExplainabilityLayer
from ControlLoops.InterferenceGraph import InterferenceGraph
from SensingOrchestra.SensingOrchestra import SensingOrchestra

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
        
        self.fastLoopThread.join()
        self.slowLoopThread.join()
        self.eventLoopThread.join()
        self.orchestraThread.join()
        self.graphThread.join()

if __name__ == "__main__":
    manager = LoopManager()
    manager.start()
time.sleep(sleepTime)
