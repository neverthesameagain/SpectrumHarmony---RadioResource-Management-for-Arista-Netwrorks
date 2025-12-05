from collections import deque
import time


class FastLoop():
    def __init__(self, interval=5):
        self.interval = interval
        self.queue = deque()
        self.isRunning = True

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(FastLoop, cls).__new__(cls)
        return cls._instance

    def start(self):
        while (self.isRunning):
            time.sleep(self.interval)
            self.processChange()

    def addChange(self, change):
        self.queue.append(change)

    def processChange(self):
        while self.queue:
            change = self.queue.popleft()
            # apply the change or whatever
            print(f"[FASTLOOP] Change : {change['type']} Value : {change['value']}")
    
