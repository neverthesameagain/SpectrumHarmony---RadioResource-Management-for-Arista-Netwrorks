import threading
import time

class DFSTimerManager:
    def __init__(self, interval, callback):
        self.interval = interval
        self.callback = callback
        self.timers = {}
        self.lock = threading.Lock()

    def _timeout(self, channel):
        with self.lock:
            self.timers.pop(channel, None)
        print(f"[Timer Expired] Channel {channel}")
        self.callback(channel)

    def start_or_reset(self, channel):
        with self.lock:
            if channel in self.timers:
                self.timers[channel].cancel()
                print(f"[Timer Reset] Channel {channel}")
            else:
                print(f"[Timer Started] Channel {channel}")

            t = threading.Timer(self.interval, self._timeout, args=[channel])
            t.start()
            self.timers[channel] = t

    def cancel(self, channel):
        with self.lock:
            if channel in self.timers:
                self.timers[channel].cancel()
                del self.timers[channel]
                print(f"[Timer Cancelled] Channel {channel}")

    def cancel_all(self):
        with self.lock:
            for ch, t in self.timers.items():
                t.cancel()
            self.timers.clear()
            print("[All DFS Timers Cancelled]")