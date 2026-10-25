"""Equal-budget absolute-concentration comparison, frozen before measurements.

This is a new, explicitly post-exploration numerical study, not a relabeling of
the old coherent/single effect objective. Uses the reviewed project optimizer.
"""
from dataclasses import asdict
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
from autophotonics.pgcd.research_experiment import ResearchBatch, summarize
from autophotonics.pgcd.beams import normalize, rotate_field
from autophotonics.budgeted_search import optimize_arm, BOUNDS
from autophotonics.designs import Candidate, residual_phase
from autophotonics.discovery import Trial
import validate_candidates as check

OUT = check.OUT
RUN = check.RUN


def main():
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    check.START = time.monotonic()
    check.SECONDS = 240
    check.NMAX = 1000
    if (OUT/'assets/optimization_protocol.json').exists():
        raise RuntimeError('Immutable optimization already exists')
    batch = ResearchBatch.from_dict(json.loads((RUN/'cycle_0096/frozen_protocol.json').read_text()))
    hypotheses = {h.beam.family:h for h in batch.cases[:2]}
    protocol = {'objective': 'Absolute median core energy / input power, not coherent-versus-single gain',
                'selection_grid':384, 'verification_grids':[384,576,768,1152],
                'budget_per_arm':64, 'seed':103, 'bounds':BOUNDS,
                'arms':['gaussian_single','pearcey_single','pearcey_coherent','butterfly_single','butterfly_coherent'],
                'transform': 'q2*rho^2 + q3*(u^3+v^3) + q4*rho^4 + ripple*sin(2*rho^2)',
                'ordering':'Apply the common phase family, then form the coherent rotated copy; normalize every final input to 1 W',
                'thresholds':{'success_relative_to_best_control':.03,'metric_convergence':.03,'independent_metric_agreement':.03},
                'environment':'free_space; fixed 0.9 mm aperture; no ideal lens; wavelength 633 nm',
                'hold_out_wavelength_m':640e-9, 'phase_noise_seeds':[103,107,113],
                'noise_rms':.02,'phase_levels':8,'expanded_window':{'extent_m':.0036,'n':1728},
                'scope':'Post-exploration comparison. Two structured sources consume four search arms versus one Gaussian arm. No LLM benefit or global-optimum claim.',
                'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'model_calls':0,'seconds':240,'max_evaluations':1000}
    check.save('optimization_protocol.json',protocol)
    e = check.engine(batch)
    sim = e.sim
    all_trials=[];best={}
    for arm in protocol['arms']:
        family,composition=arm.split('_')
        source=e.gaussian if family=='gaussian' else e.input(hypotheses[family])[1]
        def evaluate(_,candidate,reference):
            check.reserve('optimization_'+arm)
            field=source*np.exp(1j*residual_phase(candidate,sim))
            if composition=='coherent':field=normalize(field+rotate_field(field,np.pi),sim.dx,sim.setup.power_w)
            spectrum=sim.fft2(field);keep=float(np.min(sim.input_spectral_retention(spectrum)))
            images=np.asarray([abs(sim.field(spectrum,j))**2 for j in range(len(sim.z_m))])
            m=summarize(images,e,batch)[0];score=m['core_efficiency']
            valid=keep>=.995 and m['maximum_edge_fraction']<=.01
            all_trials.append({'arm':arm,'parameters':candidate.record(),'core_efficiency':score,
                               'minimum_retention':keep,'edge_fraction':m['maximum_edge_fraction'],'valid':bool(valid)})
            return Trial(arm,candidate.q2,candidate.q3,candidate.q4,candidate.ripple,score,score,0.,keep,bool(valid))
        trials=optimize_arm(sim,1.,budget=64,family=arm,names=['q2','q4','q3','ripple'],seed=103,trial_evaluator=evaluate)
        winner=max((t for t in trials if t.admissible),key=lambda t:t.normalized_floor)
        best[arm]={'parameters':winner.candidate().record(),'selection_core_efficiency':winner.normalized_floor}
        check.save('optimized_comparison_trials.json',all_trials)
        check.save('optimized_comparison.json',{'protocol':protocol,'best':best,'status':'searching'})
        print('OPTIMUM',arm,winner.normalized_floor,flush=True)
    def field_for(arm,eng,noise=None,quantize=False):
        family,composition=arm.split('_')
        source=eng.gaussian if family=='gaussian' else eng.input(hypotheses[family])[1]
        field=source*np.exp(1j*residual_phase(Candidate(**best[arm]['parameters']),eng.sim))
        if quantize:field=abs(field)*np.exp(1j*np.round(np.angle(field)*8/(2*np.pi))*2*np.pi/8)
        if noise is not None:field*=np.exp(1j*.02*np.random.default_rng(noise).normal(size=field.shape))
        if composition=='coherent':field=normalize(field+rotate_field(field,np.pi),eng.sim.dx,eng.sim.setup.power_w)
        return field
    verification={}
    for arm in protocol['arms']:
        records={}
        for n in protocol['verification_grids']:
            eng=check.engine(batch,n=n);f=field_for(arm,eng)
            records['n'+str(n)]=check.measure(eng,batch,f,arm+'_verify_n'+str(n),arrays=(n==768))
        eng=check.engine(batch,n=768)
        records['independent']=check.measure(eng,batch,field_for(arm,eng),arm+'_verify_fresnel',direct=True)
        eng=check.engine(batch,n=768,planes=41)
        records['z_refined']=check.measure(eng,batch,field_for(arm,eng),arm+'_verify_z')
        # Same pixel pitch as n=1152 at 2.4mm.
        eng=check.engine(batch,n=1728,extent=.0036)
        records['window']=check.measure(eng,batch,field_for(arm,eng),arm+'_verify_window')
        eng=check.engine(batch,n=768,wavelength=640e-9)
        records['held_out']=check.measure(eng,batch,field_for(arm,eng),arm+'_verify_held_out')
        eng=check.engine(batch,n=768)
        records['quantized']=check.measure(eng,batch,field_for(arm,eng,quantize=True),arm+'_verify_quantized')
        for seed in protocol['phase_noise_seeds']:
            records['noise'+str(seed)]=check.measure(eng,batch,field_for(arm,eng,noise=seed),arm+'_verify_noise'+str(seed))
        verification[arm]=records
        check.save('optimized_comparison.json',{'protocol':protocol,'best':best,'verification':verification,'status':'verifying'})
        print('VERIFIED',arm,records['n768']['metrics']['single']['core_efficiency'],flush=True)
    control_source=json.loads((OUT/'assets/followup_results.json').read_text())['absolute_controls']
    outcome={'protocol':protocol,'best':best,'verification':verification,'nested_classical_search':control_source,
             'status':'completed','evaluations':check.attempts,'elapsed_seconds':time.monotonic()-check.START,
             'simulation_only':True,'novelty_verified':False}
    check.save('optimized_comparison.json',outcome)
    print('COMPARISON_COMPLETE',check.attempts,'evaluations',outcome['elapsed_seconds'],'seconds',flush=True)


if __name__=='__main__':main()
