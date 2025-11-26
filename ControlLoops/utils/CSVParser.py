import csv
import ControlLoops.utils.APLogsColumns as APLog
import logging
from SensingOrchestra.utilsSO.WiFiBandEnum import WiFiBand

# logging.basicConfig(filename="control.log", level=logging.DEBUG)


class CSVParser:
    def __init__(self):
        logging.info("CSV Parser initiated...")
        self.floatToBand = {2.4: WiFiBand.BAND_2_4_GHz, 5.0: WiFiBand.BAND_5_GHz, 6.0: WiFiBand.BAND_6_GHz}

    def parseCSV(self, filepath: str):
        with open(filepath, 'r') as file:
            reader = csv.reader(file)
            next(reader)
            data = []
            for row in reader:
                row[APLog.AP_A] = row[APLog.AP_A]
                row[APLog.AP_B] = row[APLog.AP_B]
                row[APLog.DIST_M] = float(row[APLog.DIST_M])
                row[APLog.EDGE_WEIGHT] = float(row[APLog.EDGE_WEIGHT])
                row[APLog.BAND] = self.floatToBand[float(row[APLog.BAND])]
                row[APLog.CHANNEL_A] = int(row[APLog.CHANNEL_A])
                row[APLog.CHANNEL_B] = int(row[APLog.CHANNEL_B])
                row[APLog.WIDTH_A_MHZ] = int(row[APLog.WIDTH_A_MHZ])
                row[APLog.WIDTH_B_MHZ] = int(row[APLog.WIDTH_B_MHZ])
                data.append(row)
        return data
