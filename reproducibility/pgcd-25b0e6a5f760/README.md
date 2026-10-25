# Paper numerical reproduction

This package runs the fixed free-space scalar-optics calculations for this paper.
It includes a propagation solver, a fixed experiment script, numerical parameters,
archived scalar reference values and source hashes. No model API is required.

## Install and run

Use Python 3.10 or later in a fresh virtual environment:

```sh
python -m pip install -r requirements.txt
python reproduce.py --output results
```

The default CPU run evaluates the headline and identity cases. For a compatible
CUDA installation, install the matching CuPy wheel following its official guide,
then select one GPU explicitly:

```sh
CUDA_VISIBLE_DEVICES=0 python reproduce.py --backend cuda --output results-gpu
CUDA_VISIBLE_DEVICES=0 python reproduce.py --backend cuda --suite validation --output validation
```

Full validation runs the frozen mesh, two enlarged windows, doubled axial sampling,
independent direct Fresnel quadrature, 256-level phase quantization, 640 nm holdout
and phase noise with seeds 107 and 109. It can take substantially longer than the
reference calculation, especially Fresnel quadrature on CPU. The Gaussian study
uses a 2048 reference grid and up to 2560 for expanded-window probes. The solver
checks a 4096 MiB estimated GPU working-set budget. No CPU fallback occurs when
CUDA is requested. Existing output directories are never overwritten.

`results.json` records actual calculations and agreement with `expected.json`.
`axial_core.csv` provides per-plane transformed and base collection fractions.
The reported ratio is the ratio of the two median power fractions, not the median
of per-plane ratios. Physical aperture radius remains 0.9 mm. Optical input power
is normalized to 1 W. The core remains fixed on axis. Phase quantization/noise
act on the transformed arm, matching the original protocol. The wavelength probe
rescales its wrapped input phase by 633/640 as in the archived calculation.

The Airy chirp phase radius is 0.30 mm and differs from its 0.20 mm Airy scale.
The Gaussian amplitude waist is 0.10 mm. Vortex phase is exp(i*m*atan2(y,x));
at the sampled origin the factor is 1, with no amplitude regularization.
This is scalar simulation, not a laboratory measurement or a full Maxwell solver.
The conservative radial ASM cutoff is not the complete Matsushima bandlimit.

Only this paper's fixed numerical calculations are included. Hypothesis generation,
autonomous research scheduling, model prompts, manuscript writing, reviewing,
publication automation and credentials are excluded.
