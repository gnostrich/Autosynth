"""Co-trace of the reference (Jormungandr) set in the corpus's own space."""
import os; os.chdir("/home/user/Geodesic-Mixing/basin")
import sys; sys.path.insert(0,'/home/user/Geodesic-Mixing/basin')
import numpy as np, librosa
from basin import store, channels
from basin.features import frame_features, aggregate_windows
inst=store.load_instrument('instrument_nmf44.npz')
sr=int(inst['config']['sr']); hop=int(inst['config']['hop']); win=float(inst['config']['window_s'])
W=np.asarray(inst['nmf_templates'])
mean=np.asarray(inst['mean']); scale=np.asarray(inst['scale'])
pmean=np.asarray(inst['pca_mean']); pcomp=np.asarray(inst['pca_components'])
print('loading reference (86min)...', flush=True)
y,_=librosa.load('reference_sets/reference_set.mp3', sr=sr, mono=True)
print('  samples:', y.shape, flush=True)
base=frame_features(y, sr, hop)                       # [78, F]
act=channels.track_activations(y, W, hop)             # [8, F]
Fm=min(base.shape[1], act.shape[1])
act=act[:, :Fm]/(act.max()+1e-9)*10.0
frames=np.vstack([base[:, :Fm], act])                 # [86, F]
vecs,startf=aggregate_windows(frames, win, 0.5, sr, hop)   # [nwin, 172]
Xr=((vecs-mean)/scale - pmean) @ pcomp.T              # [nwin, 40] -- corpus space
# also keep the reference's per-window channel activations (mean over window)
step=max(1,int(win*sr/hop*0.5)); nwin=len(vecs)
chA=np.array([act[:, i*step:i*step+int(win*sr/hop)].mean(1) for i in range(nwin) if i*step+2<=Fm])
Xr=Xr[:len(chA)]
np.savez('/tmp/claude-0/-home-user-Geodesic-Mixing/7598b5c5-271e-5d2e-8faf-47a6f11f40d7/scratchpad/reftrace.npz', Xr=Xr, chA=chA)
print('reference trajectory:', Xr.shape, ' saved', flush=True)
# ---- CO-TRACE measurements ----
def acf(x,L):
    x=x-x.mean(0); a=x[:-L]; b=x[L:]; return float((a*b).sum()/(np.sqrt((a*a).sum()*(b*b).sum())+1e-9))
print('\nREFERENCE trajectory autocorr (coherence timescale):')
print('  '+'  '.join('lag%d:%+.2f'%(L,acf(Xr,L)) for L in [1,4,8,16,32,64,128]))
# corpus within-track autocorr for comparison
c=inst['corpus']; Xc=np.asarray(inst['features'])
segs=[Xc[a:b] for (a,b) in c.track_bounds if b-a>200]
print('CORPUS within-track autocorr (for comparison):')
print('  '+'  '.join('lag%d:%+.2f'%(L,np.mean([acf(s,L) for s in segs])) for L in [1,4,8,16,32,64,128]))
# how many channels active at once in the reference (its blend density)?
thr=chA.mean(0)+0.0
active=(chA> chA.mean(0)*0.5).sum(1)
print('\nREFERENCE channels active at once: med=%.1f mean=%.1f /8 (its blend density)'%(np.median(active),active.mean()))
# does the reference move BETWEEN corpus tracks fast or slow? nearest corpus track per window
from scipy.spatial import cKDTree
tree=cKDTree(Xc); dd,ii=tree.query(Xr,k=1)
tid=np.array([c.handles[int(j)].track_id for j in ii])
sw=np.sum(np.diff(tid)!=0)
print('reference maps onto %d distinct corpus tracks; %d switches over %d windows (dwell %.1f)'%(
    len(set(tid)), sw, len(tid), len(tid)/max(sw,1)))
