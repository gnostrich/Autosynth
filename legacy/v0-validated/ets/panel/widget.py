"""Native PySide6 panel widget (spec §8, §12) — the six lanes, meter jacks,
MIDI CC learn. Headless-testable under QT_QPA_PLATFORM=offscreen.

Native Qt only. No web/browser tech (I-13). The widget renders exactly the six
lanes from `ets.panel.lanes.LANES` (its construction asserts exhaustiveness),
routes every lane change to the OSC emitter (the one outbound boundary-measure
channel), and paints the inbound meter jacks read-only. Meters never feed a
lane: the meter widgets only read a `MeterState`; there is no signal from a jack
to the lane vector.
"""
from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget,
)

from ets.panel.lanes import (
    LANES, LaneKind, LaneVector, assert_lanes_exhaustive, default_lane_vector,
    spec,
)
from ets.panel.meters import MeterState
from ets.panel.midi import CCMap, LaneTarget
from ets.panel import osc_schema as S

_SLIDER_STEPS = 1000


def _to_slider(lane_id: str, value: float) -> int:
    s = spec(lane_id)
    frac = (value - s.lo) / (s.hi - s.lo) if s.hi > s.lo else 0.0
    return int(round(max(0.0, min(1.0, frac)) * _SLIDER_STEPS))


def _from_slider(lane_id: str, pos: int) -> float:
    s = spec(lane_id)
    return float(s.lo + (pos / _SLIDER_STEPS) * (s.hi - s.lo))


class _LaneStrip(QWidget):
    """A single scalar-lane channel strip (label + vertical slider)."""

    changed = Signal(str, float)   # (lane_id, value)

    def __init__(self, lane_id: str, parent=None) -> None:
        super().__init__(parent)
        self.lane_id = lane_id
        s = spec(lane_id)
        lay = QVBoxLayout(self)
        self._slider = QSlider(Qt.Vertical, self)
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
        self._strips: list[QSlider] = []

    def set_anchor_count(self, K: int) -> None:
        K = int(K)
        while len(self._strips) < K:
            i = len(self._strips)
            sl = QSlider(Qt.Vertical, self)
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
    """The panel. Exactly six lanes; meter jacks; MIDI CC learn; OSC out."""

    lanes_changed = Signal()

    def __init__(self, emitter=None, n_anchors: int = 0, parent=None) -> None:
        super().__init__(parent)
        self.emitter = emitter
        self.u = default_lane_vector(n_anchors)
        self.meter_state = MeterState()
        self.cc_map = CCMap()

        self._strips: Dict[str, _LaneStrip] = {}
        root = QVBoxLayout(self)
        lane_row = QHBoxLayout()

        # REGION (vector lane) — growable strips over anchors.
        self._region = _RegionStrips(self)
        self._region.set_anchor_count(n_anchors)
        self._region.changed.connect(self._on_region)
        lane_row.addWidget(self._region)

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

        # Meter jacks (read-only).
        meters_box = QGroupBox("METER JACKS (read-only)", self)
        mlay = QVBoxLayout(meters_box)
        self._jacks = {
            "drift_key": _MeterJack("DRIFT key", self),
            "drift_phase_feel": _MeterJack("DRIFT phase/feel", self),
            "drift_timbre": _MeterJack("DRIFT timbre", self),
            "eoc": _MeterJack("PHRASE EOC gate", self),
            "novelty_sat": _MeterJack("NOVELTY saturation", self),
        }
        for j in self._jacks.values():
            mlay.addWidget(j)
        root.addWidget(meters_box)
        self.refresh_meters()

    # --- the exhaustive control set (for the §8 test) -------------------------
    @property
    def lane_control_ids(self) -> tuple:
        return self._built_lane_ids

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

    def _push(self) -> None:
        if self.emitter is not None:
            self.emitter.emit(self.u)
        self.lanes_changed.emit()

    def set_anchor_count(self, K: int) -> None:
        self.u.resize_region(K)
        self._region.set_anchor_count(K)

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
        one-way read; it writes NOTHING into the lane vector or the emitter."""
        d = self.meter_state.drift
        self._jacks["drift_key"].refresh(f"{d['key']:+.3f}")
        self._jacks["drift_phase_feel"].refresh(f"{d['phase_feel']:+.3f}")
        self._jacks["drift_timbre"].refresh(f"{d['timbre']:+.3f}")
        self._jacks["eoc"].refresh("ON" if self.meter_state.eoc_gate else "off")
        self._jacks["novelty_sat"].refresh(f"{self.meter_state.novelty_saturation:.3f}")
