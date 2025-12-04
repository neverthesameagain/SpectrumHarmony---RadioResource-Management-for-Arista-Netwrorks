import csv
from . import APLogsColumns as APLog
from .WiFiBandEnum import WiFiBand


class CSVParserSO:
    def __init__(self):
        self.floatToBand = {2.4: WiFiBand.BAND_2_4_GHz, 5.0: WiFiBand.BAND_5_GHz, 6.0: WiFiBand.BAND_6_GHz}

    def parseCSV(self, filepath: str):
        with open(filepath, 'r') as file:
            reader = csv.reader(file)
            next(reader)
            # Make changes based on the actual column
            data = []
            for row in reader:
                row[APLog.TIMESTAMP] = str(row[APLog.TIMESTAMP])
                row[APLog.AP_ID] = row[APLog.AP_ID]
                row[APLog.BAND] = self.floatToBand[float(row[APLog.BAND])]
                row[APLog.CHANNEL] = int(row[APLog.CHANNEL])
                row[APLog.CHANNEL_WIDTH] = int(row[APLog.CHANNEL_WIDTH])
                row[APLog.TX_POWER_DBM] = float(row[APLog.TX_POWER_DBM])
                row[APLog.NOISE_FLOOR_DBM] = float(row[APLog.NOISE_FLOOR_DBM])
                row[APLog.NWIFI_DETECTED] = row[APLog.NWIFI_DETECTED]
                row[APLog.NWIFI_TYPE] = row[APLog.NWIFI_TYPE]
                row[APLog.AVG_CLIENT_SNR_DB] = float(row[APLog.AVG_CLIENT_SNR_DB])
                row[APLog.THROUGHPUT_AVG_Mbps] = float(row[APLog.THROUGHPUT_AVG_Mbps])
                row[APLog.P95_RETRY_PCT] = float(row[APLog.P95_RETRY_PCT])
                row[APLog.MEAN_QOE] = float(row[APLog.MEAN_QOE])
                row[APLog.P95_RETRY_PCT] = float(row[APLog.P95_RETRY_PCT])
                row[APLog.UL_PER] = float(row[APLog.UL_PER])
                row[APLog.BUSY_TIME] = float(row[APLog.BUSY_TIME])
                row[APLog.TOTAL_TIME] = float(row[APLog.TOTAL_TIME])
                row[APLog.AIRTIME_UTILIZATION] = float(row[APLog.AIRTIME_UTILIZATION])

                data.append(row)
        return data
