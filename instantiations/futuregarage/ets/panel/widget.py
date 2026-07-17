"""Native PySide6 panel widget (spec §8, §12) — the six lanes (strips + XY
vector pad for REGION), the two declared tolerance knobs (LEASH/COMMA), meter
jacks (the slide/loop pairs; the prior conflated drift jack was DELETED
outright in directive-v1 Feature 2 Stage 1), clock display, MIDI CC learn.
Headless-testable under QT_QPA_PLATFORM=offscreen.

Native Qt only. No web/browser tech (I-13). The widget renders exactly the six
lanes from `ets.panel.lanes.LANES` (its construction asserts exhaustiveness)
plus exactly the two tolerances from `ets.panel.tolerances.TOLERANCES` (also
asserted), routes every lane change to the OSC emitter (the one outbound
boundary-measure channel) and every tolerance change to /ets/tolerances, and
paints the inbound meter jacks read-only. Meters never feed a lane or a knob:
the meter widgets only read a `MeterState`; there is no signal from a jack to
the lane vector or the tolerances.
"""
from __future__ import annotations

import math
from typing import Dict, Optional

import numpy as np

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QGroupBox, QGridLayout, QHBoxLayout, QLabel,
    QSlider, QVBoxLayout, QWidget,
)

from ets.panel.lanes import (
    LANES, LaneKind, LaneVector, assert_lanes_exhaustive, default_lane_vector,
    spec,
)
from ets.panel.meters import MeterState, fmt_reading
from ets.panel.midi import CCMap, LaneTarget
from ets.panel.tolerances import (
    TOLERANCES, Tolerances, assert_tolerances_exhaustive, display as tol_display,
)
from ets.panel import osc_schema as S

_SLIDER_STEPS = 1000


def _to_slider(lane_id: str, value: float) -> int:
    s = spec(lane_id)
    frac = (value - s.lo) / (s.hi - s.lo) if s.hi > s.lo else 0.0
    return int(round(max(0.0, min(1.0, frac)) * _SLIDER_STEPS))


def _from_slider(lane_id: str, pos: int) -> float:
    s = spec(lane_id)
    return float(s.lo + (pos / _SLIDER_STEPS) * (s.hi - s.lo))


class _ScrollSlider(QSlider):
    """A vertical slider driven by HOVER + SCROLL, not click-drag (macOS
    trackpad idiom, operator request). Contract:

    * WHEEL over the widget (two-finger trackpad scroll or mouse wheel) nudges
      the value RELATIVELY — no need to click first; hovering is enough.
    * click / drag do NOT move the value (no accidental fling, no click-to-jump).
    * hovering alone does NOT move the value (no absolute "value follows the
      cursor" — the position only changes on an explicit scroll gesture).

    Everything else (range, setValue/value, valueChanged, blockSignals) is the
    stock QSlider API, so the surrounding panel code is unchanged."""

    # scroll sensitivity: a standard wheel notch is 120 units in angleDelta;
    # one notch moves ~2% of the range. Trackpad pixelDelta is finer-grained and
    # scaled to match. Derived from _SLIDER_STEPS, not hand-tuned per feel.
    _STEP_PER_NOTCH = max(1, _SLIDER_STEPS // 50)

    def __init__(self, *a, **k) -> None:
        super().__init__(*a, **k)
        self.setFocusPolicy(Qt.WheelFocus)   # wheel works on hover, no click needed
        self._accum = 0.0

    def wheelEvent(self, ev) -> None:
        # prefer high-resolution trackpad pixelDelta; fall back to angleDelta.
        pd = ev.pixelDelta().y()
        if pd != 0:
            step = pd / 8.0 * (self._STEP_PER_NOTCH / 15.0)
        else:
            step = (ev.angleDelta().y() / 120.0) * self._STEP_PER_NOTCH
        self._accum += step
        whole = int(self._accum)
        if whole:
            self._accum -= whole
            self.setValue(int(min(self.maximum(),
                                  max(self.minimum(), self.value() + whole))))
        ev.accept()

    # click / drag are inert: value changes only via wheel.
    def mousePressEvent(self, ev) -> None:
        ev.ignore()

    def mouseMoveEvent(self, ev) -> None:
        ev.ignore()

    def mouseReleaseEvent(self, ev) -> None:
        ev.ignore()


class _LaneStrip(QWidget):
    """A single scalar-lane channel strip (label + hover-scroll slider)."""

    changed = Signal(str, float)   # (lane_id, value)

    def __init__(self, lane_id: str, parent=None) -> None:
        super().__init__(parent)
        self.lane_id = lane_id
        s = spec(lane_id)
        lay = QVBoxLayout(self)
        self._slider = _ScrollSlider(Qt.Vertical, self)
        self._slider.setRange(0, _SLIDER_STEPS)
        self._slider.setValue(_to_slider(lane_id, s.default))
        self._slider.valueChanged.connect(self._on_move)
        lay.addWidget(QLabel(s.title, self))
        lay.addWidget(self._slider)

    def _on_move(self, pos: int) -> None:
        self.changed.emit(self.lane_id, _from_slider(self.lane_id, pos))

    def set_value(self, value: float) -> None:
        self._slider.blockSignals(True)
        self._slider.setValue(_to_slider(self.lane_id, value))
        self._slider.blockSignals(False)

    def value(self) -> float:
        return _from_slider(self.lane_id, self._slider.value())


class _RegionStrips(QGroupBox):
    """REGION TILT — growable channel strips / XY vector pad over discovered
    anchors. One vertical slider per anchor; `set_anchor_count` grows/shrinks."""

    changed = Signal(int, float)   # (anchor_index, value)

    def __init__(self, parent=None) -> None:
        super().__init__(spec("region").title, parent)
        self._row = QHBoxLayout(self)
        self._strips: list[_ScrollSlider] = []

    def set_anchor_count(self, K: int) -> None:
        K = int(K)
        while len(self._strips) < K:
            i = len(self._strips)
            sl = _ScrollSlider(Qt.Vertical, self)
            sl.setRange(0, _SLIDER_STEPS)
            sl.setValue(_to_slider("region", 0.0))
            sl.valueChanged.connect(lambda pos, idx=i:
                                    self.changed.emit(idx, _from_slider("region", pos)))
            self._strips.append(sl)
            self._row.addWidget(sl)
        while len(self._strips) > K:
            sl = self._strips.pop()
            self._row.removeWidget(sl)
            sl.deleteLater()

    @property
    def anchor_count(self) -> int:
        return len(self._strips)

    def set_anchor(self, i: int, value: float) -> None:
        sl = self._strips[i]
        sl.blockSignals(True)
        sl.setValue(_to_slider("region", value))
        sl.blockSignals(False)


class _RegionXYPad(QWidget):
    """The XY VECTOR PAD view of the REGION lane (spec §8 lane 1: "growable
    channel strips / XY vector pad"). A UI affordance over the SAME u_region
    vector — it introduces no lane. Interaction (macOS trackpad idiom): HOVER
    over the pad to aim toward the nearby anchors (which sit on a circle), then
    SCROLL to push the lean magnitude that way. Hovering alone changes nothing;
    click/drag are inert. Emitted through the one region path.
    """

    changed = Signal(object)   # full (K,) region lean vector

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._K = 0
        self._pos: Optional[QPointF] = None   # hover AIM (direction), not a value
        self._throw = 0.0                     # lean magnitude [0,1], scroll-driven
        self._accum = 0.0
        self.setMinimumSize(140, 140)
        self.setMouseTracking(True)           # hover reported without a click
        self.setFocusPolicy(Qt.WheelFocus)

    def set_anchor_count(self, K: int) -> None:
        self._K = int(K)
        self.update()

    def _anchor_xy(self, i: int):
        r = 0.42 * min(self.width(), self.height())
        cx, cy = self.width() / 2.0, self.height() / 2.0
        ang = 2.0 * math.pi * i / max(1, self._K)
        return cx + r * math.cos(ang), cy + r * math.sin(ang)

    def _vector(self) -> np.ndarray:
        """Region lean vector from the current AIM (hover direction) and THROW
        (scroll magnitude): anchors weighted by inverse distance to the aim
        point (vector-mixer crossfade, Doepfer A-144 idiom), magnitude = lane
        max * throw. Aim absent -> center -> even lean."""
        s = spec("region")
        K = self._K
        u = np.zeros(K, dtype=np.float32)
        if K == 0:
            return u
        if self._pos is None:
            x, y = self.width() / 2.0, self.height() / 2.0
        else:
            x, y = self._pos.x(), self._pos.y()
        w = np.zeros(K)
        for i in range(K):
            ax, ay = self._anchor_xy(i)
            w[i] = 1.0 / (math.hypot(x - ax, y - ay) + 1e-6)
        w = w / w.sum()
        u[:] = (s.hi * self._throw) * w
        return u

    # HOVER = aim only (which anchors to lean toward). It does NOT change the
    # value — no absolute "value follows the cursor".
    def mouseMoveEvent(self, ev) -> None:
        self._pos = ev.position()
        self.update()

    # click/drag inert (parity with the sliders — no accidental fling).
    def mousePressEvent(self, ev) -> None:
        ev.ignore()

    # SCROLL sets the lean magnitude toward the current aim, and emits.
    def wheelEvent(self, ev) -> None:
        pd = ev.pixelDelta().y()
        step = (pd / 400.0) if pd != 0 else (ev.angleDelta().y() / 120.0) * 0.04
        self._throw = float(min(1.0, max(0.0, self._throw + step)))
        self.changed.emit(self._vector())
        self.update()
        ev.accept()

    def paintEvent(self, _ev) -> None:
        qp = QPainter(self)
        qp.setPen(QPen(Qt.gray, 1))
        qp.drawRect(0, 0, self.width() - 1, self.height() - 1)
        for i in range(self._K):
            ax, ay = self._anchor_xy(i)
            qp.drawEllipse(QPointF(ax, ay), 3, 3)
            qp.drawText(int(ax) + 5, int(ay), str(i))
        # aim (hover) marker + throw magnitude ring from centre.
        cx, cy = self.width() / 2.0, self.height() / 2.0
        if self._throw > 0:
            rmax = 0.42 * min(self.width(), self.height())
            qp.setPen(QPen(Qt.blue, 1))
            qp.drawEllipse(QPointF(cx, cy), rmax * self._throw, rmax * self._throw)
        if self._pos is not None:
            qp.setPen(QPen(Qt.black, 2))
            qp.drawEllipse(self._pos, 5, 5)
            qp.drawText(6, self.height() - 6, f"throw {self._throw:.2f} (scroll)")
        qp.end()


class _ToleranceKnob(QWidget):
    """One declared tolerance knob (LEASH / COMMA). Displays 'inf' while the
    infinity latch is on (the shipped default — unconstraining); unlatching
    exposes a finite spin value. Emits (id, value)."""

    changed = Signal(str, float)

    def __init__(self, spec_, parent=None) -> None:
        super().__init__(parent)
        self.tol_id = spec_.id
        lay = QHBoxLayout(self)
        lay.addWidget(QLabel(f"{spec_.title} ({spec_.meaning})", self))
        self._inf = QCheckBox("inf", self)
        self._inf.setChecked(math.isinf(spec_.default))
        self._spin = QDoubleSpinBox(self)
        self._spin.setRange(spec_.lo, 1e9)
        self._spin.setDecimals(3)
        self._spin.setValue(1.0)
        self._spin.setEnabled(not self._inf.isChecked())
        self._value_label = QLabel(tol_display(spec_.default), self)
        self._inf.toggled.connect(self._on_change)
        self._spin.valueChanged.connect(self._on_change)
        lay.addWidget(self._inf)
        lay.addWidget(self._spin)
        lay.addWidget(self._value_label)

    def value(self) -> float:
        return math.inf if self._inf.isChecked() else float(self._spin.value())

    def _on_change(self, *_a) -> None:
        self._spin.setEnabled(not self._inf.isChecked())
        v = self.value()
        self._value_label.setText(tol_display(v))
        self.changed.emit(self.tol_id, v)


class _MeterJack(QWidget):
    """A read-only meter indicator (LED/jack metaphor). Reads a value on
    `refresh`; has NO path back into any lane."""

    def __init__(self, label: str, parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        self._label = QLabel(label, self)
        self._value = QLabel("--", self)
        lay.addWidget(self._label)
        lay.addWidget(self._value)

    def refresh(self, text: str) -> None:
        self._value.setText(text)


class Panel(QWidget):
    """The panel. Exactly six lanes (+ the two declared tolerance knobs);
    meter jacks incl. the slide/loop pairs; clock; MIDI CC learn; OSC out."""

    lanes_changed = Signal()
    tolerances_changed = Signal()

    def __init__(self, emitter=None, n_anchors: int = 0, parent=None) -> None:
        super().__init__(parent)
        self.emitter = emitter
        self.u = default_lane_vector(n_anchors)
        self.tolerances = Tolerances()          # leash=inf, comma=inf (shipped)
        self.meter_state = MeterState()
        self.cc_map = CCMap()

        self._strips: Dict[str, _LaneStrip] = {}
        root = QVBoxLayout(self)
        lane_row = QHBoxLayout()

        # REGION (vector lane) — growable channel strips + XY vector pad, two
        # views over the SAME u_region (spec §8 lane 1); no lane is added.
        self._region = _RegionStrips(self)
        self._region.set_anchor_count(n_anchors)
        self._region.changed.connect(self._on_region)
        self._xy = _RegionXYPad(self)
        self._xy.set_anchor_count(n_anchors)
        self._xy.changed.connect(self._on_region_vector)
        region_col = QVBoxLayout()
        region_col.addWidget(self._region)
        region_col.addWidget(self._xy)
        lane_row.addLayout(region_col)

        # The four scalar direction lanes + the sharpness lane.
        built_ids = ["region"]
        for lane in LANES:
            if lane.is_vector:
                continue
            strip = _LaneStrip(lane.id, self)
            strip.changed.connect(self._on_scalar)
            self._strips[lane.id] = strip
            lane_row.addWidget(strip)
            built_ids.append(lane.id)

        # §8 EXHAUSTIVENESS LAW, enforced at construction: exactly the six.
        assert_lanes_exhaustive(built_ids)
        self._built_lane_ids = tuple(built_ids)

        root.addLayout(lane_row)

        # The two declared TOLERANCE knobs — NOT lanes (ets.panel.tolerances):
        # they transmit on /ets/tolerances and nothing consumes them (Stage-1).
        tol_box = QGroupBox(
            "TOLERANCES (declared; no consumer until Stage-1)", self)
        tlay = QVBoxLayout(tol_box)
        self._tol_knobs: Dict[str, _ToleranceKnob] = {}
        for tspec in TOLERANCES:
            knob = _ToleranceKnob(tspec, self)
            knob.changed.connect(self._on_tolerance)
            self._tol_knobs[tspec.id] = knob
            tlay.addWidget(knob)
        assert_tolerances_exhaustive(self._tol_knobs.keys())
        root.addWidget(tol_box)

        # Clock display (master clock, /ets/clock) + engine link status
        # (handshake reply /ets/welcome — includes the declared latency L).
        clock_row = QHBoxLayout()
        self._clock = QLabel("CLOCK —", self)
        self._link = QLabel("engine: not connected", self)
        clock_row.addWidget(self._clock)
        clock_row.addWidget(self._link)
        root.addLayout(clock_row)

        # Meter jacks (read-only). The slide/loop pairs show '—' until the
        # Stage-0 shadow feed arrives. (The prior conflated DRIFT jack was
        # DELETED outright in directive-v1 Feature 2 Stage 1 — code, panel
        # element, OSC address — per merged evidence it carried zero bits the
        # slide/loop pair does not already carry; REGISTRY
        # conflation-regression-stage1-2026-07-15.)
        meters_box = QGroupBox("METER JACKS (read-only)", self)
        mlay = QGridLayout(meters_box)
        self._jacks = {
            "slide_key": _MeterJack("SLIDE key", self),
            "slide_phase_feel": _MeterJack("SLIDE phase/feel", self),
            "slide_timbre": _MeterJack("SLIDE timbre", self),
            "loop_key": _MeterJack("LOOP key", self),
            "loop_phase_feel": _MeterJack("LOOP phase/feel", self),
            "loop_timbre": _MeterJack("LOOP timbre", self),
            "eoc": _MeterJack("PHRASE EOC gate", self),
            "novelty_sat": _MeterJack("NOVELTY saturation", self),
        }
        for i, j in enumerate(self._jacks.values()):
            mlay.addWidget(j, i % 6, i // 6)
        root.addWidget(meters_box)
        self.refresh_meters()

    # --- the exhaustive control set (for the §8 / H-6 tests) ------------------
    @property
    def lane_control_ids(self) -> tuple:
        return self._built_lane_ids

    @property
    def tolerance_control_ids(self) -> tuple:
        return tuple(self._tol_knobs.keys())

    # --- lane edits → emit ----------------------------------------------------
    def _on_scalar(self, lane_id: str, value: float) -> None:
        if lane_id == "density":
            self.u.u_density = value
        elif lane_id == "continuity":
            self.u.u_continuity = value
        elif lane_id == "gauge":
            self.u.u_gauge = value
        elif lane_id == "novelty":
            self.u.u_novelty = value
        elif lane_id == "temperature":
            self.u.T_s = value
        else:
            raise AssertionError(f"unexpected scalar lane {lane_id!r}")
        self._push()

    def _on_region(self, anchor: int, value: float) -> None:
        if 0 <= anchor < self.u.n_anchors:
            self.u.u_region[anchor] = value
        self._push()

    def _on_region_vector(self, vec) -> None:
        """The XY pad view sets the whole region lean at once (same lane)."""
        vec = np.asarray(vec, dtype=np.float32).reshape(-1)
        n = min(self.u.n_anchors, vec.shape[0])
        self.u.u_region[:n] = vec[:n]
        for i in range(min(self._region.anchor_count, n)):
            self._region.set_anchor(i, float(vec[i]))
        self._push()

    def _push(self) -> None:
        if self.emitter is not None:
            self.emitter.emit(self.u)
        self.lanes_changed.emit()

    # --- tolerance knobs → /ets/tolerances (declared; consumed by nothing) ----
    def _on_tolerance(self, tol_id: str, value: float) -> None:
        if tol_id == "leash":
            self.tolerances = Tolerances(leash=value, comma=self.tolerances.comma)
        elif tol_id == "comma":
            self.tolerances = Tolerances(leash=self.tolerances.leash, comma=value)
        else:
            raise AssertionError(f"unexpected tolerance knob {tol_id!r}")
        if self.emitter is not None:
            self.emitter.emit_tolerances(self.tolerances)
        self.tolerances_changed.emit()

    def set_anchor_count(self, K: int) -> None:
        self.u.resize_region(K)
        self._region.set_anchor_count(K)
        self._xy.set_anchor_count(K)

    # --- MIDI CC learn --------------------------------------------------------
    def arm_cc_learn(self, target: LaneTarget) -> None:
        self.cc_map.arm(target)

    def handle_cc(self, channel: int, cc: int, value7: int) -> bool:
        """Route a live CC. During learn (armed) it binds; otherwise it drives
        the mapped lane and emits. Returns True if it hit a binding."""
        if self.cc_map.armed is not None:
            self.cc_map.observe(channel, cc)
            return True
        hit = self.cc_map.apply(channel, cc, value7, self.u)
        if hit:
            self._sync_controls_from_u()
            self._push()
        return hit

    def _sync_controls_from_u(self) -> None:
        self._strips["density"].set_value(self.u.u_density)
        self._strips["continuity"].set_value(self.u.u_continuity)
        self._strips["gauge"].set_value(self.u.u_gauge)
        self._strips["novelty"].set_value(self.u.u_novelty)
        self._strips["temperature"].set_value(self.u.T_s)
        for i in range(min(self._region.anchor_count, self.u.n_anchors)):
            self._region.set_anchor(i, float(self.u.u_region[i]))

    # --- meters (display only) ------------------------------------------------
    def refresh_meters(self) -> None:
        """Pull the latest MeterState into the read-only jack widgets. This is a
        one-way read; it writes NOTHING into the lane vector, the tolerances, or
        the emitter. (The welcome-driven anchor-count resize below sizes the
        region lane's SUPPORT — world structure — never a lean value.)"""
        ms = self.meter_state
        for prefix, comp in (("slide", ms.slide), ("loop", ms.loop)):
            self._jacks[f"{prefix}_key"].refresh(fmt_reading(comp["key"]))
            self._jacks[f"{prefix}_phase_feel"].refresh(
                fmt_reading(comp["phase_feel"]))
            self._jacks[f"{prefix}_timbre"].refresh(fmt_reading(comp["timbre"]))
        self._jacks["eoc"].refresh("ON" if ms.eoc_gate else "off")
        self._jacks["novelty_sat"].refresh(f"{ms.novelty_saturation:.3f}")
        if ms.clock_bar >= 0:
            self._clock.setText(f"CLOCK bar {ms.clock_bar}  "
                                f"({ms.clock_seconds:.1f}s)")
        if ms.engine_K is not None:
            dis = (f"  DISARMED: {ms.engine_disarmed} (uncalibrated scale — "
                   "u transmits, no tilt)" if ms.engine_disarmed else "")
            self._link.setText(
                f"engine: connected  K={ms.engine_K}  L={ms.engine_L} bars  "
                f"world {ms.engine_world_hash[:8]}{dis}")
            if ms.engine_K != self.u.n_anchors:
                self.set_anchor_count(ms.engine_K)
