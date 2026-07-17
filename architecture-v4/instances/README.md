# instances under architecture-v2

**v2 introduces NO new instance.** It is a display-layer relabel of the v1 machine;
it changes no audio, weight, world, or gate, so no trained model is created here.

## The default corpus vs swapped-in instances

- **psytech is the CANONICAL DEFAULT corpus** — the trained model that ships
  *initialized inside the machine* (its world `corpus.etsworld` + `LAMBDA` in
  `ets/functional/f.py` + `sigma_phi.json`). It is the "batteries-included" corpus,
  and the v2 machine inherits it via the machine copy. A user **swaps it out for
  their own corpus** by retraining/forking.
- **futuregarage is the worked example of such a swap** — a user corpus
  (deep/atmospheric halftime) run through the same machine, created under **v1**.
  It lives once, under v1 (`instantiations/futuregarage/`), and is not duplicated or
  re-pointed into later versions.

Only a genuinely NEW trained model produced *on the v2 machine* would land here as
`architecture-v2/instances/<corpus>/`.
