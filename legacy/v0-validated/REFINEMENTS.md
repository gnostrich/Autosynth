# REFINEMENTS — tracked orchestrator/build decisions

Design decisions that refine (but do not revise) `ets-spec-v0.md`. Each is a
choice the spec leaves open, recorded so it is visible and revisitable. A true
spec REVISION (a claim the spec makes that we change) is NOT recorded here — that
goes through a versioned spec change. These are the free parameters and calls
made within the spec's envelope.

---

## R1 — beat clock: dbn=False retained for v0  (2026-07-13, orchestrator DECISION)

Decision: `beat_this` is run with `dbn=False` (no DBN post-processing) for v0.
This is an orchestrator decision, tracked, not changed now.

Consequence, surfaced honestly: the bar-level metrical circle degrades to a
beat-level phase on ~9/20 corpus tracks — beats_per_bar_mode collapses to 1 or 2
rather than a stable 4 (see g0_results.json: tracks 1,10,11,12,14,15,16,18,19
report beats_per_bar_mode in {1,2}). Without the DBN's downbeat model, the
downbeat track is unreliable on these, so the phase coordinate is well-defined at
the beat level but the *bar* wrap is not. This is not hidden: it is reported per
track via `beats_per_bar_mode` in the G0 record, and metrical `phase` is computed
against whatever bar length the clock reports.

Rationale for retaining dbn=False now: the reconstruction identity (G0 ii) and
grid->onset alignment (G0 i) both pass at full tolerance without the DBN, so the
tatum grid — the object the writer actually schedules on — is sound. The bar
circle is only needed where a term keys on bar-position; T2/T4 in F key on the
metrical-slot histogram, which we build at the resolution the clock supports.

Revisit condition: turn dbn=True if G4 (generation quality) shows the missing
bar circle causes phrase-scale incoherence. Deferred until there is evidence the
bar wrap matters for generation; adding it now would be tuning ahead of a gate.
