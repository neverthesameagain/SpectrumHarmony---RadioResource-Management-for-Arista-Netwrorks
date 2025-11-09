#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ARISTA RRM+ Unified Synthetic Data Generator (Final v11)
--------------------------------------------------------
Outputs (Part-1 compliant):

  • data/Aplog_all_channels.csv         → full telemetry (all APs)
  • data/Aplog_<band>_GHz_<ch>.csv      → per-band / per-channel telemetry
  • data/fft_dataset.csv                → full FFT dataset
  • data/FFT_<band>_GHz_<ch>.csv        → per-band / per-channel FFT samples
  • data/sensing_events.csv             → per-event table (cf/bw/duty/conf)
  • docs/airtime_cost.txt               → sensing airtime ratio
  • docs/kpi_summary.csv                → KPI summary (edge clients included)
  • docs/schema.md                      → column dictionary and units

Bands: 2.4 GHz + 5 GHz (DFS included)
Non-Wi-Fi classes: BLE, ZigBee, Microwave, FHSS, Radar
Physics: FSPL + log-distance (n≈2.6) + shadowing (σ≈3.5 dB)
Noise: −174 + 10 log₁₀(B) + NF (+ 1 dB jitter)
Airtime: Wi-Fi + non-Wi-Fi + sensing (< 2 %)
"""
import os, math, random, argparse, logging
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import numpy as np, pandas as pd

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("RRMPlusSim")

# ---------- Constants ----------
SEED = int(os.getenv("RRMPLUS_SEED", "42"))
np.random.seed(SEED); random.seed(SEED)

OUT = Path("data"); DOCS = Path("docs")
for p in (OUT, DOCS): p.mkdir(exist_ok=True)

CH24 = list(range(1,15))
DFS_CH = [52,56,60,64,100,104,108,112,116,120,124,128,132,136,140,144]
CH5  = [36,40,44,48] + DFS_CH + [149,153,157,161]
WIDTHS = [20,40,80]
PHY_MAX_24, PHY_MAX_5 = 72.2, 433.0
WIDTH_SCALE = {20:1.0,40:1.7,80:3.0}

DEFAULT_SIM_HOURS=1.0
DEFAULT_SCAN_PERIOD=10.0
DEFAULT_SENSING_TIME=0.12
CLIENTS_PER_AP=20
CELL_R=12.0
RSSI_MIN,RSSI_MAX=-94.0,-30.0
NF_24,NF_5=6.0,6.5
FFT_CLASSES=["wifi","BLE","ZigBee","Microwave","FHSS","Radar"]
DIURNAL_24=np.array([0.20,0.18,0.16,0.16,0.18,0.25,0.35,0.55,0.70,0.78,
                     0.82,0.85,0.88,0.90,0.92,0.95,0.96,0.92,0.85,0.75,
                     0.60,0.50,0.40,0.30])

@dataclass
class AP:
    id:str; band:str; ch:int; width:int; tx:float; x:float; y:float; phy:float; gain:float=2.0
@dataclass
class Client:
    id:str; apid:str; x:float; y:float; d:float

# ---------- Helpers ----------
def width_scale(w): return WIDTH_SCALE.get(w,1.0)
def ch2mhz(band,ch): return 2407+5*ch if band=="2.4" else 5000+5*ch
def noise_floor_dbm(band,bw):
    base=-174+10*math.log10(bw*1e6)
    nf=NF_24 if band=="2.4" else NF_5
    return base+nf+np.random.normal(0,1.2)
def fspl_db(d,f):
    return 20*math.log10(max(d,0.1))+20*math.log10(f)-27.55
def rssi_dbm(d,ap):
    f=ch2mhz(ap.band,ap.ch); eirp=ap.tx+ap.gain
    pl=fspl_db(1,f)+10*2.6*math.log10(max(d,1))
    return float(np.clip(eirp-pl+np.random.normal(0,3.5),RSSI_MIN,RSSI_MAX))
def retry_pct_from_snr(s,i): return float(np.clip(100/(1+math.exp(0.38*(s-18)))+35*i+np.random.normal(0,2),0,100))
def thr_mbps_from_snr(s,b,w,r): 
    phy=(PHY_MAX_24 if b=="2.4" else PHY_MAX_5)*width_scale(w)
    eff=np.clip((s+5)/40,0,1)*(1-r/120)
    return float(max(0,phy*eff*(0.9+np.random.rand()*0.12)))
def qoe_from(s,r):
    s=np.clip((s+5)/40,0,1); r=1-np.clip(r/50,0,1)
    return float(5*(0.7*s+0.3*r))
def uplink_per_from_snr(s): return float(100/(1+math.exp(0.3*(s-15))))
def diurnal_frac(ts): return float(DIURNAL_24[ts.hour])
def overlap_ratio(band,ch,w,cf,bw):
    if bw<=0: return 0
    a_lo,a_hi=ch2mhz(band,ch)-w/2,ch2mhz(band,ch)+w/2
    e_lo,e_hi=cf-bw/2,cf+bw/2
    inter=max(0,min(a_hi,e_hi)-max(a_lo,e_lo))
    return inter/(a_hi-a_lo)

def gen_aps():
    xs=np.linspace(0,66,14); ys=np.linspace(0,44,8)
    coords=[(float(x),float(y)) for y in ys for x in xs]
    aps=[]; k=0
    for ch in CH24:
        tx=float(np.random.randint(14,21))
        aps.append(AP(f"AP24_{ch}","2.4",ch,20,tx,*coords[k],PHY_MAX_24)); k+=1
    for ch in CH5:
        w=20 if ch in DFS_CH and np.random.rand()<0.9 else int(np.random.choice(WIDTHS,p=[.7,.25,.05]))
        tx=float(np.random.randint(14,23))
        aps.append(AP(f"AP5_{ch}","5",ch,w,tx,*coords[k],PHY_MAX_5*width_scale(w))); k+=1
    return aps

def gen_clients(aps):
    cs=[]
    for a in aps:
        for i in range(CLIENTS_PER_AP):
            r=CELL_R*math.sqrt(np.random.rand()); t=np.random.rand()*2*math.pi
            cs.append(Client(f"C_{a.id}_{i}",a.id,a.x+r*math.cos(t),a.y+r*math.sin(t),r))
    return cs
def random_walk(cs): 
    for c in cs: c.x+=np.random.normal(0,0.15); c.y+=np.random.normal(0,0.15)

def run(sim_hours,scan_period,sense_time,start_ts,orchestrated=False):
    n_steps=int(sim_hours*3600/scan_period); start=datetime.fromisoformat(start_ts)
    aps,cs=gen_aps(),gen_clients(gen_aps())
    ap_rows,fft_rows,event_rows=[],[],[]
    total_sense=total_time=0
    for step in range(n_steps):
        ts=start+timedelta(seconds=step*scan_period)
        random_walk(cs)
        for a in aps:
            c_list=[c for c in cs if c.apid==a.id]
            nf=noise_floor_dbm(a.band,a.width)
            load=np.clip((0.25+0.75*diurnal_frac(ts))*(1.1 if a.band=="2.4" else 1.0)*(0.8+0.4*np.random.rand()),0.05,0.98)
            busy_wifi=scan_period*load*0.55
            label=random.choices(FFT_CLASSES,weights=[0.5,0.1,0.1,0.1,0.1,0.1])[0]
            if a.band=="5" and a.ch in DFS_CH and np.random.rand()<(0.25 if not orchestrated else 0.12): label="Radar"
            bins=np.random.normal(nf-3,3,64)
            ev_center,ch_bw,ev_duty,ev_power=ch2mhz(a.band,a.ch),0,0,nf-10
            if label=="Radar":
                ch_bw=np.random.choice([1,5,10,float(a.width)]); ev_duty=np.random.uniform(0.02,0.2)
                ev_power=nf+np.random.uniform(-30,5); ev_center+=np.random.uniform(-10,10)
            elif label=="FHSS":
                ch_bw=np.random.uniform(1,10); ev_duty=np.random.uniform(0.1,0.5)
                ev_center+=((step%5)-2)*5; ev_power=nf+np.random.uniform(-25,-10)
            elif label!="wifi":
                ch_bw=np.random.uniform(1,min(40,a.width)); ev_duty=np.random.uniform(0.05,0.8)
                ev_power=np.random.uniform(nf-40,nf-10); ev_center+=np.random.uniform(-30,30)
            ovl=overlap_ratio(a.band,a.ch,a.width,ev_center,ch_bw)
            ovl_eff=ovl*(0.75 if orchestrated and label!="wifi" else 1)
            nonwifi_time=scan_period*ovl_eff*ev_duty*0.65
            interf_index=np.clip(np.random.rand()*(0.7 if orchestrated else 1),0,1)
            snrs,thrs,rtys,qoes,pers,rssis=[],[],[],[],[],[]
            for c in c_list or [Client("temp",a.id,0,0,CELL_R*0.7)]:
                s_rssi=rssi_dbm(c.d,a); s_snr=s_rssi-nf
                r=retry_pct_from_snr(s_snr,interf_index)
                th=thr_mbps_from_snr(s_snr,a.band,a.width,r)
                q=qoe_from(s_snr,r); p=uplink_per_from_snr(s_snr)
                rssis.append(s_rssi); snrs.append(s_snr); thrs.append(th); rtys.append(r); qoes.append(q); pers.append(p)
            avg_snr,avg_thr,p95r,mean_qoe,avg_per,mean_rssi=np.mean(snrs),np.mean(thrs),np.percentile(rtys,95),np.mean(qoes),np.mean(pers),np.mean(rssis)
            busy=np.clip(busy_wifi+sense_time+nonwifi_time,0,scan_period)
            airtime=busy/scan_period*100
            total_sense+=sense_time; total_time+=scan_period
            fft_row=dict(timestamp=ts.isoformat(),ap_id=a.id,band=a.band,channel=a.ch,label=label,
                         center_mhz=ev_center,bw_mhz=ch_bw,duty=ev_duty,power_dbm=ev_power,
                         **{f"fft_bin_{i}":float(b) for i,b in enumerate(bins)})
            fft_rows.append(fft_row)
            conf=float(np.clip(np.random.beta(8,2) if label!="wifi" else np.random.beta(2,8),0,1))
            event_rows.append(dict(timestamp=ts.isoformat(),ap_id=a.id,band=a.band,channel=a.ch,
                                   center_freq_mhz=ev_center,bandwidth_mhz=ch_bw,
                                   duty_cycle=ev_duty,class_label=label,confidence=conf))
            ap_rows.append(dict(TIMESTAMP=ts.isoformat(),AP_ID=a.id,BAND=a.band,CHANNEL=a.ch,
                                CHANNEL_WIDTH=a.width,TX_POWER_DBM=a.tx,NOISE_FLOOR_DBM=nf,
                                AVG_CLIENT_SNR_DB=avg_snr,THROUGHPUT_AVG_Mbps=avg_thr,P95_RETRY_PCT=p95r,
                                MEAN_QOE=mean_qoe,UL_PER=avg_per,BUSY_TIME=busy,TOTAL_TIME=scan_period,
                                AIRTIME_UTILIZATION=airtime,NWIFI_DETECTED=(label!="wifi"),NWIFI_TYPE=label,
                                CLIENTS=len(c_list),MEAN_RSSI_DBM=mean_rssi,CENTER_MHZ=ch2mhz(a.band,a.ch)))
    ap_df,fft_df,evt_df=pd.DataFrame(ap_rows),pd.DataFrame(fft_rows),pd.DataFrame(event_rows)

    # ----- global CSVs -----
    req_cols=["TIMESTAMP","AP_ID","BAND","CHANNEL","CHANNEL_WIDTH","TX_POWER_DBM","NOISE_FLOOR_DBM",
              "AVG_CLIENT_SNR_DB","THROUGHPUT_AVG_Mbps","P95_RETRY_PCT","MEAN_QOE","UL_PER",
              "BUSY_TIME","TOTAL_TIME","AIRTIME_UTILIZATION","NWIFI_DETECTED","NWIFI_TYPE"]
    ap_df.to_csv(OUT/"Aplog_all_channels.csv",index=False,
                 columns=req_cols+[c for c in ap_df.columns if c not in req_cols])
    fft_df.to_csv(OUT/"fft_dataset.csv",index=False)
    evt_df.to_csv(OUT/"sensing_events.csv",index=False)

    # ----- per-band / per-channel splits -----
    for (band,ch),sub in ap_df.groupby(["BAND","CHANNEL"]):
        fname=f"Aplog_{band.replace('.','_')}_GHz_{ch}.csv"
        sub.to_csv(OUT/fname,index=False,columns=req_cols+[c for c in sub.columns if c not in req_cols])
    for (band,ch),sub in fft_df.groupby(["band","channel"]):
        fname=f"FFT_{band.replace('.','_')}_GHz_{ch}.csv"
        sub.to_csv(OUT/fname,index=False)

    # ----- Airtime + KPIs -----
    sense_ratio=total_sense/total_time if total_time else 0
    (DOCS/"airtime_cost.txt").write_text(f"sensing_airtime_ratio={sense_ratio:.4f}\n")
    edge_mask=(ap_df["MEAN_RSSI_DBM"]>=-70)&(ap_df["MEAN_RSSI_DBM"]<=-65)
    edge=ap_df[edge_mask]
    kpi=pd.DataFrame([dict(sim_hours=sim_hours,tick_seconds=scan_period,
                           aps_total=ap_df["AP_ID"].nunique(),
                           mean_qoe_all=ap_df["MEAN_QOE"].mean(),
                           p95_retry_all=ap_df["P95_RETRY_PCT"].quantile(0.95),
                           ul_per_all=ap_df["UL_PER"].mean(),
                           mean_qoe_edge=edge["MEAN_QOE"].mean() if len(edge) else np.nan,
                           p95_retry_edge=edge["P95_RETRY_PCT"].quantile(0.95) if len(edge) else np.nan,
                           ul_per_edge=edge["UL_PER"].mean() if len(edge) else np.nan,
                           sensing_airtime_ratio=sense_ratio,orchestrated=int(orchestrated))])
    kpi.to_csv(DOCS/"kpi_summary.csv",index=False)

    # ----- Schema doc -----
    schema=f"""# RRM+ Simulator Schema v11

### Global outputs
Aplog_all_channels.csv, FFT_dataset.csv, sensing_events.csv, per-band/per-channel splits.
Columns are identical and ordered for backward compatibility.

TIMESTAMP,AP_ID,BAND,CHANNEL,CHANNEL_WIDTH,TX_POWER_DBM,NOISE_FLOOR_DBM,
AVG_CLIENT_SNR_DB,THROUGHPUT_AVG_Mbps,P95_RETRY_PCT,MEAN_QOE,UL_PER,
BUSY_TIME,TOTAL_TIME,AIRTIME_UTILIZATION,NWIFI_DETECTED,NWIFI_TYPE,
CLIENTS,MEAN_RSSI_DBM,CENTER_MHZ
"""
    (DOCS/"schema.md").write_text(schema)
    log.info("Simulation complete. Airtime=%.2f%%  CSVs in %s",sense_ratio*100,OUT)

def parse_args():
    p=argparse.ArgumentParser()
    p.add_argument("--hours",type=float,default=DEFAULT_SIM_HOURS)
    p.add_argument("--scan",type=float,default=DEFAULT_SCAN_PERIOD)
    p.add_argument("--sense",type=float,default=DEFAULT_SENSING_TIME)
    p.add_argument("--start",type=str,default="2025-11-02T00:00:00")
    p.add_argument("--orchestrated",type=int,default=0)
    return p.parse_args()

if __name__=="__main__":
    a=parse_args()
    run(a.hours,a.scan,a.sense,a.start,bool(a.orchestrated))
