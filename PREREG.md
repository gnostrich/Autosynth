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

(no gates registered yet — build order is at 5a: skeleton + harness)
