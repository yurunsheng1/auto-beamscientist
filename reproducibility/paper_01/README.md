# Paper 01 reproducibility bundle

This bundle contains the reviewed numerical source used for **“Core-energy concentration in rotationally superposed apodized catastrophe fields”**, its frozen input protocol, solver modules, and archived result artifacts. The public manuscript is available on the [Auto BeamScientist site](https://yurunsheng1.github.io/auto-beamscientist/).

## Re-run the numerical study

Requirements: Python 3.10+, NumPy, SciPy, and a working CUDA installation with a CuPy wheel that matches the installed CUDA version. Install the matching CuPy package using the [official CuPy installation guide](https://docs.cupy.dev/en/stable/install.html); it is not pinned in `requirements.txt` because CUDA versions vary by machine. The recorded scripts request CUDA explicitly; they do not silently fall back to CPU. The run uses bounded search budgets (600 evaluation invocations / 240 s, then 200 / 180 s, then 1000 / 240 s) and the largest verification grid is 1728. GPU memory availability must be sufficient.

Unpack the archive, enter `project/`, install compatible dependencies, then run:

```sh
python -m pip install -r requirements.txt
python runs/pgcd/paper/source/validate_candidates.py
python runs/pgcd/paper/source/additional_controls.py
python runs/pgcd/paper/source/optimize_concentration.py
```

These commands recreate the bounded follow-up, optimized Gaussian coherent control, and absolute-concentration comparison. Alternatively run `./reproduce.sh` from the bundle root. The scripts have immutable-output guards: use a fresh extraction for a clean run. Random seeds and search settings are recorded in each frozen protocol. Device and numerical-library differences can change low-order digits.

To rebuild the manuscript figures and PDF after a successful run, install a LaTeX distribution with `pdflatex` and `bibtex`, plus Matplotlib, PyMuPDF (`pymupdf`) and Pillow, then run:

```sh
python runs/pgcd/paper/source/build_paper.py
```

## Contents and limits

- `project/autophotonics/`: solver, beam definitions, metrics, and bounded search implementation used by the scripts.
- `project/runs/pgcd/paper/source/`: numerical scripts and the manuscript builder.
- `project/runs/pgcd_experiments_20261023T185327Z/cycle_0096/frozen_protocol.json`: original fixed research question and hypothesis definitions.
- `project/runs/pgcd/paper/cache/` and `project/runs/pgcd/paper/`: paper source and bibliographic metadata needed for the PDF build.
- `reference_results/`: archived JSON/NPZ numerical outputs from the published manuscript version; these are reference data and are kept separate from a fresh run's output directory.

The included `collect_data.py` is an archival helper from the original GPU-host workflow; it expects a full historical source-run snapshot and is not part of the clean rerun sequence above. No LLM calls are made by the numerical reproduction scripts. This is a scalar simulation study, not an experimental measurement or proof of novelty.
