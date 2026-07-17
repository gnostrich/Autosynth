# litepaper/ — documentation only

This folder contains a post-v1 **litepaper** for the Equilibrium Tape Synth
(ETS). It is **documentation, generated after the build**, and it changes nothing
about the system:

- It creates **no** code, tests, gates, or artifacts.
- It does **not** modify `ets-spec-v0.md`, `ets-connector-v0.md`, `REGISTRY.jsonl`,
  `PREREG.md`, or any source file. Those remain the single authorities; this paper
  is a *reading* of them, not a revision.
- Nothing in the build, CI, or faithfulness manifest depends on these files. They
  are inert with respect to every workflow.

Authorities (if this paper and the sources disagree, **the sources win**):

| Concern | Authority |
|---|---|
| Object definition, F, invariants, gates | `ets-spec-v0.md` |
| Panel↔writer typing, Layer-0 tilt map | `ets-connector-v0.md` |
| Build history, decisions, incidents, real numbers | `REGISTRY.jsonl` |
| Registered experiments | `PREREG.md` |
| Enforced invariant checks | `tests/invariants/manifest.py` |

Every number in the litepaper is traced to one of those sources or to a committed
results artifact (`g0_results.json`, `g1_results.json`, `g2_results.json`,
`training_results.json`, `latency_desktop.json`, `ets/calibration/sigma_phi.json`).
Where a claim could not be verified from the code or registry, the paper says so
rather than inventing.

## Contents and formats

The canonical deliverable is the **LaTeX-typeset PDF**:

- `litepaper.tex` — arXiv-preprint-style LaTeX source (`\documentclass[11pt]{article}`,
  `amsmath`/`amssymb` for the F functional and Gibbs measure, `booktabs` tables,
  `hyperref`, a self-contained **TikZ** pipeline diagram — no external image).
- `litepaper.pdf` — the **rendered PDF** (9 pages).
- `LITEPAPER.md` — the same content in Markdown (companion/source-of-content; the
  PDF is the authoritative rendering).

### Render path used

The PDF was produced with a **real LaTeX engine** (not an HTML/Chromium fallback):

- `pdflatex` from **TeX Live 2023** (installed via
  `apt-get install texlive-latex-base texlive-latex-extra texlive-fonts-recommended
  texlive-science texlive-pictures`), run **twice** so the TikZ diagram and
  `\ref`/`\label` cross-references resolve.
- `tectonic` was tried first but is not available in this environment; the
  Chromium print-to-pdf fallback was **not** needed. This PDF is genuinely
  LaTeX-typeset.

To rebuild:

```bash
cd litepaper && pdflatex litepaper.tex && pdflatex litepaper.tex
```

(Build artifacts `.aux`/`.log`/`.out` are not committed.)
</content>
</invoke>
