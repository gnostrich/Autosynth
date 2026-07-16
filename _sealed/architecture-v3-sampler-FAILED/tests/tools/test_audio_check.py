"""Contract tests for tools/audio_check.py (directive v1, PART B step 2).

The script is standalone (stdlib + numpy + sounddevice, both lazily imported)
and must degrade gracefully on a headless box: a clear diagnostic on stderr,
exit code 2, never a traceback. On a box with a working output device it exits
0 after rendering the tone. Both sides of the contract are exercised: the
environment-dependent branch (0 XOR 2, each with its required message) and the
missing-dependency branch, forced deterministically with an import shim in a
subprocess.
"""
from __future__ import annotations

import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(REPO, "tools", "audio_check.py")


def _run(env=None, args=()):
    return subprocess.run([sys.executable, SCRIPT, *args],
                          capture_output=True, text=True, env=env, timeout=120)


def test_exit_code_contract():
    r = _run()
    assert r.returncode in (0, 2), (r.returncode, r.stdout, r.stderr)
    if r.returncode == 2:
        # graceful headless path: a named diagnostic, never a traceback.
        assert "audio_check:" in r.stderr, r.stderr
        assert "Traceback" not in r.stderr, r.stderr
    else:
        # sounding path (desktop): device list + success line on stdout.
        assert "ok: tone rendered." in r.stdout, r.stdout
        assert "output-capable" in r.stdout, r.stdout


def test_missing_sounddevice_is_actionable(tmp_path):
    # Shadow sounddevice with a module that refuses to import: the script must
    # print the pip-install hint and exit 2 — deterministic on every box.
    (tmp_path / "sounddevice.py").write_text(
        "raise ImportError('shadowed by test_missing_sounddevice_is_actionable')\n")
    env = dict(os.environ, PYTHONPATH=str(tmp_path))
    r = _run(env=env)
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "pip install sounddevice" in r.stderr, r.stderr
    assert "Traceback" not in r.stderr, r.stderr


def test_bad_device_override_is_graceful():
    # Whatever the box (no PortAudio, no devices, or a real desktop), asking
    # for a nonexistent device must end in a diagnostic exit 2, no traceback.
    r = _run(args=("--device", "no-such-device-xyzzy"))
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "audio_check:" in r.stderr, r.stderr
    assert "Traceback" not in r.stderr, r.stderr
