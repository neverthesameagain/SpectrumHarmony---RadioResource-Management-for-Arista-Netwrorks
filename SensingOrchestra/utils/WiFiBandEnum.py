from enum import Enum


class WiFiBand(Enum):
    BAND_2_4_GHz = "2.4GHz"
    BAND_5_GHz = "5GHz"
    BAND_6_GHz = "6GHz"

class DFSState(Enum):
    AVAILABLE = 1 # the channel is available for use
    NOT_AVAILABLE = 0 # the channel is not available for use
