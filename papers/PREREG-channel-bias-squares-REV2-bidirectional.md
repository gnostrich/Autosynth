# PREREG revision R2 — channel-bias squares: BIDIRECTIONAL (amplify AND damp)

**Status:** operator-directed 2026-07-19. Extends `PREREG-channel-bias-squares-REV1-soft.md`
(**RATIFIED**); the REV1 record is left intact. This is a **RANGE EXTENSION of an
already-ratified control**, not a new mechanism: the soft `channel_logbias` addend
at `fiber_choice_logits` already handles a negative addend mathematically. Awaiting
ets-auditor PASS on the diff.

## Why this is not a new mechanism (the physics premise, honored)
The fiber choice is a **softmax** over the pooled-channel candidate units at each
beat. Adding a **constant** to every channel's log-weight leaves the draw unchanged
— only the **RELATIVE β** between channels matters (**gauge invariance**). So:

> amplifying one channel ≡ damping all the rest.

REV1 shipped only the positive half (`amplify ∈ [0, 1]`, `β_T = LAMBDA['T1p']·amplify`,
emitted only for `amplify > 0`). REV2 widens the SAME addend to `amplify ∈ [-1, 1]`:
a **negative** β is a soft **down-weight** (damp) in the SAME `fiber_choice_logits`
softmax. Bidirectional simply exposes both handles explicitly, so a single gesture
can **lift one channel AND cut another** in one relative move. No second decision
channel, no clamp, no new lane — the same one `TiltTerms.channel_logbias` the writer
already consumes (I-1).

## Model
    log w(c) = −E_F(c)/T_s + λ_cont·1[cont](c) + λ_novelty·reuse(c) + β_T(c)
    β_T = LAMBDA['T1p'] · amplify,   amplify ∈ [-1, 1]   (sign carries direction)

- `amplify > 0` → positive addend → up-weight channel T's candidates (amplify).
- `amplify < 0` → negative addend → down-weight channel T's candidates (soft damp).
- `amplify = 0` / empty → **no addend** → **byte-identical** fiber draw (hard invariant).

## Hypothesis
**H1(damp):** damping a channel T monotonically **LOWERS** its provenance fraction
**below its neutral (amplify=0) baseline** as the damp deepens, on MOST channels
(same majority rule + per-channel disarm allowance as the amplify gate),
byte-identical at zero, **generative** — the down-weight is soft (it does not hard-
mute; a channel's provenance approaches, but the mechanism itself never pins it to,
zero). The amplify half (REV1 H1) is unchanged and re-measured for regression.

**Null (H0):** damping does not move provenance below baseline, or moves it non-
monotonically, or the all-zero vector is no longer byte-identical.

**Kill condition:** any all-zero (any sign) input that is not byte-identical is a
kill (invariant breach). If damp fails to lower provenance on a majority of channels
the damp handle disarms HONESTLY (as REV1 disarms a mushy channel) — it is never
patched with a hard mute.

## Gate result (H1 damp) — RESULT: DAMP HOLDS (and amplify H1 still HOLDS)
World: `demo.etsworld` (4 real committed channels, M=2), 48 bars/condition
(`cloud/tools/channel_bias_pull_verify.py`; both curves in
`papers/channel_bias_pull_results.json`). Per-channel track-T output-unit fraction:

| channel | −1.0 | −0.6 | −0.3 | **0.0** | 0.3 | 0.6 | 1.0 |
|---|---|---|---|---|---|---|---|
| track 0 | 0.028 | 0.028 | 0.049 | **0.293** | 0.721 | 0.921 | 0.944 |
| track 1 | 0.009 | 0.023 | 0.083 | **0.238** | 0.728 | 0.901 | 0.953 |
| track 2 | 0.032 | 0.044 | 0.082 | **0.273** | 0.798 | 0.949 | 0.968 |
| track 3 | 0.000 | 0.000 | 0.029 | **0.196** | 0.680 | 0.884 | 0.912 |

Damp: monotone-down 4/4, material drop 4/4 (`damp_gain ≤ −0.05`). Amplify: monotone
4/4, material 4/4, confusion diagonal-dominant. Byte-identical at zero (rows + settled
O bit-identical). The curve is the honest **mirror** of the amplify pull.

## Walls (disclosed, honest)
- **Byte-identity at all-zero** (any sign) is the hard invariant — held (measured
  True; `set_channel_bias` and `channel_logbias` both key off `!= 0.0`, so an all-
  zero vector still maps to `None` ⇒ no addend).
- **Damp is soft, not a mute.** The MECHANISM never pins provenance to zero. But on
  a small world the OUTCOME can reach ~0 (track 3 → 0.000 at damp ≤ −0.6): when a
  channel's candidates are down-weighted enough, F + the other channels' candidates
  naturally win every softmax draw. This is the object excluding the channel, not a
  hard clamp — disclosed so no one reads "reaches 0" as a pinning move.
- **No settlement/F/render/root-ets edit.** The addend is sign-agnostic already
  (`architecture-v6/ets/writer/tilt.py` + `realize.py` add `β_T` into the fiber
  softmax with no sign assumption); REV2 only widens the range in the cloud layer
  (`channel_bias.py`, `engine_bridge.py`, FE, verifier, tests). Root `ets/`
  untouched. Only the range of the already-ratified control was widened.

## Success / stop (mirrors REV1)
SUCCESS: damp lowers provenance below baseline, monotone, material, on a majority of
channels, byte-identical at zero (met above). STOP/DISARM: if damp is mushy on a
majority, the damp handle disarms honestly — no hard mute is ever substituted.
