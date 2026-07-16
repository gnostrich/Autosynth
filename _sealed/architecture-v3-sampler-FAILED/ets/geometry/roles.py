"""Role space (spec §4, §5): per-track role prototypes and the GW-typed coupling
into shared anchors.

Why prototypes: a track carries ~1e4 (slot,band) units. Coupling every unit to
anchors by Gromov-Wasserstein would be O(n^2) in n~1e4. Instead each track is
QUANTISED, WITHIN the track only, into K_LOCAL role prototypes (mass-weighted
clustering on within-track descriptors). A prototype is a small metric-measure
atom: a mass, a within-track gauge-quotiented geometry (prototype-prototype
cost), a metrical-slot histogram, and a band profile. Cross-track traffic then
runs prototype-space -> anchors via GW (ot.entropic_gw), which uses ONLY internal
distances — no coordinate crosses a track boundary (I-2). This is the spec's
"intrinsic geometry to anchors, GW-typed" (T1) made computable.

Gauge (spec §3): clustering is done inside one track, where the gauge frame is
fixed, so it is gauge-agnostic. The prototype-prototype cost is built from the
same gauge-quotiented metrics as CostStructure (timbre L2, transposition-quotient
pitch class, circular metrical) and is normalised within-track (RMS -> 1) so no
absolute-scale / loudness coordinate leaks across the boundary.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

K_LOCAL = 12          # role prototypes per track
S_SLOTS = 8           # metrical slots on the circle (phase bins)
N_BANDS = 8


@dataclass
class Prototypes:
    """A track as a small metric-measure space in role coordinates (all private
    to the track; only cost + histograms leave, never raw unit coordinates)."""
    track_id: int
    cost: np.ndarray       # (K,K) within-track gauge-quotiented prototype cost, RMS~1
    mass: np.ndarray       # (K,) prototype masses, sum = 1
    slot_hist: np.ndarray  # (K, S_SLOTS) metrical-slot mass profile, rows sum to mass
    band_profile: np.ndarray  # (K, N_BANDS) band mass profile, rows sum to mass
    timbre: np.ndarray     # (K, 4) mean timbre (kept private; NOT used cross-track)
    chroma: np.ndarray     # (K, 12) mean chroma (private; quotient taken in cost)


def _quotient_pair_costs(timbre, chroma, phase_sc):
    """Gauge-quotiented KxK costs for each channel, each normalised to RMS 1."""
    K = timbre.shape[0]
    Ct = np.zeros((K, K)); Cp = np.zeros((K, K)); Cm = np.zeros((K, K))
    for i in range(K):
        for j in range(K):
            Ct[i, j] = np.linalg.norm(timbre[i] - timbre[j])
            # transposition quotient: min over the 12 cyclic chroma rotations
            best = np.inf
            a = chroma[i]
            for r in range(12):
                d = np.linalg.norm(a - np.roll(chroma[j], r))
                if d < best:
                    best = d
            Cp[i, j] = best
            # circular metrical distance from (sin,cos) embedding
            Cm[i, j] = 1.0 - float(phase_sc[i] @ phase_sc[j]) / 2.0

    def _norm(M):
        off = M[~np.eye(K, dtype=bool)]
        s = float(np.sqrt(np.mean(off ** 2))) if off.size else 1.0
        return M / (s if s > 0 else 1.0)
    return _norm(Ct) + _norm(Cp) + _norm(Cm)


def extract_prototypes(track, k_local: int = K_LOCAL, seed: int = 0) -> Prototypes:
    """Quantise a Track into k_local role prototypes (within-track clustering)."""
    from sklearn.cluster import KMeans
    u = track.units
    masses = np.asarray(track.masses, float)
    band = u["band"].astype(int)
    phase = u["phase"].astype(float)
    timbre = track.C_timbre.desc                      # (n,4) already standardised
    chroma = track.C_pitchclass.desc                  # (n,12) L1-normalised

    # within-track clustering features: timbre + band one-hot + phase (sin,cos).
    ph = 2 * np.pi * phase
    band_oh = np.zeros((len(u), N_BANDS)); band_oh[np.arange(len(u)), band] = 1.0
    feat = np.concatenate([timbre,
                           1.5 * band_oh,
                           np.stack([np.sin(ph), np.cos(ph)], 1)], axis=1)
    w = masses + 1e-9
    k = min(k_local, len(np.unique(feat, axis=0)))
    km = KMeans(n_clusters=k, n_init=4, random_state=seed).fit(feat, sample_weight=w)
    lab = km.labels_

    P = k
    mass = np.zeros(P); tim = np.zeros((P, 4)); chr_ = np.zeros((P, 12))
    slot_hist = np.zeros((P, S_SLOTS)); band_prof = np.zeros((P, N_BANDS))
    phase_sc = np.zeros((P, 2))
    slot = np.clip((phase * S_SLOTS).astype(int), 0, S_SLOTS - 1)
    for p in range(P):
        m = lab == p
        wm = w[m]; tot = wm.sum() + 1e-12
        mass[p] = wm.sum()
        tim[p] = (timbre[m] * wm[:, None]).sum(0) / tot
        chr_[p] = (chroma[m] * wm[:, None]).sum(0) / tot
        cph = (np.cos(ph[m]) * wm).sum() / tot
        sph = (np.sin(ph[m]) * wm).sum() / tot
        n = np.hypot(cph, sph) + 1e-12
        phase_sc[p] = [sph / n, cph / n]
        np.add.at(slot_hist[p], slot[m], wm)
        np.add.at(band_prof[p], band[m], wm)
    # normalise masses to a probability (role DISTRIBUTION; absolute loudness is a
    # gauge quantity and must not cross the boundary, I-2).
    mass = mass / (mass.sum() + 1e-12)
    slot_hist = slot_hist / (slot_hist.sum() + 1e-12)
    band_prof = band_prof / (band_prof.sum(1, keepdims=True) + 1e-12) * mass[:, None]

    cost = _quotient_pair_costs(tim, chr_, phase_sc)
    return Prototypes(track_id=track.track_id, cost=cost, mass=mass,
                      slot_hist=slot_hist, band_profile=band_prof,
                      timbre=tim, chroma=chr_)


def role_distance(Pa: Prototypes, Pb: Prototypes, eps: float = 0.05) -> float:
    """Gauge-invariant role distance between two tracks = entropic GW between
    their prototype spaces. Uses internal distances only (I-2)."""
    from ..functional import ot
    _, dist = ot.entropic_gw(Pa.cost, Pb.cost, Pa.mass, Pb.mass, eps)
    return float(dist)


def role_distance_matrix(protos, eps: float = 0.05) -> np.ndarray:
    n = len(protos)
    D = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            D[i, j] = D[j, i] = role_distance(protos[i], protos[j], eps)
    return D
