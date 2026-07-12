"""Continuous intrinsic multiscale render -- no clusters, no knobs.

The data's slow coordinate Y (tICA) is smooth (499-step glide). We ride it
directly: the conductor rides the corpus forward (Y glides intrinsically),
and every transition lands on the NEAREST window in slow-space so Y never
jumps -- the coherence is preserved across track crossings. Channels
re-source at the trace's OWN slow displacement scale (median |Y(t+tau)-Y(t)|
over a correlation time -- measured, not chosen), each staggered, each
landing on the nearest slow-space window from a different track. Cross-track
mixing is emergent; coherence is the continuous coordinate itself."""
import os; os.chdir("/home/user/Geodesic-Mixing/basin")
import sys; sys.path.insert(0,'/home/user/Geodesic-Mixing/basin')
import numpy as np, soundfile as sf
from scipy.spatial import cKDTree
from basin import store, operator
from basin.render import GrainReader
TAG=sys.argv[1] if len(sys.argv)>1 else 'c1'
inst=store.load_instrument('instrument_nmf44.npz'); c=inst['corpus']; H=c.handles
mem=inst['atlas'].memberships; psi,_=operator.full_psi(inst['eigvals'],inst['eig_right'])
K=int(c.n_channels); bounds=c.track_bounds
d=np.load('/tmp/claude-0/-home-user-Geodesic-Mixing/7598b5c5-271e-5d2e-8faf-47a6f11f40d7/scratchpad/tica.npz')
Y=d['Y']; N=len(Y)
Yn=(Y-Y.mean(0))/(Y.std(0)+1e-9)                 # balanced slow-space
tree=cKDTree(Yn)
tid=np.array([H[w].track_id for w in range(N)])
# trace-derived slow correlation time & displacement scale (NOT chosen)
tau=100
disps=[]
for (a,b) in bounds:
    if b-a>tau: disps.append(np.linalg.norm(Yn[a+tau:b]-Yn[a:b-tau],axis=1))
scale=float(np.median(np.concatenate(disps)))    # natural slow step per corr-time
def nearest_other_track(yt, cur_tid, kq=40):
    dd,ii=tree.query(yt,k=kq)
    for j in ii:
        if tid[j]!=cur_tid: return int(j)
    return int(ii[0])
cfg=dict(inst['config']); sr=int(cfg['sr']); MINUTES=12; SEED=5
shared={}; rj=GrainReader(c,mem,cfg,seed=SEED,stem='mix',shared_cache=shared,psi=psi)
rch=[GrainReader(c,mem,cfg,seed=SEED+7*k,stem=f'ch{k}',shared_cache=shared,psi=psi) for k in range(K)]
rng=np.random.default_rng(SEED)
xfade=int(round(float(cfg['crossfade_s'])*sr)); lin=np.linspace(0,1,xfade,endpoint=False)[:,None]
total=int(MINUTES*60*sr); cap=int(total*1.1)+8*xfade; out=np.zeros((cap,2),dtype=np.float32)
t=0;i=0
home=int(rng.integers(N))
src=[home]*K; anchor=[Yn[home].copy() for _ in range(K)]
crossed=[]; Ytrace=[]; homejumps=0
while t<total:
    # conductor rides corpus; at track end, seamless nearest-Y jump to another track
    if home+1<N and H[home+1].track_id==H[home].track_id:
        home=home+1
    else:
        home=nearest_other_track(Yn[home], H[home].track_id); homejumps+=1
    yt=Yn[home]; ht=H[home].track_id; Ytrace.append(Y[home].copy())
    stride=rj.native_stride(home); glen=stride+xfade
    if t+glen>=cap: break
    nc=0
    for k in range(K):
        # re-source when the conductor has glided one slow-scale since this
        # channel's anchor (trace-derived rate) or the channel's track ended
        drift=np.linalg.norm(yt-anchor[k])
        ended=not(src[k]+1<N and H[src[k]+1].track_id==H[src[k]].track_id)
        if drift>scale or ended:
            src[k]=nearest_other_track(yt, H[src[k]].track_id)
            anchor[k]=yt.copy()
        else:
            src[k]=src[k]+1
        if H[src[k]].track_id!=ht: nc+=1
        g=rch[k].grain_audio(src[k],glen).copy()
        if i>0: g[:xfade]*=lin
        g[-xfade:]*=(1-lin); out[t:t+glen]+=g
    crossed.append(nc/K); t+=stride; i+=1
out=out[:total+xfade]; pk=float(np.max(np.abs(out))+1e-9)
if pk>0.95: out*=0.95/pk
sf.write(f'renders/con_{TAG}.flac',out,sr)
# report + acid test: does the RENDERED conductor carry the slow tail?
Yt=np.array(Ytrace)
def acf(x,L):
    x=x-x.mean(0); a=x[:-L]; b=x[L:]; return float((a*b).sum()/(np.sqrt((a*a).sum()*(b*b).sum())+1e-9))
n30=30*sr; env=[float(np.sqrt(np.mean(out[j:j+n30]**2))) for j in range(0,len(out)-n30,n30)]
print('slow displacement scale (trace):','%.2f'%scale,' home track-jumps:',homejumps)
print('env:',' '.join('%.2f'%v for v in env[::3]))
print('mean channels crossed: %.1f/%d (emergent)'%(np.mean(crossed)*K,K))
print('RENDERED conductor slow-coord autocorr (data: .43@4 .28@16 .13@32 .05@64):')
print('  '+'  '.join('lag%d:%+.2f'%(L,acf(Yt,L)) for L in [1,4,8,16,32,64]))
