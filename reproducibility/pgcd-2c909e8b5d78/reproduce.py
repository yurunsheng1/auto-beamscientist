"""Fixed scalar-optics calculations for this paper; no external services."""
from pathlib import Path
import argparse
import csv
import gc
import json
import platform
import numpy as np
from scipy.special import airy
from solver import AngularSpectrum, OpticalSetup, fresnel_direct

ROOT = Path(__file__).resolve().parent


def normalized(field, dx, power):
    return np.asarray(field, dtype=complex) * np.sqrt(power / (np.sum(abs(field)**2) * dx**2))


def input_fields(config, case, sim, label):
    if case['family'] == 'airy':
        s = sim.x[0] / case['scale_m']
        one = airy(s)[0] * np.exp(case['apodization'] * s)
        amplitude = np.outer(one, one)
    elif case['family'] == 'gaussian':
        amplitude = np.exp(-sim.r2 / case['scale_m']**2)
    else:
        raise ValueError('This paper package supports only its fixed source family')
    aperture = sim.r2 <= config['aperture_radius_m']**2
    base = normalized(amplitude * aperture, sim.dx, config['power_w'])
    if case['transformation'] == 'chirp':
        phase = case['amount'] * sim.r2 / case['phase_radius_m']**2
    elif case['transformation'] == 'vortex':
        # atan2(0,0)=0: origin factor 1, no amplitude regularization.
        phase = case['amount'] * np.arctan2(sim.y, sim.x)
    else:
        raise ValueError('Unsupported paper transformation')
    # Normalize after applying phase, as in the frozen calculation.
    transformed = normalized(amplitude * np.exp(1j*phase) * aperture, sim.dx, config['power_w'])
    if label == 'quantization':
        levels = config['quantization_levels']
        transformed = abs(transformed) * np.exp(1j*np.round(np.angle(transformed)/(2*np.pi)*levels)/levels*2*np.pi)
    elif label == 'held_out_wavelength':
        transformed = abs(transformed) * np.exp(1j*np.angle(transformed)*config['wavelength_m']/config['held_out_wavelength_m'])
    elif label.startswith('noise_'):
        seed = int(label.split('_')[1])
        noise = np.random.default_rng(seed).normal(size=transformed.shape)
        transformed *= np.exp(1j*config['noise_rms_rad']*noise)
    return transformed, base


def measure(field, sim, config, solver):
    spectrum = sim.fft2(field)
    retained = float(np.min(sim.input_spectral_retention(spectrum)))
    core = sim.r2 <= config['core_radius_m']**2
    fractions, edges, powers = [], [], []
    for j,z in enumerate(sim.z_m):
        propagated = sim.field(spectrum,j) if solver == 'asm' else fresnel_direct(field,sim,float(z))
        intensity = abs(propagated)**2
        fractions.append(float(intensity[core].sum()*sim.dx**2/config['power_w']))
        powers.append(float(intensity.sum()*sim.dx**2))
        edge = int(round(sim.setup.n*.12))
        mask = np.ones(intensity.shape,bool); mask[edge:-edge,edge:-edge] = False
        edges.append(float(intensity[mask].sum()/intensity.sum()))
    return {'core_efficiency':float(np.median(fractions)), 'axial_core_fraction':fractions,
            'input_power_w':float(np.sum(abs(field)**2)*sim.dx**2),
            'minimum_spectral_retention':retained,'maximum_edge_fraction':max(edges),
            'minimum_output_power_w':min(powers)}


def condition(config,label):
    n,extent = config['reference_n'],config['reference_extent_m']
    dx = extent/n
    if label == 'mesh':n = config['mesh_n']
    elif label in ('window','second_window'):
        extent = config[label+'_extent_m']; n = int(round(extent/dx))
    planes = 2*config['z_planes']-1 if label == 'z_grid' else config['z_planes']
    wavelength = config['held_out_wavelength_m'] if label == 'held_out_wavelength' else config['wavelength_m']
    return n,extent,planes,wavelength,'fresnel' if label == 'fresnel' else 'asm'


def run(config, case, label, backend):
    n,extent,planes,wavelength,propagator = condition(config,label)
    setup = OpticalSetup(n=n,extent_m=extent,wavelength_m=wavelength,
                         waist_m=case['phase_radius_m'],power_w=config['power_w'])
    sim = AngularSpectrum(setup,np.linspace(config['z_start_m'],config['z_end_m'],planes),
                          backend=backend,gpu_memory_mb=4096)
    transformed,base = input_fields(config,case,sim,label)
    arms = {name:measure(field,sim,config,propagator) for name,field in [('transformed',transformed),('base',base)]}
    ratio = arms['transformed']['core_efficiency']/arms['base']['core_efficiency']
    checks = {'finite':bool(np.isfinite(ratio)),
              'equal_power':all(abs(a['input_power_w']/config['power_w']-1)<1e-9 for a in arms.values()),
              'sampling_retention':all(a['minimum_spectral_retention']>=.995 for a in arms.values()),
              'window_edges':all(a['maximum_edge_fraction']<=.01 for a in arms.values())}
    return {'case':case['id'],'condition':label,'n':n,'extent_m':extent,'z_m':sim.z_m.tolist(),
            'ratio':ratio,'arms':arms,'checks':checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend',choices=['numpy','cuda'],default='numpy')
    parser.add_argument('--suite',choices=['reference','validation'],default='reference',
                        help='Reference computes headline/identity cases; validation adds mesh/window/z/Fresnel and robustness probes.')
    parser.add_argument('--conditions',nargs='+',help='Optionally select named probes from the suite')
    parser.add_argument('--output',type=Path,default=Path('results'))
    args = parser.parse_args()
    config = json.loads((ROOT/'config.json').read_text())
    expected = json.loads((ROOT/'expected.json').read_text())
    labels = ['reference'] if args.suite == 'reference' else ['mesh','reference','window','second_window','fresnel','z_grid','quantization','held_out_wavelength','noise_107','noise_109']
    if args.conditions:
        if set(args.conditions)-set(labels):parser.error('--conditions must belong to the selected suite')
        labels = args.conditions
    args.output.mkdir(parents=True,exist_ok=False)
    results = []
    try:
        for case in config['cases']:
            for label in labels:
                result = run(config,case,label,args.backend)
                target = expected[case['id']][label]
                pairs = [(result['ratio'],target['ratio'])]
                pairs += [(result['arms'][arm]['core_efficiency'],target[key]) for arm,key in [('transformed','transformed_core_efficiency'),('base','base_core_efficiency')]]
                result['matches_archived_measurement'] = bool(all(np.isclose(a,b,rtol=1e-7,atol=1e-10) for a,b in pairs))
                results.append(result)
                (args.output/'results.json').write_text(json.dumps({'python':platform.python_version(),'numpy':np.__version__,'backend':args.backend,'results':results},indent=2)+'\n')
                with (args.output/'axial_core.csv').open('w',newline='') as f:
                    writer = csv.writer(f);writer.writerow(['case','condition','z_m','transformed_core_fraction','base_core_fraction'])
                    for row in results:
                        writer.writerows(zip([row['case']]*len(row['z_m']),[row['condition']]*len(row['z_m']),row['z_m'],row['arms']['transformed']['axial_core_fraction'],row['arms']['base']['axial_core_fraction']))
                print(f"{case['id']} {label}: ratio={result['ratio']:.12g}, matches_archive={result['matches_archived_measurement']}, checks={all(result['checks'].values())}",flush=True)
                gc.collect()
                if args.backend == 'cuda':
                    import cupy as cp
                    cp.get_default_memory_pool().free_all_blocks()
        if not all(r['matches_archived_measurement'] and all(r['checks'].values()) for r in results):
            raise SystemExit('At least one comparison failed; see results.json')
    finally:
        print('Output:',args.output,flush=True)


if __name__ == '__main__':main()
