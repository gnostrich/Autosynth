"""Corpus-time training machinery (spec §6).

Build-order step d (training loop / F-weight NCE estimator) is NOT implemented
here — it depends on F (another builder's step c). This package currently holds
ONLY the internal SCRAMBLE COMPARISON CLASS (``scramble.py``), which is
independent of F: it constructs the negatives (disarrangements of real tracks'
own units) that the estimator will later score. See ``ets.training.scramble``.
"""
