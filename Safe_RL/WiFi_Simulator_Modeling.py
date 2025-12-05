import math
import numpy as np
from datetime import datetime, timedelta

# the receiver noise floor in dBm (for 20MHz)
NOISE_FLOOR_DBM = -95.0

# pathloss: reference distance D0 and pathloss at D0
D0 = 1.0
PL0_DB = 30.0

# pathloss exponent 
ETA = 4.0

# shadowing standard deviation in dB
SHADOW_STD_DB = 6.0

# receiver implementation margin in dB
IMPLEMENTATION_MARGIN_DB = 4.0

# packet size in bytes
PACKET_SIZE = 4000


class AccessPoint:
    def __init__(self, ap_id, x, y, seed=None):
        self.ap_id = ap_id
        self.pos = (x, y)
        self.rng = np.random.default_rng(seed)

        # configuration parameters
        self.tx_power_dbm = None
        self.channel_width_mhz = None
        self.obss_pd_dbm = None
        self.channel_center_mhz = None

        # dynamic state
        self.associated_clients = [] 
        self.last_stats = None           

    # basic configuration
    def configure(self, tx_power_dbm, channel_width_mhz, obss_pd_dbm, channel_center_mhz=None):
        self.tx_power_dbm = tx_power_dbm
        self.channel_width_mhz = channel_width_mhz
        self.obss_pd_dbm = obss_pd_dbm
        self.channel_center_mhz = channel_center_mhz if channel_center_mhz is not None else 5180.0

    # defines the Q function
    def Q(self, x):
        return 0.5 * math.erfc(x / math.sqrt(2.0))
    
    # calculates BER for BPSK in AWGN
    def ber_bpsk_awgn(self, ebn0_lin):
        return self.Q(math.sqrt(2.0 * ebn0_lin))
    
    # calculates BER for M-QAM in AWGN
    def ber_mqam_awgn(self, ebn0_lin, M):
        k = math.log2(M)
        q = self.Q(math.sqrt((3 * k / (M - 1)) * ebn0_lin))
        return 2 * (1 - 1 / math.sqrt(M)) / k * q
    
    # calculates PER from BER
    def per_from_ber(self, ber, Nbits):
        return 1 - (1 - ber)**Nbits
    
    # calculates pathloss in dB
    def pathloss_db(self, d):
        shadow = self.rng.normal(0, SHADOW_STD_DB)
        return PL0_DB + 10 * ETA * math.log10(max(d, D0) / D0) + shadow
    
    # calculates SNR in dB
    def snr_db(self, tx_dbm, dist, channel_width_mhz=20):

        # pathloss and rx power
        rx_dbm = tx_dbm - self.pathloss_db(dist)

        # noise increases with bandwidth: 10*log10(B/20)
        bw_penalty_db = 10.0 * math.log10(channel_width_mhz / 20.0)

        # effective noise floor for this bandwidth
        noise_dbm_bw = NOISE_FLOOR_DBM + bw_penalty_db
        snr_db = rx_dbm - noise_dbm_bw

        # subtract implementation margin to get realistic effective SNR
        snr_db -= IMPLEMENTATION_MARGIN_DB

        return snr_db
    
    # selects that MCS which would give the best effective rate
    # however, only MCS that meet their minimum SNR threshold are considered
    # the MCS table has the minimum SNR thresholds for each MCS
    def select_mcs(self, snr_db, channel_width_mhz):
        MCS_TABLE = [
            {"mcs": 0, "M": 2,  "r": 1/2, "rate_mbps": 6.5,  "min_snr_db": 0.0},
            {"mcs": 3, "M": 16, "r": 1/2, "rate_mbps": 26.0, "min_snr_db": 8.0},
            {"mcs": 5, "M": 64, "r": 2/3, "rate_mbps": 52.0, "min_snr_db": 16.0},
            {"mcs": 7, "M": 64, "r": 5/6, "rate_mbps": 65.0, "min_snr_db": 22.0},
        ]

        best = {"rate_mbps": 0.0, "per": 1.0, "mcs": 0}

        for entry in MCS_TABLE:
            # skip MCS that are below their minimum SNR threshold
            if snr_db < entry["min_snr_db"]:
                continue

            M, r = entry["M"], entry["r"]
            snr_lin = 10**(snr_db / 10)
            ebn0 = snr_lin / (math.log2(M) * r)

            if M == 2:
                ber = self.ber_bpsk_awgn(ebn0)
            else:
                ber = self.ber_mqam_awgn(ebn0, M)

            per = self.per_from_ber(ber, PACKET_SIZE * 8)
            rate = entry["rate_mbps"] * (channel_width_mhz / 20)

            eff = rate * (1 - per)
            if eff > best["rate_mbps"]:
                best = {"rate_mbps": rate, "per": per, "mcs": entry["mcs"]}

        # if none passed threshold, pick the lowest threshold MCS
        if best["rate_mbps"] == 0.0:
            entry = MCS_TABLE[0]
            per = 1.0
            M, r = entry["M"], entry["r"]
            snr_lin = 10**(snr_db / 10)
            ebn0 = snr_lin / (math.log2(M) * r)
            ber = self.ber_bpsk_awgn(ebn0)
            per = self.per_from_ber(ber, 4000 * 8)
            best = {"rate_mbps": entry["rate_mbps"] * (channel_width_mhz / 20), "per": per, "mcs": entry["mcs"]}

        return best
    
    # computes the fraction of victim channel overlapped by interferer using rectangular channels
    # we know the centre frequencies and bandwidths of both victim and interferer
    # this allows us to compute the width of the region of overlap
    # this width is then normalized by the victim bandwidth to get the overlap fraction
    def _channel_overlap_fraction(self, victim_center_mhz, victim_width, interferer_center_mhz, interferer_width):
        v_lo = victim_center_mhz - victim_width/2.0
        v_hi = victim_center_mhz + victim_width/2.0
        i_lo = interferer_center_mhz - interferer_width/2.0
        i_hi = interferer_center_mhz + interferer_width/2.0

        overlap_lo = max(v_lo, i_lo)
        overlap_hi = min(v_hi, i_hi)
        overlap = max(0.0, overlap_hi - overlap_lo)

        return overlap / victim_width

    # BSS - the AP + clients associated to it
    # OBSS - other BSSs in the area, which are potential interferers
    # OBSS-PD - OBSS Packet Detection threshold which determines if an OBSS defers or not
    # if the OBSS senses the victim AP above its OBSS-PD, it defers and does not interfere
    # we must compute if each neighbor AP defers or not based on OBSS-PD
    # if it does not defer, we compute the received power at the client position

    # computes total interference power in dBm at a client position from neighbor APs
    # self - the AP whose client we are evaluating (the victim AP)
    # neighbor_aps - list of AccessPoint objects considered as potential interferers
    
    def compute_interference_dbm(self, neighbor_aps, client_pos):

        total_power_mw = 0.0
        cx, cy = client_pos

        for ap in neighbor_aps:
            # skip if neighbor has no configuration
            if ap.tx_power_dbm is None or ap.channel_width_mhz is None or ap.obss_pd_dbm is None:
                continue

            # (1) determine if the neighbor would defer because it senses this AP strongly
            ax, ay = self.pos
            nx, ny = ap.pos
            d_ap_to_neighbor = math.dist((ax, ay), (nx, ny))
            rx_at_neighbor_dbm = self.tx_power_dbm - ap.pathloss_db(d_ap_to_neighbor)

            if rx_at_neighbor_dbm > ap.obss_pd_dbm:
                continue

            # (2) compute received power from neighbor AP at client position (use neighbor's pathloss)
            d_neighbor_to_client = math.dist((nx, ny), (cx, cy))
            rx_power_dbm_at_client = ap.tx_power_dbm - ap.pathloss_db(d_neighbor_to_client)

            # (3) compute channel overlap fraction (how much of victim bandwidth is overlapped)
            overlap_frac = self._channel_overlap_fraction(
                victim_center_mhz=self.channel_center_mhz,
                victim_width=self.channel_width_mhz,
                interferer_center_mhz=ap.channel_center_mhz,
                interferer_width=ap.channel_width_mhz
            )

            if overlap_frac <= 0.0:
                continue

            # (4) scale the interfering power by overlap fraction in linear domain
            rx_power_mw = 10 ** (rx_power_dbm_at_client / 10.0)
            scaled_rx_power_mw = rx_power_mw * overlap_frac

            total_power_mw += scaled_rx_power_mw

        if total_power_mw <= 0.0:
            return -200.0
        return 10.0 * math.log10(total_power_mw)

    # simulation of one time step
    def step(self, neighbor_aps, dt=1.0):

        throughput_list = []
        retry_list = []

        N = len(self.associated_clients)
        if N == 0:
            self.last_stats = {
                "p50_throughput": 0,
                "p95_retry": 0,
                "clients": 0
            }
            return self.last_stats
        
        # compute total demand of associated clients
        total_demand = sum(client.demand_mbps for client in self.associated_clients)

        # we loop through each associated client
        for client in self.associated_clients:

            # airtime share proportional to demand
            airtime_share = client.demand_mbps / total_demand

            # use ap coordinates and client coordinates to compute distance
            cx, cy = client.pos
            ax, ay = self.pos
            d = math.dist((ax, ay), (cx, cy))

            # PHY layer -> preliminary SNR calculation
            snr_raw_db = self.snr_db(self.tx_power_dbm, d)

            # interference calculation
            interf_dbm = self.compute_interference_dbm(neighbor_aps, client.pos)
            interf_lin = 10**(interf_dbm/10)
            noise_lin = 10**(NOISE_FLOOR_DBM/10)
            
            # effective SNR after interference
            snr_eff = snr_raw_db - 10*math.log10(1 + interf_lin/noise_lin)

            # select MCS based on effective SNR
            mcs = self.select_mcs(snr_eff, self.channel_width_mhz)

            # retries ~ geometric distribution based on PER
            per = mcs["per"]
            if per >= 0.9999:
                retries = 20
            else:
                retries = np.random.geometric(1.0 - per)
                retries = min(retries, 20)


            retry_list.append(retries)

            # throughput
            thr = mcs["rate_mbps"] * airtime_share * (1 - per)
            throughput_list.append(thr)

        # compute percentiles
        p50_throughput = np.percentile(throughput_list, 50)
        p95_retry = np.percentile(retry_list, 95)
        
        # update last stats
        self.last_stats = {
            "p50_throughput": p50_throughput,
            "p95_retry": p95_retry,
            "clients": N,
        }
        return self.last_stats
    

class Client:
    def __init__(self, client_id, x, y, traffic_demand='medium'):
        self.id = client_id
        self.pos = (x, y)
        
        # traffic demand
        demand_map = {
            'light': 5,
            'medium': 20,
            'heavy': 80
        }
        self.demand_mbps = demand_map.get(traffic_demand, 20)

    def __repr__(self):
        x, y = self.pos
        return f"Client(id={self.id}, pos=({x:.1f},{y:.1f}), demand={self.demand_mbps}Mbps)"
    

class Environment:
    def __init__(self, width, height, aps, start_date="2025-01-01 00:00:00"):

        # dimensions of the area
        self.width = width
        self.height = height

        # list of AccessPoint objects
        self.aps = aps

        # list of Client objects
        self.clients = []
        
        # current simulation time
        self.current_time = datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S")


    # spawning clients with random positions + random demand
    def spawn_clients(self, n_clients):
        self.clients = []
        for i in range(n_clients):
            x = np.random.uniform(0, self.width)
            y = np.random.uniform(0, self.height)

            demand_type = np.random.choice(["light", "medium", "heavy"], p=[0.3, 0.5, 0.2])

            client = Client(client_id=i, x=x, y=y, traffic_demand=demand_type)
            self.clients.append(client)

    # associate clients to the best AP (highest SNR)
    def associate_clients(self):

        for ap in self.aps:
            ap.associated_clients = []

        for client in self.clients:
            best_ap = None
            best_snr = -999

            for ap in self.aps:
                ax, ay = ap.pos
                cx, cy = client.pos
                d = math.dist((ax, ay), (cx, cy))

                snr = ap.snr_db(ap.tx_power_dbm, d, ap.channel_width_mhz)
                if snr > best_snr:
                    best_snr = snr
                    best_ap = ap

            best_ap.associated_clients.append(client)

    # sinusoidal model for client count variation
    def sample_client_count(self, hour):
        # parameters for sinusoidal model
        peak_clients = 25
        min_clients = 5
        
        # midpoint and amplitude
        baseline = (peak_clients + min_clients) / 2
        amplitude = (peak_clients - min_clients) / 2

        # phase shift so peak occurs at 18:00 (6 PM)
        peak_hour = 18
        phase_shift = peak_hour

        # sinusoidal variation with noise
        value = baseline + amplitude * np.sin(2 * np.pi * (hour - phase_shift) / 24)
        noise = np.random.normal(0, 2)
        
        # obtain final client count, clipped to valid range
        client_count = int(value + noise)
        client_count = max(min_clients, min(peak_clients, client_count))
        return client_count

    # run simulation for one timestep
    def step(self):
        results = []

        for ap in self.aps:
            # neighbors = all other APs
            neighbor_aps = [n for n in self.aps if n != ap]

            stats = ap.step(neighbor_aps)
            results.append({
                "ap_id": ap.ap_id,
                **stats
            })

        return results

    # high-level 20-day simulation
    def run_simulation(self, days=20):
        logs = []
        total_hours = days * 24

        for hour in range(total_hours):

            # vary client count realistically
            n_clients = self.sample_client_count(hour % 24)
            self.spawn_clients(n_clients)

            # associate clients to APs
            self.associate_clients()

            # step through the wireless PHY/MAC simulation
            hour_stats = self.step()

            logs.append({
                "hour": hour,
                "client_count": n_clients,
                "ap_stats": hour_stats
            })

        return logs
