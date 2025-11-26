import threading
import time
import logging

logging.basicConfig(filename="output.log", level=logging.DEBUG)

class DFSTimerManager:
    def __init__(self, interval, callback):
        self.interval = interval
        self.callback = callback
        self.timers = {}
        self.lock = threading.Lock()
        self.isRunning = True

    def _timeout(self, channel):
        with self.lock:
            self.timers.pop(channel, None)
        logging.info(f"[Timer Expired] Channel {channel}")
        self.callback(channel)

    def start_or_reset(self, channel):
        with self.lock:
            if channel in self.timers:
                self.timers[channel].cancel()
                logging.info(f"[Timer Reset] Channel {channel}")
            else:
                logging.info(f"[Timer Started] Channel {channel}")

            t = threading.Timer(self.interval, self._timeout, args=[channel])
            t.daemon = True
            t.start()
            self.timers[channel] = t

    def cancel(self, channel):
        with self.lock:
            if channel in self.timers:
                self.timers[channel].cancel()
                del self.timers[channel]
                logging.info(f"[Timer Cancelled] Channel {channel}")

    def cancel_all(self):
        with self.lock:
            for ch, t in self.timers.items():
                t.cancel()
            self.timers.clear()
            logging.info("[All DFS Timers Cancelled]")