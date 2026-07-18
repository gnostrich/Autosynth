"""THE FIELD (ui-v6): one unified control/display surface — a field of squares
you push (bias) and zoom (drill). It REPLACES the pad grid, the XY/vector pad,
and the hierarchical drill-in. Native Qt only (I-13).

GOVERNING INVARIANT (FIELD-INV, auditor-enforced):

    You push -> the engine re-settles -> the display shows the ENGINE'S ANSWER.

A square's fill brightness IS its live settled weight, read from the engine's
read-only telemetry (/ets/roleactivity, /ets/nowplaying, /ets/unitpool,
/ets/profiles). No UI path sets brightness from cursor/scroll input:

  * every settled store in `FieldModel` is written ONLY through the
    capability-guarded `_ingest` (a `FieldTelemetryWriter` obtained once by the
    telemetry applier holds the token; any other caller RAISES) — the runtime
    tripwire;
  * no input handler in `FieldView` may name a settled-writing method — the
    static (AST) check in tests/field/test_field_inv.py, proven to bite on an
    echo fixture.

The ONE gesture is hover-scroll BIAS: it accumulates an operator INPUT value
per square (shown as a RING on the square's edge, distinct from the fill) and
the app routes the composite through the panel's EXISTING region-tilt lane
(`Panel.set_region_vector` -> clamp -> slew -> /ets/lanes). The machine
re-settles around the bias; it is never forced (FIELD-D: the field changes WHAT
IS BIASED, never how F scores or the writer settles). Down-bias saturates at
"strongly disfavored" (-1 x the safe envelope) and can never hard-mute: the
region lane is an exponential tilt, so settled weight stays > 0 (FIELD-B).
Membership (hard include/exclude) is the SEPARATE crate/library system.

Recursive drill by ZOOM (pinch / Ctrl+scroll), no levels, no submenus:
TRACK squares (out) -> the ROLES a track loads (mid) -> a role's UNIT pool
(in). DEPTH IS SELF-SIZING per square by the SAME noise-floor criterion that
set M: the participation-ratio effective mode count (Sum w)^2 / Sum w^2
(`ets/functional/anchors.py::effective_rank`; the FORMULA is restated here as
pure arithmetic on telemetry vectors — the instrument may not import
ets.functional, F3-B door). A square expands only while its sub-structure
clears the floor (round(PR) >= 2); ATOMIC squares render NO expansion
affordance. Depth honestly ends at units: the engine emits no sub-unit
telemetry, and faking finer slices would violate FIELD-E (every glowing square
is backed by a real track/role/unit with real settled weight — real or absent).

Disclosed wall (carried from ui-v5, unchanged): the engine emits no PER-UNIT
sounding signal, so a unit square's fill breathes with its SOURCE TRACK's
/ets/nowplaying activity — honest track-grain brightness at unit grain, not a
fabricated per-unit weight.

Composition law: this module imports numpy, Qt, the display palette, and the
panel's declared safe envelope. NOTHING from the trained object
(render/engine/writer/functional/geometry) — enforced by the door tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ets.instrument.model import track_palette
from ets.panel.envelope import SAFE_REGION_MAGNITUDE


# ---- the noise-floor criterion (FIELD-C) -----------------------------------
# The SAME participation-ratio formula that self-sized the anchor count M
# (anchors.effective_rank: (sum w)^2 / sum w^2 over a non-negative spectrum),
# restated on a square's sub-element weight vector. Pinned to the anchors.py
# implementation by value in tests/field/test_field_c_selfsizing.py.

def participation_ratio(w) -> float:
    """Effective number of distinct sub-modes in a non-negative weight vector:
    (sum w)^2 / sum w^2, with negatives clipped to 0 (a mass vector). 0 for an
    empty/zero vector."""
    v = np.maximum(np.asarray(w, dtype=np.float64).reshape(-1), 0.0)
    s1 = float(v.sum())
    s2 = float((v ** 2).sum())
    if s2 <= 0.0:
        return 0.0
    return (s1 * s1) / s2


def clears_noise_floor(w) -> bool:
    """A square may expand only while its sub-structure clears the floor: at
    least TWO effective sub-modes (round(PR) >= 2, the same rounding the anchor
    count uses). One dominant mode (or none) = ATOMIC — nothing distinct inside
    above the floor, so drilling would resolve into noise."""
    return int(round(participation_ratio(w))) >= 2


# ---- FIELD-INV capability guard --------------------------------------------
# Settled brightness enters the model ONLY through a FieldTelemetryWriter,
# which is constructed holding the private token. This is a runtime tripwire
# (paired with the static AST check in the harness): a gesture handler that
# tries to write brightness has no token and raises.
#
# DISCLOSED LIMIT (auditor note 1, 2026-07-17): Python offers no true
# capability sealing — code that imports this module can read
# `_TELEMETRY_TOKEN` and forge a write. The token is a TRIPWIRE against
# accidental misuse, not a sandbox; the load-bearing teeth are the harness's
# TRANSITIVE static check (tests/field/test_field_inv.py), the single-lane
# wire spy, and the byte-identical delete test (tests/field/test_field_d_*).

_TELEMETRY_TOKEN = object()


class FieldTelemetryWriter:
    """The ONE write capability for settled/telemetry state. Constructed only by
    `FieldModel.telemetry_writer()`; the live app hands it to the telemetry
    applier and to nothing else."""

    def __init__(self, model: "FieldModel", token) -> None:
        if token is not _TELEMETRY_TOKEN:
            raise PermissionError(
                "FIELD-INV: FieldTelemetryWriter may only be constructed by "
                "FieldModel.telemetry_writer()")
        self._model = model

    def apply_roleactivity(self, levels: List[float]) -> None:
        self._model._ingest("roleactivity", levels, token=_TELEMETRY_TOKEN)

    def apply_nowplaying(self, activity: Dict[int, float]) -> None:
        self._model._ingest("nowplaying", activity, token=_TELEMETRY_TOKEN)

    def apply_profiles(self, profiles: Dict[int, List[float]]) -> None:
        self._model._ingest("profiles", profiles, token=_TELEMETRY_TOKEN)

    def apply_unitpool(self, role: int, units: List[dict]) -> None:
        self._model._ingest("unitpool", (int(role), list(units)),
                            token=_TELEMETRY_TOKEN)


# ---- squares ----------------------------------------------------------------

@dataclass(frozen=True)
class Square:
    """One square of the field, as a display fact.

    `settled` is the ENGINE'S ANSWER (fill brightness, 0..1, from telemetry);
    `bias` is the OPERATOR'S INPUT (-1..+1, the edge ring) — kept as two fields
    on purpose so the gap between "how hard I pushed" and "how much it took"
    stays legible and the two can never be conflated into one channel."""
    kind: str                       # "track" | "role" | "unit"
    key: Tuple                      # ("track", t) | ("role", r) | ("unit", role, uid, tid)
    label: str
    track: Optional[int]            # colour source (None for role squares)
    settled: float                  # engine's settled weight (fill)
    bias: float                     # accumulated operator bias (ring)
    expandable: bool                # FIELD-C: sub-structure clears the floor
    n_children: int                 # effective children if expandable, else 0


class FieldModel:
    """Pure state of the field (no Qt): telemetry-fed settled weights, the
    operator's per-square bias ledger, and the square tree built ONLY from
    ingested telemetry (FIELD-E: a square exists iff the engine named its
    track/role/unit; empty telemetry = empty field, never placeholders)."""

    BIAS_LIMIT = 1.0                # soft-saturation stop (x safe envelope)

    def __init__(self) -> None:
        self._roleactivity: List[float] = []
        self._nowplaying: Dict[int, float] = {}
        self._profiles: Dict[int, List[float]] = {}
        self._unit_pools: Dict[int, List[dict]] = {}
        self._bias: Dict[Tuple, float] = {}

    # -- telemetry ingestion (capability-guarded; FIELD-INV) ------------------
    def telemetry_writer(self) -> FieldTelemetryWriter:
        return FieldTelemetryWriter(self, _TELEMETRY_TOKEN)

    def _ingest(self, kind: str, payload, *, token=None) -> None:
        if token is not _TELEMETRY_TOKEN:
            raise PermissionError(
                "FIELD-INV violation: settled brightness may only be written "
                "by the telemetry applier (obtain FieldModel.telemetry_writer())"
                " — never from an input/gesture path")
        if kind == "roleactivity":
            self._roleactivity = [float(min(1.0, max(0.0, v)))
                                  for v in payload]
        elif kind == "nowplaying":
            for t, v in dict(payload).items():
                self._nowplaying[int(t)] = float(min(1.0, max(0.0, v)))
        elif kind == "profiles":
            for t, p in dict(payload).items():
                self._profiles[int(t)] = [float(x) for x in p]
        elif kind == "unitpool":
            role, units = payload
            self._unit_pools[int(role)] = [dict(u) for u in units]
        else:
            raise ValueError(f"unknown telemetry kind {kind!r}")

    # -- the square tree (built only from ingested telemetry; FIELD-E) -------
    @property
    def n_roles(self) -> int:
        return len(self._roleactivity)

    def track_squares(self) -> List[Square]:
        """Zoomed OUT: one square per source track the engine has named (via
        /ets/profiles or /ets/nowplaying). Fill = that track's settled
        now-playing activity. Expandable iff its engine-emitted anchor profile
        has >= 2 effective roles above the floor."""
        out: List[Square] = []
        for t in sorted(set(self._profiles) | set(self._nowplaying)):
            p = self._profiles.get(t)
            expandable = clears_noise_floor(p) if p else False
            n_kids = int(round(participation_ratio(p))) if expandable else 0
            key = ("track", int(t))
            out.append(Square(
                kind="track", key=key, label=f"T{t}", track=int(t),
                settled=float(self._nowplaying.get(t, 0.0)),
                bias=self._bias.get(key, 0.0),
                expandable=expandable, n_children=n_kids))
        return out

    def role_square(self, r: int) -> Square:
        key = ("role", int(r))
        lvl = (self._roleactivity[r]
               if 0 <= r < len(self._roleactivity) else 0.0)
        pool = self._unit_pools.get(int(r), [])
        # sub-structure weights: how strongly each pool unit loads THIS role
        # (its engine-emitted profile value at r) — distinctness above the floor.
        w = [float(u.get("profile", [0.0] * (r + 1))[r])
             for u in pool
             if len(u.get("profile", [])) > r]
        expandable = clears_noise_floor(w)
        return Square(
            kind="role", key=key, label=f"R{r}", track=None,
            settled=float(lvl), bias=self._bias.get(key, 0.0),
            expandable=expandable,
            n_children=int(round(participation_ratio(w))) if expandable else 0)

    def role_squares_flat(self) -> List[Square]:
        """MID zoom: every role/anchor as a square (fill = settled per-role
        level from /ets/roleactivity)."""
        return [self.role_square(r) for r in range(len(self._roleactivity))]

    def roles_of_track(self, t: int) -> List[Square]:
        """A TRACK square's children: the roles its engine-emitted profile
        loads above the noise floor — the top round(PR) roles by profile mass
        (balanced-truncation reading: modes below the floor are truncated).
        Role squares are GLOBAL objects (same key however reached): a role
        loaded by two tracks appears under both — true by construction, all
        cross-track traffic factors through the anchors."""
        p = self._profiles.get(int(t))
        if not p or not clears_noise_floor(p):
            return []
        k_eff = min(len(p), int(round(participation_ratio(p))))
        order = np.argsort(np.asarray(p, dtype=np.float64))[::-1][:k_eff]
        return [self.role_square(int(r)) for r in sorted(order.tolist())]

    def unit_squares(self, role: int) -> List[Square]:
        """A ROLE square's children: its engine-emitted drill pool
        (/ets/unitpool), coloured by source track. Fill = the unit's source
        track's settled activity (disclosed track-grain wall). Units are
        ATOMIC: no sub-unit telemetry exists, so expandable is False and no
        affordance is rendered."""
        out: List[Square] = []
        for u in self._unit_pools.get(int(role), []):
            uid = int(u.get("unit_id", -1))
            tid = int(u.get("track_id", -1))
            key = ("unit", int(role), uid, tid)
            out.append(Square(
                kind="unit", key=key, label=f"u{uid}", track=tid,
                settled=float(self._nowplaying.get(tid, 0.0)),
                bias=self._bias.get(key, 0.0),
                expandable=False, n_children=0))
        return out

    def children(self, key: Tuple) -> List[Square]:
        if key[0] == "track":
            return self.roles_of_track(key[1])
        if key[0] == "role":
            return self.unit_squares(key[1])
        return []                                   # unit: atomic

    # -- operator bias (input state; ring display + region-lane routing) ------
    def add_bias(self, key: Tuple, delta: float) -> float:
        """Accumulate scroll bias on a square, SOFT-saturating at +-BIAS_LIMIT
        ("strongly favored/disfavored"). The stop is a saturation of the INPUT;
        because the region lane is an exponential tilt, even the full down-stop
        re-weights and never mutes (FIELD-B). Returns the new value."""
        b = self._bias.get(key, 0.0) + float(delta)
        b = float(min(self.BIAS_LIMIT, max(-self.BIAS_LIMIT, b)))
        if abs(b) < 1e-9:
            self._bias.pop(key, None)
        else:
            self._bias[key] = b
        return b

    def bias_of(self, key: Tuple) -> float:
        return self._bias.get(key, 0.0)

    def clear_bias(self) -> None:
        self._bias.clear()

    def _direction(self, key: Tuple, K: int) -> Optional[np.ndarray]:
        """The region-space direction a square's bias leans toward — each from
        ENGINE-EMITTED data (no fabricated join): a role is its own axis; a
        track leans along its /ets/profiles anchor-mass profile; a unit leans
        along its /ets/unitpool anchor profile (peak-normalized, the existing
        fine-steer semantics)."""
        if key[0] == "role":
            r = int(key[1])
            if not 0 <= r < K:
                return None
            d = np.zeros(K, dtype=np.float32)
            d[r] = 1.0
            return d
        if key[0] == "track":
            p = self._profiles.get(int(key[1]))
            if not p:
                return None
            v = np.asarray(p, dtype=np.float32).reshape(-1)
        else:                                       # unit
            _, role, uid, tid = key
            v = None
            for u in self._unit_pools.get(int(role), []):
                if (int(u.get("unit_id", -1)) == int(uid)
                        and int(u.get("track_id", -1)) == int(tid)):
                    v = np.asarray(u.get("profile", ()),
                                   dtype=np.float32).reshape(-1)
                    break
            if v is None:
                return None
        peak = float(np.max(np.abs(v))) if v.size else 0.0
        if peak <= 0.0:
            return None
        d = np.zeros(K, dtype=np.float32)
        n = min(K, v.shape[0])
        d[:n] = v[:n] / np.float32(peak)
        return d

    def region_vector(self, K: Optional[int] = None) -> np.ndarray:
        """The composite region LEAN all current square biases add up to,
        scaled to the panel's declared safe envelope. This is the ONLY thing
        the field hands toward the engine, and the app routes it through the
        panel's existing region path (set_region_vector -> clamp -> slew ->
        /ets/lanes): the sanctioned tilt lane, no new authority (FIELD-D)."""
        K = int(K) if K is not None else self.n_roles
        out = np.zeros(K, dtype=np.float32)
        for key, b in self._bias.items():
            d = self._direction(key, K)
            if d is not None:
                out += np.float32(b) * d
        return out * np.float32(SAFE_REGION_MAGNITUDE)


# ---- the widget -------------------------------------------------------------

class FieldView(QWidget):
    """Draws the field and turns gestures into MODEL INPUT only:

      * plain hover-scroll  -> bias the hovered square (model.add_bias) and
                               emit `bias_changed` (the app pushes the model's
                               composite through the panel region path);
      * Ctrl+scroll / pinch -> zoom: drill INTO the hovered square (only if it
                               is expandable — FIELD-C) or back out;
      * click on a unit     -> emit `unit_clicked` (CUE audition routing only).

    NO handler here writes brightness: fills come exclusively from the model's
    telemetry-fed settled state at paint time (FIELD-INV; AST-checked, and the
    model's settled stores are capability-locked besides). No mouse tracking,
    no hover-move handler: a passive hover is inert (carried B1 invariant)."""

    bias_changed = Signal()
    unit_clicked = Signal(tuple)                    # a unit square's key
    zoom_changed = Signal()

    BIAS_STEP = 0.125                               # per wheel notch

    def __init__(self, model: Optional[FieldModel] = None, parent=None) -> None:
        super().__init__(parent)
        self.model = model if model is not None else FieldModel()
        self._stack: List[Tuple] = []               # zoom path (square keys)
        self.setMinimumSize(320, 240)
        self.setToolTip(
            "THE FIELD — every square is real material (track / role / unit), "
            "glowing by its LIVE SETTLED WEIGHT (the engine's answer, never "
            "your input echoed back).\n"
            "hover + scroll = bias it up/down (soft; saturates, never mutes — "
            "use the crate for hard include/exclude)\n"
            "Ctrl+scroll (pinch) = zoom in/out; only squares with real "
            "sub-structure above the noise floor expand; unit fills breathe "
            "at track grain (no per-unit sounding telemetry — honest wall)\n\n"
            "internal: region-tilt lane only; brightness = settled telemetry")

    # -- zoom state -----------------------------------------------------------
    @property
    def zoom_path(self) -> List[Tuple]:
        return list(self._stack)

    def current_squares(self) -> List[Square]:
        if not self._stack:
            ts = self.model.track_squares()
            # before /ets/profiles arrives there may be roles but no tracks —
            # show the honest flat role field rather than an empty pane.
            return ts if ts else self.model.role_squares_flat()
        return self.model.children(self._stack[-1])

    def breadcrumb(self) -> str:
        if not self._stack:
            return ("TRACKS" if self.model.track_squares() else "ROLES")
        return " > ".join(
            ("TRACKS",) + tuple(
                (f"T{k[1]}" if k[0] == "track" else f"R{k[1]}")
                for k in self._stack))

    def zoom_into(self, key: Tuple) -> bool:
        """Drill into a square — REFUSED unless its sub-structure clears the
        noise floor (FIELD-C: no drill resolves into noise)."""
        for sq in self.current_squares():
            if sq.key == key:
                if not sq.expandable:
                    return False
                self._stack.append(key)
                self.zoom_changed.emit()
                self.update()
                return True
        return False

    def zoom_out(self) -> bool:
        if not self._stack:
            return False
        self._stack.pop()
        self.zoom_changed.emit()
        self.update()
        return True

    # -- geometry -------------------------------------------------------------
    _HEADER_PX = 22

    def _grid(self, n: int) -> Tuple[int, int]:
        cols = max(1, int(n ** 0.5 + 0.999))
        rows = max(1, (n + cols - 1) // cols)
        return rows, cols

    def square_at(self, x: float, y: float) -> Optional[Square]:
        sqs = self.current_squares()
        n = len(sqs)
        if n == 0 or y < self._HEADER_PX:
            return None
        rows, cols = self._grid(n)
        w = self.width() / cols
        h = (self.height() - self._HEADER_PX) / rows
        if w <= 0 or h <= 0:
            return None
        c = int(x / w)
        r = int((y - self._HEADER_PX) / h)
        if not (0 <= c < cols and 0 <= r < rows):
            return None
        k = r * cols + c
        return sqs[k] if 0 <= k < n else None

    # -- gestures (INPUT only; never brightness) ------------------------------
    def wheelEvent(self, ev) -> None:
        pos = ev.position()
        sq = self.square_at(pos.x(), pos.y())
        notches = ev.angleDelta().y() / 120.0
        if ev.modifiers() & Qt.ControlModifier:
            self._zoom_gesture(sq, notches)
        elif sq is not None and notches:
            self.model.add_bias(sq.key, notches * self.BIAS_STEP)
            self.bias_changed.emit()
            self.update()
        ev.accept()

    def event(self, ev) -> bool:                    # trackpad pinch = zoom
        if ev.type() == QEvent.NativeGesture and hasattr(ev, "value"):
            try:
                sq = self.square_at(ev.position().x(), ev.position().y())
            except Exception:
                sq = None
            self._zoom_gesture(sq, float(ev.value() or 0.0))
            return True
        return super().event(ev)

    def _zoom_gesture(self, sq: Optional[Square], amount: float) -> None:
        if amount > 0 and sq is not None:
            self.zoom_into(sq.key)                  # refused if atomic
        elif amount < 0:
            self.zoom_out()

    def mousePressEvent(self, ev) -> None:
        sq = self.square_at(ev.position().x(), ev.position().y())
        if sq is not None and sq.kind == "unit":
            self.unit_clicked.emit(sq.key)          # CUE audition routing only
        ev.accept()

    # -- paint (fills read ONLY the model's settled state) --------------------
    def paintEvent(self, _ev) -> None:
        qp = QPainter(self)
        qp.setPen(QPen(Qt.gray, 1))
        qp.drawText(6, 15, self.breadcrumb() +
                    ("   (Ctrl+scroll: back out)" if self._stack else ""))
        sqs = self.current_squares()
        n = len(sqs)
        if n == 0:
            qp.drawText(6, self._HEADER_PX + 16, "no material yet")
            qp.end()
            return
        rows, cols = self._grid(n)
        w = self.width() / cols
        h = (self.height() - self._HEADER_PX) / rows
        for k, sq in enumerate(sqs):
            r, c = divmod(k, cols)
            x, y = c * w, self._HEADER_PX + r * h
            if sq.track is not None:
                cr, cg, cb = track_palette(sq.track)
                col = QColor(cr, cg, cb)
            else:
                col = QColor(60, 90, 200)           # role family colour
            # FILL = the engine's settled answer, nothing else.
            col.setAlphaF(0.15 + 0.85 * max(0.0, min(1.0, sq.settled)))
            qp.fillRect(int(x) + 3, int(y) + 3, int(w) - 6, int(h) - 6, col)
            qp.setPen(QPen(Qt.black, 1))
            qp.drawRect(int(x) + 3, int(y) + 3, int(w) - 6, int(h) - 6)
            qp.drawText(int(x) + 7, int(y) + 17, sq.label)
            # RING = the operator's bias input (distinct channel from the fill).
            if abs(sq.bias) > 1e-9:
                ring = (QColor(255, 200, 40) if sq.bias > 0
                        else QColor(80, 200, 255))
                qp.setPen(QPen(ring, 1 + round(3 * abs(sq.bias))))
                qp.drawRect(int(x) + 5, int(y) + 5, int(w) - 10, int(h) - 10)
            # expansion affordance ONLY where real sub-structure clears the
            # floor (FIELD-C affordance honesty): atomic squares get nothing.
            if sq.expandable:
                qp.setPen(QPen(Qt.gray, 1))
                qp.drawText(int(x) + 7, int(y + h) - 8,
                            f"▸{sq.n_children}")
        qp.end()
