# Butterfly centroid experiment

This package computes the fixed numerical experiments for *Centroid Excursion
of an Apodized Butterfly Field and Its Inversion Pair*. It contains the scalar
propagation solver, fixed parameters, reference scalar values and this script.

With Python 3.10 or later:

```sh
python -m pip install -r requirements.txt
python reproduce.py --output results
```

The default CPU run evaluates four amplitude weights (0, 0.4, 0.8, 1) on the
384 × 384 reference grid. For CUDA, install a CuPy wheel compatible with your
CUDA installation, and explicitly select one GPU:

```sh
CUDA_VISIBLE_DEVICES=0 python reproduce.py --backend cuda --output results-gpu
CUDA_VISIBLE_DEVICES=0 python reproduce.py --backend cuda --suite validation --output validation
```

The full suite computes all 24 registered weight/tier conditions: reference,
mesh, 41-plane axial refinement, independent direct Fresnel quadrature, and two
larger propagation domains. `--conditions` selects named tiers from that suite.
The largest tier uses 1536 × 1536 samples, 41 axial planes and an 8192 MiB
estimated GPU workspace budget. Direct Fresnel quadrature may be slow on CPU.
No CPU fallback occurs when CUDA is requested. Existing output directories
are never overwritten.

Every input is normalized to 1 W inside the same 0.9 mm circular aperture.
The wavelength is 633 nm, Gaussian envelope radius and butterfly source scale
are 0.30 mm, and propagation is free space over 20–60 mm without a lens.
Centroids use all pixels in the half-open square [-L/2,L/2) on both axes.
The largest-domain tier additionally integrates smaller detector squares from
the same propagated fields. Coherent intensity is normalized by its measured
input pair power; incoherent intensity is (I_single+a² I_rotated)/(1+a²).
The butterfly source uses a rotated-contour C6 integral with 192 nodes and a
384-node source-convergence check, matching the paper's numerical definition.

`results.json` contains newly calculated centroids, excursions, normalization,
detector-window results, checks and agreement with `expected.json`.
`centroid_trajectories.csv` records full sampled paths. Expected values are used
only for comparison after propagation; they never replace computed results.
The 1 pm archive-comparison tolerance is a code-regression tolerance. It does
not change the paper's original 3.125 μm error floor or its failed target-margin
criterion. These are scalar simulations, not laboratory measurements; the
radial ASM cutoff is not the complete Matsushima passband.

Only this paper's fixed numerical reproduction is included. There is no
autonomous research engine, model/API access, hypothesis generation, scheduling,
manuscript writing, review or publication code, prompts, transcripts or credentials.
