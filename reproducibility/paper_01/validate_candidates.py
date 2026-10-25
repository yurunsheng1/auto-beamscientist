"""Bounded numerical follow-up of the two existing cycle-96 observations.

Reviewed source only. No generated code or API calls. Run from the project root.
All choices below are frozen before measurements; outputs never replace old data.
"""
from dataclasses import asdict, replace
from pathlib import Path
import hashlib
import json
import signal
import sys
import time

signal.signal(signal.SIGINT, signal.SIG_IGN)
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from autophotonics.pgcd.research_experiment import ResearchBatch, summarize
from autophotonics.pgcd.physics import ExperimentEngine, fresnel_direct
from autophotonics.pgcd.beams import normalize, rotate_field
from autophotonics.physics import OpticalSetup
from autophotonics.budgeted_search import optimize_arm, BOUNDS
from autophotonics.designs import residual_phase, Candidate
from autophotonics.discovery import Trial

OUT = ROOT / 'runs/pgcd/paper'
RUN = ROOT / 'runs/pgcd_experiments_20261023T185327Z'
START = time.monotonic()
SECONDS = 240
NMAX = 600
attempts = 0


def save(name, data):
    p = OUT / 'assets' / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, allow_nan=False), encoding='utf-8')


def reserve(label):
    global attempts
    if time.monotonic() - START > SECONDS or attempts >= NMAX:
        raise RuntimeError('Bounded numerical follow-up exhausted its time/evaluation allowance')
    attempts += 1
    p = OUT / 'assets/followup_attempts.jsonl'
    with p.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'attempt': attempts, 'label': label}) + '\n')


def engine(batch, n=384, extent=2.4e-3, planes=21, wavelength=633e-9):
    setup = OpticalSetup(n=n, extent_m=extent, wavelength_m=wavelength)
    return ExperimentEngine(setup, np.linspace(batch.z_start_m, batch.z_end_m, planes),
                            backend='cuda', gpu_memory_mb=4096)


def measure(e, batch, field, label, direct=False, arrays=False):
    reserve(label)
    sim = e.sim
    rotated = rotate_field(field, np.pi)
    coherent = normalize(field + rotated, sim.dx, sim.setup.power_w)
    inputs = {'single': field, 'rotated': rotated, 'coherent': coherent}
    images = {}
    metrics = {}
    curves = {}
    keeps = []
    for name, source in inputs.items():
        spectrum = sim.fft2(source)
        keeps.append(float(np.min(sim.input_spectral_retention(spectrum))))
        stack = np.asarray([abs(fresnel_direct(source, sim, float(z)))**2 if direct
                            else abs(sim.field(spectrum, j))**2
                            for j, z in enumerate(sim.z_m)])
        images[name] = stack
    images['incoherent'] = (images['single'] + images['rotated']) / 2
    for name, stack in images.items():
        metrics[name] = summarize(stack, e, batch, images['single'])[0]
        curves[name] = (stack[:, sim.r2 <= batch.core_radius_m**2].sum(axis=1)
                        * sim.dx**2 / sim.setup.power_w).tolist()
    a, b = metrics['coherent']['core_efficiency'], metrics['single']['core_efficiency']
    checks = {'finite': all(np.isfinite(a).all() for a in images.values()),
              'sampling_retention': min(keeps) >= .995,
              'window_edges': max(m['maximum_edge_fraction'] for m in metrics.values()) <= .01,
              'input_power': all(abs(np.sum(abs(f)**2)*sim.dx**2/sim.setup.power_w - 1) < 1e-9 for f in inputs.values())}
    row = {'label': label, 'setup': asdict(sim.setup), 'lens_applied': False,
           'solver': 'direct_fresnel' if direct else 'scalar_asm', 'z_m': sim.z_m.tolist(),
           'metrics': metrics, 'core_curves': curves, 'relative_gain': a/b - 1,
           'checks': {k: bool(v) for k, v in checks.items()}, 'minimum_retention': min(keeps),
           'input_even_power_fraction': float(np.sum(abs((field+rotated)/2)**2)*sim.dx**2/sim.setup.power_w)}
    if arrays:
        np.savez_compressed(OUT/'assets'/(label+'.npz'), x_m=sim.x[0], z_m=sim.z_m,
                            **{name+'_profile': stack[:, abs(sim.x[0]) < batch.marginal_half_width_m, :].sum(axis=1)*sim.dx
                               for name, stack in images.items()})
    save(label+'.json', row)
    return row


def main():
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    (OUT/'assets').mkdir(parents=True, exist_ok=True)
    if (OUT/'assets/followup_protocol.json').exists():
        raise RuntimeError('Immutable follow-up already exists; do not silently rerun or overwrite')
    batch = ResearchBatch.from_dict(json.loads((RUN/'cycle_0096/frozen_protocol.json').read_text()))
    hypotheses = batch.cases[:2]
    assert all(h.environment.kind == 'free_space' and not h.transformations for h in hypotheses)
    protocol = {'source_cycle': 'cycle_0096', 'source_ids': [h.id for h in hypotheses],
                'selection': 'Post-campaign follow-up of observed positive branches; not prospective discovery',
                'question': 'Does the recorded equal-power rotational-superposition core-energy gain persist under numerical and physical checks?',
                'actual_geometry': 'Free space, no thin-lens phase. The old thin-lens narrative is not used.',
                'metric': 'Median fixed-core energy / input energy over 49..71 mm; radius 35 micrometres',
                'grids': [192, 256, 384], 'window': {'n': 576, 'extent_m': .0036},
                'z_refinement': 41, 'independent_propagator': 'real-space separable Fresnel quadrature on the full common image grid',
                'phase_quantization_levels': 8, 'noise_rms': .02, 'noise_seeds': [103,107,113,127,131],
                'held_out_wavelength_m': 640e-9, 'absolute_baseline_budget_per_family': 64,
                'baseline_bounds': BOUNDS, 'thresholds': {'positive_relative_gain': .05, 'relative_metric_convergence': .03, 'independent_relative_metric_agreement': .03},
                'limits': {'seconds': SECONDS, 'evaluation_invocations': NMAX}, 'model_calls': 0,
                'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    save('followup_protocol.json', protocol)
    results = {}
    for h in hypotheses:
        family = h.beam.family
        rows = {}
        for n in (192,256,384):
            e = engine(batch, n=n)
            rows['n'+str(n)] = measure(e, batch, e.input(h)[1], family+'_n'+str(n), arrays=(n==384))
        e = engine(batch, n=576, extent=.0036)
        rows['window'] = measure(e, batch, e.input(h)[1], family+'_window')
        e = engine(batch, planes=41)
        rows['z_refined'] = measure(e, batch, e.input(h)[1], family+'_z_refined')
        e = engine(batch)
        field = e.input(h)[1]
        rows['independent'] = measure(e, batch, field, family+'_fresnel', direct=True)
        quantized = abs(field)*np.exp(1j*np.round(np.angle(field)*8/(2*np.pi))*2*np.pi/8)
        rows['quantized'] = measure(e, batch, quantized, family+'_quantized')
        rows['noise'] = []
        for seed in protocol['noise_seeds']:
            perturbed = field*np.exp(1j*.02*np.random.default_rng(seed).normal(size=field.shape))
            rows['noise'].append(measure(e, batch, perturbed, family+'_noise'+str(seed)))
        eh = engine(batch, wavelength=640e-9)
        rows['held_out'] = measure(eh, batch, eh.input(h)[1], family+'_held_out')
        base = rows['n384']
        def discrepancy(row):
            return max(abs(row['metrics'][arm]['core_efficiency']/base['metrics'][arm]['core_efficiency']-1)
                       for arm in ('single','coherent'))
        checks = {name: discrepancy(rows[name]) <= .03 for name in ('n256','window','z_refined','independent')}
        checks['basic'] = all(all(r['checks'].values()) for r in [v for k,v in rows.items() if k!='noise']+rows['noise'])
        checks['positive_gain'] = all(r['relative_gain'] >= .05 for r in [v for k,v in rows.items() if k!='noise']+rows['noise'])
        rows['confirmation'] = {'checks': checks, 'passed': all(checks.values()),
                                'metric_relative_discrepancies': {k: discrepancy(rows[k]) for k in ('n192','n256','window','z_refined','independent')}}
        results[family] = rows
        save('followup_results.json', {'protocol': protocol, 'families': results, 'evaluations': attempts})
        print('FOLLOWUP', family, json.dumps(rows['confirmation']), flush=True)
    # Optimize ABSOLUTE concentration rather than the often-degenerate ratio
    # between a Gaussian and its identical rotational copy.
    e = engine(batch)
    sim = e.sim
    controls = {}
    trials_out = []
    for family,names in [('defocus',['q2']),('quadratic_quartic',['q2','q4']),('four_parameter',['q2','q4','q3','ripple'])]:
        def score(_, candidate, reference):
            reserve('baseline_'+family)
            f = e.gaussian*np.exp(1j*residual_phase(candidate, sim))
            spectrum = sim.fft2(f)
            retention = float(np.min(sim.input_spectral_retention(spectrum)))
            stack = np.asarray([abs(sim.field(spectrum,j))**2 for j in range(len(sim.z_m))])
            m = summarize(stack,e,batch)[0]
            admissible = retention >= .995 and m['maximum_edge_fraction'] <= .01
            value = m['core_efficiency']
            trials_out.append({'family':family,'parameters':candidate.record(),'core_efficiency':value,'minimum_retention':retention,'edge_fraction':m['maximum_edge_fraction'],'admissible':bool(admissible)})
            return Trial(family,candidate.q2,candidate.q3,candidate.q4,candidate.ripple,value,value,0.,retention,bool(admissible))
        trials = optimize_arm(sim,1.,budget=64,family=family,names=names,seed=103,trial_evaluator=score)
        best = max((t for t in trials if t.admissible),key=lambda t:t.normalized_floor)
        controls[family] = {'parameters':best.candidate().record(),'absolute_core_efficiency':best.normalized_floor,'evaluations':64}
        print('ABSOLUTE_CONTROL', family, best.normalized_floor, flush=True)
    save('absolute_control_trials.json', trials_out)
    results_out = {'protocol':protocol,'families':results,'absolute_controls':controls,'evaluations':attempts,'elapsed_seconds':time.monotonic()-START,
                   'novelty_verified':False,'simulation_only':True}
    save('followup_results.json', results_out)
    print('FOLLOWUP_COMPLETE', json.dumps({'evaluations':attempts,'elapsed_seconds':results_out['elapsed_seconds'],'controls':controls}),flush=True)


if __name__ == '__main__':
    main()
