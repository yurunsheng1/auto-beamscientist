# Paper 01 runtime code

This download contains only the bounded numerical runtime: three Python entry points, the solver/search modules they import, the fixed input protocol required by those scripts, dependencies, and a launcher. It contains no manuscript, archived result files, figures, citation files, or AI Scientist framework/paper materials.

## Requirements

Python 3.10+, NumPy, SciPy, CUDA, and a CuPy wheel compatible with the installed CUDA version. Install the matching CuPy package using the [official installation guide](https://docs.cupy.dev/en/stable/install.html). The scripts request CUDA explicitly and have bounded limits: 600 evaluations / 240 s, then 200 / 180 s, then 1000 / 240 s. The largest grid is 1728.

## Run

Extract the archive and run from its root:

```sh
./reproduce.sh
```

Or install the listed Python dependencies and invoke the three scripts in sequence:

```sh
cd project
python runtime/paper_01/source/validate_candidates.py
python runtime/paper_01/source/additional_controls.py
python runtime/paper_01/source/optimize_concentration.py
```

Use a fresh extraction for each run; the scripts refuse to overwrite frozen outputs. Results are created locally under `project/runs/pgcd/paper/assets/` and are not included in the download.
