# EIGEN-modes (E1/E2) — the object's native control basis

Read-only measurement, demo.etsworld (M=2, D=5 observables: region0, region1,
density, cont, novelty). Prereg: scratchpad/eigen/PREREG.md. Ensemble N_SEED=24
× N_BAR=32, central-difference response h=0.75, floor = p97.5 of the shuffled-
null eigenspectrum. Wall 173s. Repo byte-identical (this findings doc only).

## RESULT: k = 4

The honest control basis is the eigenspectrum of the SYMMETRIZED RESPONSE
KERNEL Ksym = (K+K^T)/2, K[i,j] = d<obs_i>/du_lane_j (NOT the marginal
covariance — see the P5 trap below). Eigenvalues (= honest gains, EP-1):

| mode | eigenvalue (gain) | dominant composition | reading |
|---|---|---|---|
| 1 | 5.73 | 0.99·novelty (− 0.16·density) | strongest knob |
| 2 | 2.43 | 0.68·region1 + 0.66·density + 0.32·region0 | fill/density blend |
| 3 | 1.14 | 0.76·region0 − 0.59·region1 + 0.25·density | region contrast |
| 4 | **−0.17** | 0.98·cont | continuity — near-dead / inverted (P5) |
| — | 0.0007 | (novelty residual) | below floor → NOT a knob |

Floor ≈ 0.137 (null) / p99 0.147. Modes 1–4 clear it by magnitude; the 5th
does not. **k = 4**, self-sizing by the same measured-floor law as M.

## THE P5 TRAP (why response kernel, not covariance)
The marginal covariance is FOOLED here: continuity has the LARGEST marginal
variance (8.08) yet ZERO steering response — variance and response decouple
exactly when FDT breaks (the armed-but-inert P5 finding). A covariance-based
panel would render continuity as a huge knob that does nothing, re-committing
the disarmed lie in the eigenbasis. The RESPONSE kernel correctly gives
continuity a near-floor negative gain (−0.17) → a dead/near-dead mode. The
directive's word "CONSTRAINED covariance ... ceiling-saturated directions show
~zero" is satisfied by the response kernel, not the raw covariance.

## Sign honesty
Mode 4's gain is NEGATIVE (inverted response). It is retained (magnitude clears
floor) but flagged sign<0 so the panel renders it truthfully, not as a normal
favour/disfavour axis. EP-1 checks gain==eigenvalue including sign.

## Persistence JSON (bridge emits in world_info)
{"modes":[{"index":i,"gain":eigenvalue,"sign":±1,"composition":{obs:weight,...},
"earned_word":str|null},...],"eigen_floor":floor,"k":k,"basis":"response_kernel_sym"}

## Live-set note
The operator's set is M=3 flat-B; it RECOMPUTES its own k+modes on load
(operating-point objects). This demo run establishes the METHOD + fixture k;
the panel self-sizes to whatever the loaded world reports.
