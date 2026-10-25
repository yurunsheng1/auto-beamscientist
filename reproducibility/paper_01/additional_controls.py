"""Common-composition Gaussian control and an unrestricted thin-lens reference."""
from pathlib import Path
import signal
signal.signal(signal.SIGINT, signal.SIG_IGN)
import sys
import time
import json
import numpy as np
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).resolve().parent))
from autophotonics.pgcd.research_experiment import ResearchBatch,summarize
from autophotonics.pgcd.beams import normalize,rotate_field
from autophotonics.budgeted_search import optimize_arm,BOUNDS
from autophotonics.designs import residual_phase,Candidate
from autophotonics.discovery import Trial
import validate_candidates as check


def main():
    check.START=time.monotonic();check.SECONDS=180;check.NMAX=200
    out=check.OUT
    if (out/'assets/additional_control_protocol.json').exists():raise RuntimeError('Frozen control study already exists')
    batch=ResearchBatch.from_dict(json.loads((check.RUN/'cycle_0096/frozen_protocol.json').read_text()))
    protocol={'question':'Does the candidate still improve over Gaussian with the SAME coherent projection and phase-search budget?',
              'budget':64,'seed':103,'bounds':BOUNDS,'selection_n':384,'verification_n':[384,576,768,1152],
              'unrestricted_reference':'Gaussian with a 60mm ideal thin lens, outside the frozen q2 bounds. Included to delimit any bounded-control superiority claim.',
              'seconds':180,'max_evaluations':200,'model_calls':0}
    check.save('additional_control_protocol.json',protocol)
    e=check.engine(batch);sim=e.sim;trials_out=[]
    def score(_,c,ref):
        check.reserve('gaussian_coherent_search')
        field=e.gaussian*np.exp(1j*residual_phase(c,sim))
        field=normalize(field+rotate_field(field,np.pi),sim.dx,1.)
        spectrum=sim.fft2(field);keep=float(np.min(sim.input_spectral_retention(spectrum)))
        stack=np.asarray([abs(sim.field(spectrum,j))**2 for j in range(len(sim.z_m))])
        m=summarize(stack,e,batch)[0];value=m['core_efficiency'];valid=keep>=.995 and m['maximum_edge_fraction']<=.01
        trials_out.append({'parameters':c.record(),'core_efficiency':value,'valid':bool(valid)})
        return Trial(c.family,c.q2,c.q3,c.q4,c.ripple,value,value,0.,keep,bool(valid))
    trials=optimize_arm(sim,1.,budget=64,family='gaussian_coherent',names=['q2','q4','q3','ripple'],seed=103,trial_evaluator=score)
    best=max((t for t in trials if t.admissible),key=lambda t:t.normalized_floor).candidate()
    def source(eng,noise=None,quantize=False):
        field=eng.gaussian*np.exp(1j*residual_phase(best,eng.sim))
        if quantize:field=abs(field)*np.exp(1j*np.round(np.angle(field)*8/(2*np.pi))*2*np.pi/8)
        if noise is not None:field*=np.exp(1j*.02*np.random.default_rng(noise).normal(size=field.shape))
        return normalize(field+rotate_field(field,np.pi),eng.sim.dx,1.)
    records={}
    for n in (384,576,768,1152):
        eng=check.engine(batch,n=n);records['n'+str(n)]=check.measure(eng,batch,source(eng),'gaussian_coherent_verify_n'+str(n),arrays=(n==768))
    eng=check.engine(batch,n=768)
    records['independent']=check.measure(eng,batch,source(eng),'gaussian_coherent_verify_fresnel',direct=True)
    records['quantized']=check.measure(eng,batch,source(eng,quantize=True),'gaussian_coherent_verify_quantized')
    for seed in (103,107,113):records['noise'+str(seed)]=check.measure(eng,batch,source(eng,noise=seed),'gaussian_coherent_verify_noise'+str(seed))
    eng=check.engine(batch,n=768,wavelength=640e-9)
    records['held_out']=check.measure(eng,batch,source(eng),'gaussian_coherent_verify_held_out')
    eng=check.engine(batch,n=768,planes=41)
    records['z_refined']=check.measure(eng,batch,source(eng),'gaussian_coherent_verify_z')
    eng=check.engine(batch,n=1728,extent=.0036)
    records['window']=check.measure(eng,batch,source(eng),'gaussian_coherent_verify_window')
    references={}
    for n in (768,1152):
        eng=check.engine(batch,n=n)
        references['gaussian_lens_n'+str(n)]=check.measure(eng,batch,eng.gaussian*np.exp(1j*eng.sim.lens_phase),'gaussian_lens_n'+str(n))
        references['unmodulated_gaussian_n'+str(n)]=check.measure(eng,batch,eng.gaussian,'unmodulated_gaussian_n'+str(n))
    previous=json.loads((out/'assets/followup_results.json').read_text())['absolute_controls']
    for kind in ('defocus','quadratic_quartic'):
        eng=check.engine(batch,n=768);c=Candidate(**previous[kind]['parameters'])
        references[kind]=check.measure(eng,batch,eng.gaussian*np.exp(1j*residual_phase(c,eng.sim)),'optimized_'+kind+'_n768')
    result={'protocol':protocol,'best':{'parameters':best.record(),'selection_core_efficiency':max(t.normalized_floor for t in trials if t.admissible)},
            'verification':records,'references':references,'trials':trials_out,'evaluations':check.attempts,'elapsed_seconds':time.monotonic()-check.START}
    check.save('additional_controls.json',result)
    print('ADDITIONAL_CONTROLS',json.dumps({'best':best.record(),'verified_core':records['n768']['metrics']['single']['core_efficiency'],'lens_core':references['gaussian_lens_n768']['metrics']['single']['core_efficiency'],'evaluations':check.attempts,'seconds':result['elapsed_seconds']}),flush=True)


if __name__=='__main__':main()
