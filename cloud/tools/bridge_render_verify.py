"""RENDER A REAL JOURNEY TO AUDIO, with the telemetry for the SAME bars.

Straight play -> bridge -> reroute -> commit, captured from the engine's own
transport (subscribed as a browser is), with each bar's admitted set, per-track
share and unit spread logged alongside. The point is that the file and the
numbers describe the same bars: a spread number nobody can hear, and audio
nobody has measured, are each half a claim.

WHY IT EXISTS: on 2026-08-14 a build was shipped, and then rolled back, on
placement telemetry alone -- nobody had listened to it. The operator had to
report by ear what the numbers had already implied. This tool closes that gap:
run it before claiming a build sounds like anything.

TIME IS COLUMN 0. `track_unit_slices` rows are `[t0_s, t1_s, unit_id, mass, q]`;
eight tools in this repo read column 3 (MASS) as seconds for a day. Click
positions here are fractions of the track's own measured SECONDS range.

WARM-UP IS REAL: the first bar on a full-size world costs ~65s (the source bank
decodes), then ~0.4s/bar. This produces one bar before the journey starts so
the holds measure playing, not loading.

Usage:
  ETS_W=/path/world.etsworld OUT=/tmp/bridge.wav \
      python3 cloud/tools/bridge_render_verify.py
"""
import os, struct, sys, threading, time, queue as _q, functools
REPO="/home/user/Geodesic-Mixing"
sys.path.insert(0,REPO); sys.path.insert(0,os.path.join(REPO,"architecture-v6"))
from cloud.companion.engine_bridge import StreamPlayer
import ets.writer.stream as S

W=os.environ.get("ETS_W","/tmp/corpus_world.etsworld")
OUT=os.environ.get("OUT","/tmp/bridge_real.wav")
p=StreamPlayer(W,seed=0,is_trained=True,eigen_n_seed=2,eigen_n_bar=2)
n=len(p.world.tracks); log=[]
orig=S.StreamWriter.write_bar
def spy(self,tilt=None,clamps=None,fence=None):
    r=orig(self,tilt=tilt,clamps=clamps,fence=fence)
    tot=0.0;per={};un={}
    for (_s,tid,uid,_sec,m) in r.rows:
        tot+=float(m); per[int(tid)]=per.get(int(tid),0.0)+float(m); un.setdefault(int(tid),[]).append(int(uid))
    adm=(tuple(range(n)) if fence is None else tuple(t for t in range(n)
         if float(fence.track_mask.get(t,0.0))>=float(fence.openness)))
    log.append({"adm":adm,"sh":{t:round(v/tot,3) for t,v in per.items()} if tot else {},
                "spread":{t:(max(u)-min(u)) for t,u in un.items() if len(u)>1}})
    return r
S.StreamWriter.write_bar=functools.wraps(orig)(spy)

pcm=bytearray(); stop=threading.Event(); q=p.subscribe()
def drain():
    while not stop.is_set():
        try: pcm.extend(q.get(timeout=0.5))
        except _q.Empty: pass
threading.Thread(target=drain,daemon=True).start()
def t_of(tr,f):
    _t,sl=p._straight_track_slices(tr); s=[float(x[0]) for x in sl]   # col 0 = SECONDS
    return min(s)+f*(max(s)-min(s))
def hold(k,limit=180):
    st=len(log); t0=time.time()
    while len(log)-st<k and time.time()-t0<limit: time.sleep(0.2)
p.produce_one_bar()                       # absorb the one-off warm-up
marks={}
p.live_enter(); p.live_start(0,t_of(0,0.20)); hold(6)
marks["bridge 0->4"]=len(pcm)/2/44100.; p.live_click(4,t_of(4,0.30)); hold(8)
marks["reroute ->7"]=len(pcm)/2/44100.; p.live_click(7,t_of(7,0.40)); hold(8)
marks["commit on 7"]=len(pcm)/2/44100.; p.live_click(7,t_of(7,0.42)); hold(5)
p.live_stop(); p.stop(); stop.set(); time.sleep(1)
d=bytes(pcm)
with open(OUT,"wb") as f:
    f.write(b"RIFF"+struct.pack("<I",36+len(d))+b"WAVEfmt ")
    f.write(struct.pack("<IHHIIHH",16,1,1,44100,44100*2,2,16))
    f.write(b"data"+struct.pack("<I",len(d))+d)
print("WROTE %s  %.1fs"%(OUT,len(d)/2/44100.))
for k,v in marks.items(): print("  %-14s at %.1fs"%(k,v))
fen=[b for b in log if len(b["adm"])<n]
print("bridge bars: %d | max spread %s | off-pair mass %.4f"%(
   len(fen), max([max(b["spread"].values()) for b in fen if b["spread"]] or [0]),
   max([sum(v for t,v in b["sh"].items() if t not in b["adm"]) for b in fen] or [0])))
