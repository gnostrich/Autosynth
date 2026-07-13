# PREREG — pre-registration ledger for ETS gates

Discipline (spec §13, builder rule 4, auditor §4):

- No gate G0–G6 may run before its pre-registration entry below is COMMITTED.
- Each entry states: hypothesis, procedure, null construction, kill condition.
- The null must be calibrated (solver floor measured first).
- No metric named in a prereg may also appear in any objective/loss (I-5).
- `REGISTRY.jsonl` is append-only and committed before each run; a run that
  invalidates an instrument is fixed by a NEW pre-registered entry, never by
  editing an old one.

Entry template (copy per gate, fill, commit before running):

## G<k> — <name>  (status: DRAFT | REGISTERED | RUN)
- prereg_commit: <sha, filled at registration>
- hypothesis:
- procedure:
- null construction (and solver-floor calibration):
- kill condition:
- registry_ids: [<REGISTRY.jsonl ids appended for this gate>]

---

## G0 — ingestion + beat-clock sanity + reconstruction identity  (status: REGISTERED)
- prereg_commit: this commit (registers the entry); code_under_test: 78cf26f
- registry_ids: [g0-ingestion-2026-07-13]
- corpus: corpus/*.mp3, 20 tracks, 44.1 kHz internal.
- tool logged: beat_this==1.1.0 / checkpoint final0 / dbn=False.

- hypothesis:
  (i)  Each corpus track carries a measurable, regular pulse, and the derived
       beat grid sits on the audio's real events (grid→onset aligned).
  (ii) The fixed-filterbank unitization is an IDENTITY representation: scheduling
       a track's own units at their own tatum slots (identity transform,
       rectangular overlap-add) reproduces the track over the grid-covered span
       within tolerance. (Because the filterbank is partition-of-unity /
       perfect-reconstruction, this half certifies COVERAGE + SCHEDULING
       completeness — an off-by-one, uncovered lead-in/out, or mis-placed slot
       would break it. Stated openly, not as a hidden strength.)

- procedure:
  Per track: load→44.1k mono; beat_this→beats,downbeats; build tatum grid
  (2 tatums/beat) + onset-refined boundaries; STFT partition-of-unity 8-band
  filterbank; per-(slot,band) unit with mass + descriptors.
  (i)  pulse_present := n_beats ≥ 32 AND fraction of IBIs within [0.5,2.0]×median
       ≥ 0.80 (breakdown gaps tolerated). align := median beat→nearest-onset
       distance over beats with an onset within 100 ms search window.
       Report modal beats-per-bar (info).
  (ii) recon := relative L2 of (own-unit overlap-add) vs source over the
       grid-covered span [first tatum, last tatum].
  Domain note: wall-clock outside [first tatum, last tatum] is not part of the
  metrical object; covered_fraction reported per track.

- pass tolerances (pre-stated, fixed; NOT used in any objective — I-5):
  - MIN_BEATS = 32
  - regular-IBI fraction ≥ 0.80
  - median grid→onset alignment ≤ 50 ms
  - reconstruction relative L2 ≤ 1e-3  (−60 dB)
  A track PASSES G0 iff pulse_present ∧ (median_align ≤ 50 ms) ∧ (recon ≤ 1e-3).

- null construction (and solver-floor calibration):
  Reconstruction floor measured first on synthetic audio (band-sum round-trip):
  observed ≈ 1e-8 (−157 dB) ≫ below the 1e-3 tolerance, so the tolerance is not
  floor-limited — it is a coverage/scheduling budget with ~5 orders of margin.
  Beat-clock null: a shuffled/rotated grid (beats replaced by uniform-random
  times at the same rate) would give median align ≈ (tatum/2) ~ 90–180 ms and
  regular-IBI fraction near the [0.5,2.0] band's chance mass; passing tracks must
  beat that by construction (median align target ≤ 50 ms). No trained metric
  here, so no learned-solver floor applies.

- kill condition (WALL PROTOCOL, spec §2):
  - If a track has pulse_present == False → it has NO measurable pulse: STOP,
    record as a wall, do NOT special-case or patch the clock.
  - If any track's recon > 1e-3 with correct coverage → filterbank/unitization
    cannot meet the identity: STOP, re-derive; do not loosen the tolerance.
  Either outcome is reported to the human as a candidate spec revision, never
  silently worked around.
