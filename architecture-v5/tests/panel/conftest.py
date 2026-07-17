"""Panel tests run headless: force the offscreen Qt platform before any Qt
import so CI needs no display. Pure-logic tests (lanes/osc/midi/meters) import
no Qt at all; the one widget test uses this offscreen backend."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
