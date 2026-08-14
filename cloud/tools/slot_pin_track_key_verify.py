"""SLOT_PIN RE-KEYING — byte identity when slot_pin is ABSENT (PR-6-style).

The per-track-slot-pin amendment (2026-08-14) re-keys ``ClampTerms.slot_pin``
from ``{slot: (unit_ids,)}`` to ``{(track_id, slot): (unit_ids,)}``. This is a
re-keying of an EXISTING field's content, not a new field, so the same
neutral-law obligation the original slot_pin disclosure proved still applies:
a passage of fences that never supply ``slot_pin`` at all must hash
IDENTICALLY whether the (now per-track) clause is present-but-unused in
``realize.py``/``clamp.py`` or physically removed from them.

Reuses the EXACT tape construction the retroactive slot_pin disclosure used
(papers/PREREG-live-mode.md, "Byte-identity evidence"): 16 bars, 4 fence
configurations (unfenced, single-track, unit-pinned, two-track decaying),
none of them ever passing ``slot_pin=``, hashing emitted rows + settled
occupancy.

    [SPK-1] present-but-unused == the pre-amendment reference hash
            (22d27d511b433c86... -- the SAME hash the original slot_pin
            disclosure recorded, proving THIS re-keying changes nothing when
            the field is simply never supplied, exactly like the field's own
            first landing had to prove).

Physical removal is checked by a companion PROCEDURE (not automated here,
because "removed" means editing the source file and cannot be done inside a
running process without a subprocess round-trip): run this script, then
comment out the ``slot_pin`` clause in ``realize.py::_admits`` (or replace
its body with ``return True`` after the unit_pin check), re-run, and confirm
the SAME hash -- the transcript of this exact run is recorded in the
per-track-slot-pin PREREG amendment.
"""
from __future__ import annotations

import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "architecture-v6"))

REFERENCE_HASH = "22d27d511b433c8623fff75af8b52fc602ac7fcd29e1a723dd801fc1064ca64a"


def _tape() -> str:
    from ets.writer.clamp import clamp0
    from ets.writer.stream import StreamWriter
    from tests.harness.worldtools import build_synthetic_world

    w = build_synthetic_world()
    tid = int(w.tracks[0].track_id)
    sw = StreamWriter(w, seed=5)
    h = hashlib.sha256()
    pin = tuple(range(0, 40))
    o = 1.0
    for i in range(16):
        if i % 4 == 0:
            f = None
        elif i % 4 == 1:
            f = clamp0(track_mask={tid: 1.0}, openness=1.0)
        elif i % 4 == 2:
            f = clamp0(track_mask={tid: 1.0}, openness=1.0, unit_pin=(tid, pin))
        else:
            o = max(1e-6, o * 0.8)
            f = clamp0(track_mask={tid: o, (tid + 2) % len(w.tracks): o}, openness=o)
        r = sw.write_bar(fence=f)
        h.update(repr(r.rows).encode())
        h.update(r.O.tobytes())
    return h.hexdigest()


def run() -> int:
    got = _tape()
    ok = got == REFERENCE_HASH
    print("  [%s] SPK-1 slot_pin-absent neutral law  got=%s want=%s"
          % ("PASS" if ok else "FAIL", got[:16], REFERENCE_HASH[:16]), flush=True)
    print(("\nALL PASS  (1 check, 0 failed)" if ok else
           "\nFAILED: SPK-1  (1 check, 1 failed)"), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(run())
