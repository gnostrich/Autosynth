"""Small synthetic stage-3 fixtures so the harness runs fast and offline.

``make_synthetic_protos`` builds a handful of real ``roles.Prototypes`` with the
exact shape/normalization contract that ``roles.extract_prototypes`` produces, plus
a shared latent so the traffic operator has structure (effective rank > 1) and the
anchor-fit does real work. The prototypes carry PRIVATE timbre/chroma too — so the
raw-never-uploaded tests can prove those never reach the wire.

A minimal prototypes fixture is sufficient to exercise service + client + harness
end-to-end. A full-corpus run would replace this with the local ingest
(``ets.ingestion.pipeline`` -> ``roles.extract_prototypes`` over the cached tracks);
that path is heavier (librosa/beat_this/scikit-learn) and needs the audio, so it is
run on the device, not in this offline harness.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ets.geometry import roles


def _one_proto(rng, latent, K=6, S=8, N=8, d=4):
    # timbre near a shared latent (so tracks share cross-track role structure)
    timbre = latent[None, :] + 0.6 * rng.standard_normal((K, d))
    # pairwise euclidean cost, symmetric, zero diagonal, RMS-normalized (~1)
    diff = timbre[:, None, :] - timbre[None, :, :]
    cost = np.linalg.norm(diff, axis=2)
    cost = 0.5 * (cost + cost.T)
    np.fill_diagonal(cost, 0.0)
    off = cost[~np.eye(K, dtype=bool)]
    cost = cost / (np.sqrt(np.mean(off ** 2)) + 1e-12)

    mass = rng.random(K) + 0.1
    mass = mass / mass.sum()

    slot_hist = rng.random((K, S)) + 0.05
    slot_hist = slot_hist / slot_hist.sum() * 1.0          # sums to ~1 over all
    band_profile = rng.random((K, N)) + 0.05
    band_profile = band_profile / band_profile.sum(1, keepdims=True) * mass[:, None]

    chroma = np.abs(rng.standard_normal((K, 12)))
    chroma = chroma / chroma.sum(1, keepdims=True)

    return roles.Prototypes(
        track_id=-1, cost=cost, mass=mass, slot_hist=slot_hist,
        band_profile=band_profile, timbre=timbre, chroma=chroma)


def make_synthetic_protos(n_tracks: int = 4, K: int = 6, seed: int = 0):
    """A small corpus of ``n_tracks`` prototype spaces with shared role structure."""
    rng = np.random.default_rng(seed)
    latents = rng.standard_normal((3, 4))                  # three shared roles
    protos = []
    for t in range(n_tracks):
        latent = latents[t % len(latents)]
        P = _one_proto(rng, latent, K=K)
        P = roles.Prototypes(track_id=t, cost=P.cost, mass=P.mass,
                             slot_hist=P.slot_hist, band_profile=P.band_profile,
                             timbre=P.timbre, chroma=P.chroma)
        protos.append(P)
    return protos
