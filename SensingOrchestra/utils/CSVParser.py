import csv
import utils.APLogsColumns as APLog
from utils.WiFiBandEnum import WiFiBand


class CSVParser:
    def __init__(self):
        self.floatToBand = {2.4: WiFiBand.BAND_2_4_GHz, 5.0: WiFiBand.BAND_5_GHz, 6.0: WiFiBand.BAND_6_GHz}
        print("Initializing CSV parser...")

    def parseCSV(self, filepath: str):
        with open(filepath, 'r') as file:
            reader = csv.reader(file)
            next(reader)
            # Make changes based on the actual column
            data = []
            for row in reader:
                row[APLog.AP_ID] = row[APLog.AP_ID]
                row[APLog.BAND] = self.floatToBand[float(row[APLog.BAND])]
                row[APLog.CHANNEL] = int(row[APLog.CHANNEL])
                row[APLog.CHANNEL_WIDTH] = int(row[APLog.CHANNEL_WIDTH])
                row[APLog.TX_POWER_DBM] = float(row[APLog.TX_POWER_DBM])
                row[APLog.AVG_RSSI_DBM] = float(row[APLog.AVG_RSSI_DBM])
                row[APLog.NOISE_FLOOR_DBM] = float(row[APLog.NOISE_FLOOR_DBM])
                row[APLog.NWIFI_DETECTED] = row[APLog.NWIFI_DETECTED]
                row[APLog.AVG_CLIENT_SNR_DB] = float(row[APLog.AVG_CLIENT_SNR_DB])
                row[APLog.THROUGHPUT_AVG_Mbps] = float(row[APLog.THROUGHPUT_AVG_Mbps])
                row[APLog.P95_RETRY_PCT] = float(row[APLog.P95_RETRY_PCT])
                row[APLog.MEAN_QOE] = float(row[APLog.MEAN_QOE])
                row[APLog.MEAN_DISTANCE_M] = float(row[APLog.MEAN_DISTANCE_M])
                row[APLog.P95_DISTANCE_M] = float(row[APLog.P95_DISTANCE_M])
                row[APLog.MAX_DISTANCE_M] = float(row[APLog.MAX_DISTANCE_M])
                row[APLog.BUSY_TIME] = float(row[APLog.BUSY_TIME])
                row[APLog.TOTAL_TIME] = float(row[APLog.TOTAL_TIME])

                data.append(row)
        return data
