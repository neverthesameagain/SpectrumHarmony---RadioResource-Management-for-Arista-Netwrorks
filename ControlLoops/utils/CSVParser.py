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
                row[APLog.TIMESTAMP] = row[APLog.TIMESTAMP]
                row[APLog.BAND] = self.floatToBand[float(row[APLog.BAND])]
                row[APLog.AP_A] = str(row[APLog.AP_A])
                row[APLog.AP_B] = str(row[APLog.AP_B])
                row[APLog.DIST_M] = float(row[APLog.DIST_M])
                row[APLog.PATHLOSS_DB] = float(row[APLog.PATHLOSS_DB])
                row[APLog.CHANNEL_A] = int(row[APLog.CHANNEL_A])
                row[APLog.CHANNEL_B] = int(row[APLog.CHANNEL_B])
                row[APLog.WIDTH_A_MHZ] = int(row[APLog.WIDTH_A_MHZ])
                row[APLog.WIDTH_B_MHZ] = int(row[APLog.WIDTH_B_MHZ])
                row[APLog.TX_A_DBM] = float(row[APLog.TX_A_DBM])
                row[APLog.TX_B_DBM] = float(row[APLog.TX_B_DBM])
                row[APLog.AIRTIME_A] = float(row[APLog.AIRTIME_A])
                row[APLog.AIRTIME_B] = float(row[APLog.AIRTIME_B])
                row[APLog.LOAD_MIN] = float(row[APLog.LOAD_MIN])
                row[APLog.LOAD_MAX] = float(row[APLog.LOAD_MAX])
                row[APLog.P95_RETRY_A] = float(row[APLog.P95_RETRY_A])
                row[APLog.P95_RETRY_B] = float(row[APLog.P95_RETRY_B])
                row[APLog.NWIFI_DETECTED_A] = row[APLog.NWIFI_DETECTED_A]
                row[APLog.NWIFI_DETECTED_B] = row[APLog.NWIFI_DETECTED_B]
                row[APLog.NWIFI_TYPE_A] = str(row[APLog.NWIFI_TYPE_A])
                row[APLog.NWIFI_TYPE_B] = str(row[APLog.NWIFI_TYPE_B])
                row[APLog.CHANNEL_OVERLAP] = float(row[APLog.CHANNEL_OVERLAP])
                row[APLog.RX_POWER_EST_NORM] = float(row[APLog.RX_POWER_EST_NORM])
                row[APLog.DIST_SCORE] = float(row[APLog.DIST_SCORE])
                row[APLog.RADAR_PENALTY] = float(row[APLog.RADAR_PENALTY])
                row[APLog.EDGE_WEIGHT] = float(row[APLog.EDGE_WEIGHT])
                data.append(row)
        return data
