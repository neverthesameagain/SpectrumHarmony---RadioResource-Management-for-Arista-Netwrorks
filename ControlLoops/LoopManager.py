from threading import Thread
import time
from ControlLoops.FastLoop import FastLoop
from ControlLoops.InterferenceGraph import InterferenceGraph
from ControlLoops.SlowLoop import SlowLoop
from SensingOrchestra.SensingOrchestra import SensingOrchestra


class LoopManager():
    def __init__(self):
        print("Loop Manager initialized...")
        self.fastLoop = FastLoop(2)
        self.slowLoop = SlowLoop(10)
        self.graph = InterferenceGraph()
        self.orchestra = SensingOrchestra("AP24_1")

    def start(self):
        interference = Thread(target=self.graph.start, daemon=True)
        interference.start()
        interference.join()
        fastThread = Thread(target=self.fastLoop.start, daemon=True)
        slowThread = Thread(target=self.slowLoop.start, daemon=True)
        orchestra = Thread(target=self.orchestra.start, daemon=True)
        slowThread.start()
        fastThread.start()
        orchestra.start()


loopManager = LoopManager()
loopManager.start()
sleepTime = 100
time.sleep(sleepTime)
