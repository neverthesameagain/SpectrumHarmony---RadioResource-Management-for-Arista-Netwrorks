# ==============================================================
# ARISTA RRM+ Synthetic Simulation (Final Instrumented Version)
# ==============================================================

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import math, sys

# ---------------- CONFIG ----------------
rng = np.random.default_rng(42)
N_AP, CLIENTS_PER_AP, RADIUS_M = 6, 40, 10.0
RSSI_MIN, RSSI_MAX = -70, -30
N_MIN = 24 * 60
START_TS = datetime(2025, 11, 2, 0, 0, 0)

BANDS = ["2.4", "5"]
CH_24 = [1, 6, 11]
CH_5 = [36, 40, 44, 48]
WIDTHS = [20, 40, 80]
PHY_MAX_24, PHY_MAX_5 = 72.0, 200.0

def width_scale(w): return {20:1.0,40:1.7,80:3.0}.get(w,1.0)

# ---------------- AP GRID ----------------
grid_x, grid_y = np.linspace(0, 40, 3), np.linspace(0, 20, 2)
ap_coords = [(x, y) for y in grid_y for x in grid_x][:N_AP]
ap_meta=[]
for i,(x,y) in enumerate(ap_coords):
    band = rng.choice(BANDS,p=[0.4,0.6])
    if band=="2.4":
        ch,width,phy = rng.choice(CH_24),20,PHY_MAX_24
    else:
        ch,width = rng.choice(CH_5),rng.choice(WIDTHS,p=[0.6,0.3,0.1])
        phy=PHY_MAX_5*width_scale(width)
    ap_meta.append({
        "ap_id":f"AP_{i+1}","x":x,"y":y,"band":band,"channel":int(ch),
        "channel_width_mhz":int(width),"tx_power_dbm":float(rng.integers(14,21)),
        "phy_max_mbps":phy
    })
ap_df=pd.DataFrame(ap_meta)

# ---------------- CLIENTS ----------------
clients=[]
for _,ap in ap_df.iterrows():
    for k in range(CLIENTS_PER_AP):
        r=RADIUS_M*math.sqrt(rng.uniform())
        θ=rng.uniform(0,2*np.pi)
        x,y=ap.x+r*np.cos(θ),ap.y+r*np.sin(θ)
        clients.append({
            "client_id":f"C_{ap.ap_id}_{k+1}","connected_ap":ap.ap_id,
            "band":ap.band,"channel":ap.channel,"x":x,"y":y,"distance_m":r
        })
clients_df=pd.DataFrame(clients)

# ---------------- MODELS ----------------
def rssi_from_distance(d,std=1.5):
    base=RSSI_MAX-(d/RADIUS_M)*(RSSI_MAX-RSSI_MIN)
    return float(np.clip(base+rng.normal(0,std),RSSI_MIN,RSSI_MAX))

def noise_floor(band):
    base=-94.5 if band=="2.4" else -96.0
    return float(base+rng.normal(0,1.5))

def nonwifi_event():
    if rng.random()<0.25:
        n=int(rng.integers(1,3)); penalty=float(rng.uniform(3,10))
        peaks=[(int(rng.integers(5,59)),float(rng.uniform(10,20))) for _ in range(n)]
        return True,n,penalty,peaks
    return False,0,0.0,[]

def overlap_score(ap_row):
    same=ap_df[(ap_df.band==ap_row.band)&(ap_df.channel==ap_row.channel)&(ap_df.ap_id!=ap_row.ap_id)]
    dists=np.sqrt((same.x-ap_row.x)**2+(same.y-ap_row.y)**2)
    return int((dists<25).sum())

def retry_pct(snr,nonwifi=False):
    base=100/(1+np.exp(0.35*(snr-18)))
    if nonwifi: base+=8
    return float(np.clip(base+rng.normal(0,2),0,100))

def throughput(snr,band,width,retry):
    phy=PHY_MAX_24 if band=="2.4" else PHY_MAX_5
    phy*=width_scale(width)
    eff=np.clip(snr/35,0,1)*(1-retry/120)*(0.9+rng.uniform(0,0.15))
    return float(max(0,phy*eff))

def qoe(snr,retry):
    s=np.clip(snr/35,0,1); r=1-np.clip(retry/50,0,1)
    return float(5*(0.7*s+0.3*r))

# ---------------- SIMULATION ----------------
ap_overlap={a.ap_id:overlap_score(a) for _,a in ap_df.iterrows()}
ap_log,client_log,fft_log=[],[],[]

print(f"🚀 Starting 24-hour simulation ({N_AP} APs, {CLIENTS_PER_AP*N_AP} clients)...")

for minute in range(N_MIN):
    ts=START_TS+timedelta(minutes=minute)

    if minute % 100 == 0:
        print(f" ⏱️  Progress: minute {minute}/{N_MIN} ({minute/60:.1f} hrs simulated)")

    ap_noise,ap_nwflag,ap_penalty,ap_peaks={}, {}, {}, {}
    for _,a in ap_df.iterrows():
        nf=noise_floor(a.band)
        flag,count,pen,peaks=nonwifi_event()
        ap_noise[a.ap_id]=nf; ap_nwflag[a.ap_id]=(flag,count)
        ap_penalty[a.ap_id]=pen; ap_peaks[a.ap_id]=peaks

        bins=rng.normal(-90,3,64)
        if flag:
            for c,p in peaks: bins[c-1:c+2]+=p
        fft_log.append({
            "timestamp":ts.isoformat(),"ap_id":a.ap_id,
            **{f"fft_bin_{i}":float(b) for i,b in enumerate(bins)},
            "label":"non_wifi" if flag else "wifi"
        })

    ap_snr,ap_thr,ap_rty,ap_q,ap_dist={},{},{},{},{}
    for _,c in clients_df.iterrows():
        apid=c.connected_ap
        a=ap_df[ap_df.ap_id==apid].iloc[0]
        dist=c.distance_m
        rssi_ap_rx=rssi_from_distance(dist)
        nf=ap_noise[apid]; pen=ap_penalty[apid]
        snr_ap_rx=float(np.clip(rssi_ap_rx-(nf+pen),-5,40))
        rssi_client_rx=rssi_ap_rx+rng.normal(0,1)
        snr_client_rx=float(np.clip(rssi_client_rx-(nf+pen),-5,40))
        nw=ap_nwflag[apid][0]
        rty=retry_pct(snr_client_rx,nw)
        thr=throughput(snr_client_rx,a.band,a.channel_width_mhz,rty)
        q=qoe(snr_client_rx,rty)
        client_log.append({
            "timestamp":ts.isoformat(),"client_id":c.client_id,"connected_ap":apid,
            "band":a.band,"channel":a.channel,"rssi_dbm":rssi_client_rx,"snr_db":snr_client_rx,
            "throughput_mbps":thr,"retry_rate_pct":rty,"qoe":q,"x":c.x,"y":c.y,
            "distance_m":dist,"affected_nonwifi":nw
        })
        ap_snr.setdefault(apid,[]).append(snr_client_rx)
        ap_thr.setdefault(apid,[]).append(thr)
        ap_rty.setdefault(apid,[]).append(rty)
        ap_q.setdefault(apid,[]).append(q)
        ap_dist.setdefault(apid,[]).append(dist)

    for _,a in ap_df.iterrows():
        snrs=np.array(ap_snr.get(a.ap_id,[]))
        thrs=np.array(ap_thr.get(a.ap_id,[]))
        rtys=np.array(ap_rty.get(a.ap_id,[]))
        qoes=np.array(ap_q.get(a.ap_id,[]))
        dists=np.array(ap_dist.get(a.ap_id,[]))
        ap_log.append({
            "timestamp":ts.isoformat(),"ap_id":a.ap_id,"band":a.band,"channel":a.channel,
            "channel_width_mhz":a.channel_width_mhz,"tx_power_dbm":a.tx_power_dbm,
            "noise_floor_dbm":ap_noise[a.ap_id],
            "channel_utilization_pct":float(np.clip(rng.normal(40,10),5,95)),
            "nwifi_detected":ap_nwflag[a.ap_id][0],
            "nwifi_count":ap_nwflag[a.ap_id][1],
            "overlap_score":ap_overlap[a.ap_id],
            "avg_client_snr_db":float(np.nanmean(snrs)) if snrs.size else 0,
            "throughput_avg_mbps":float(np.nanmean(thrs)) if thrs.size else 0,
            "p95_retry_pct":float(np.nanpercentile(rtys,95)) if rtys.size else 0,
            "mean_qoe":float(np.nanmean(qoes)) if qoes.size else 0,
            "mean_distance_m":float(np.nanmean(dists)) if dists.size else 0,
            "p95_distance_m":float(np.nanpercentile(dists,95)) if dists.size else 0,
            "max_distance_m":float(np.nanmax(dists)) if dists.size else 0,
            "decision_action":"none","reason_code":"none"
        })

# ---------------- SAVE & SUMMARY ----------------
client_df=pd.DataFrame(client_log)
ap_df_out=pd.DataFrame(ap_log)
fft_df=pd.DataFrame(fft_log)

client_df.to_csv("client_log_24h.csv",index=False)
ap_df_out.to_csv("ap_log_24h.csv",index=False)
fft_df.to_csv("fft_dataset_24h.csv",index=False)

print("\n✅ Simulation complete!")
print(" - client_log_24h.csv")
print(" - ap_log_24h.csv")
print(" - fft_dataset_24h.csv")

# --- Summary stats ---
def summarize(df, cols):
    print("\n📊 Summary Statistics:")
    for c in cols:
        print(f"  {c:<20} → min: {df[c].min():>8.3f},  max: {df[c].max():>8.3f}")

summarize(client_df, ["rssi_dbm","snr_db","throughput_mbps","retry_rate_pct","qoe","distance_m"])
summarize(ap_df_out, ["avg_client_snr_db","throughput_avg_mbps","p95_retry_pct","mean_qoe","mean_distance_m","p95_distance_m","max_distance_m"])
