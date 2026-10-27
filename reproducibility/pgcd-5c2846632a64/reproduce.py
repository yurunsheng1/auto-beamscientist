"""Fixed butterfly centroid experiment; local numerical computation only."""
from pathlib import Path
import argparse
import csv
import gc
import json
import platform

import numpy as np
from scipy.ndimage import map_coordinates
from solver import AngularSpectrum, OpticalSetup, fresnel_direct

ROOT=Path(__file__).resolve().parent


def normalized(field,dx,power):
    total=float(np.sum(abs(field)**2)*dx**2)
    if not np.isfinite(total) or total<=0:raise ValueError('Invalid input power')
    return np.asarray(field,dtype=complex)*np.sqrt(power/total)


def butterfly(x,scale,points=192):
    """C6(u,v) by the same rotated-contour trapezoidal quadrature."""
    s=np.linspace(-3.,3.,points);t=s*np.exp(1j*np.pi/12)
    weights=np.ones(points)*(s[1]-s[0]);weights[[0,-1]]*=.5
    weights=weights*np.exp(1j*np.pi/12)*np.exp(-s**6)
    return (np.exp(1j*np.outer(x/scale,t*t))*weights)@np.exp(1j*np.outer(t,x/scale))


def inputs(config,sim,weight,points=192):
    source=butterfly(sim.x[0],config['source_scale_m'],points)*np.exp(-sim.r2/config['waist_m']**2)
    single=normalized(source*(sim.r2<=config['aperture_radius_m']**2),sim.dx,config['power_w'])
    n=sim.setup.n;coords=np.arange(n)-n//2;x,y=np.meshgrid(coords,coords)
    angle=config['rotation_rad']
    samples=np.array([(-np.sin(angle)*x+np.cos(angle)*y)+n//2,
                      (np.cos(angle)*x+np.sin(angle)*y)+n//2])
    rotated=map_coordinates(single.real,samples,order=1,mode='constant')+1j*map_coordinates(single.imag,samples,order=1,mode='constant')
    rotated=normalized(rotated,sim.dx,config['power_w'])
    pair=single+weight*np.exp(1j*config['relative_phase_rad'])*rotated
    pair_power=float((abs(pair)**2).sum()*sim.dx**2)
    return {'single':single,'rotated':rotated,'coherent':normalized(pair,sim.dx,config['power_w'])},pair_power


def moment(intensity,sim,half=None):
    if half is None:
        total=intensity.sum();cx=float((intensity*sim.x).sum()/total);cy=float((intensity*sim.y).sum()/total)
    else:
        mask=(sim.x>=-half)&(sim.x<half)&(sim.y>=-half)&(sim.y<half)
        cropped=intensity[mask];total=cropped.sum()
        cx=float((cropped*sim.x[mask]).sum()/total);cy=float((cropped*sim.y[mask]).sum()/total)
    return [cx,cy]


def excursion(path):
    c=np.array(path)
    return float(np.linalg.norm(c-c[0],axis=1).max())


def run(config,tier,weight,backend):
    sim=AngularSpectrum(OpticalSetup(n=tier['n'],extent_m=tier['extent_m'],
        wavelength_m=config['wavelength_m'],waist_m=config['waist_m'],power_w=config['power_w']),
        np.linspace(config['z_start_m'],config['z_end_m'],tier['planes']),backend=backend,
        gpu_memory_mb=config['gpu_memory_mb'])
    fields,pair_power=inputs(config,sim,weight)
    refined=inputs(config,sim,weight,points=384)[0]['single'];single=fields['single']
    overlap=float(abs(np.vdot(single,refined))/np.linalg.norm(single)/np.linalg.norm(refined))
    spectra={a:sim.fft2(f) for a,f in fields.items()}
    retention=min(float(sim.input_spectral_retention(s).min()) for s in spectra.values())
    paths={a:[] for a in ('single','rotated','coherent','incoherent')}
    powers={a:[] for a in paths};edges=[];detectors={}
    halves=config['detector_half_widths_m'] if tier['label']=='second_window' else []
    for half in halves:detectors[str(half)]={a:[] for a in paths}
    edge=int(round(sim.setup.n*.12));mask=np.ones(sim.x.shape,bool);mask[edge:-edge,edge:-edge]=False
    for j,z in enumerate(sim.z_m):
        intensities={}
        for arm,f in fields.items():
            propagated=sim.field(spectra[arm],j) if tier['propagator']=='asm' else fresnel_direct(f,sim,float(z))
            intensities[arm]=abs(propagated)**2
        intensities['incoherent']=(intensities['single']+weight**2*intensities['rotated'])/(1+weight**2)
        for arm,intensity in intensities.items():
            paths[arm].append(moment(intensity,sim));total=intensity.sum()
            powers[arm].append(float(total*sim.dx**2));edges.append(float(intensity[mask].sum()/total))
            for half in halves:detectors[str(half)][arm].append(moment(intensity,sim,half))
    values={a:excursion(p) for a,p in paths.items()}
    checks={'finite':bool(np.isfinite(list(values.values())).all()),
            'equal_power':all(abs(float((abs(f)**2).sum()*sim.dx**2)/config['power_w']-1)<1e-9 for f in fields.values()),
            'sampling_retention':retention>=.995,'window_edges':max(edges)<=.01,
            'integral_convergence':overlap>=.9999}
    return {'tier':tier['label'],'weight':weight,'n':tier['n'],'extent_m':tier['extent_m'],
        'propagator':tier['propagator'],'z_m':sim.z_m.tolist(),'centroid_paths_m':paths,
        'excursions_m':values,'coherent_minus_single_m':values['coherent']-values['single'],
        'coherent_minus_incoherent_m':values['coherent']-values['incoherent'],
        'normalization':{'power_w':config['power_w'],'input_pair_power_w':pair_power,
                         'coherent_intensity_factor':config['power_w']/pair_power,'incoherent_intensity_factor':1/(1+weight**2)},
        'minimum_output_power_w':{a:min(p) for a,p in powers.items()},
        'minimum_spectral_retention':retention,'maximum_edge_fraction':max(edges),
        'detector_windows':{h:{'centroid_paths_m':p,'excursions_m':{a:excursion(c) for a,c in p.items()}} for h,p in detectors.items()},
        'checks':checks}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend',choices=('numpy','cuda'),default='numpy')
    parser.add_argument('--suite',choices=('reference','validation'),default='reference')
    parser.add_argument('--conditions',nargs='+',help='Select registered tiers from the requested suite')
    parser.add_argument('--output',type=Path,default=Path('results'))
    args=parser.parse_args();config=json.loads((ROOT/'config.json').read_text());expected=json.loads((ROOT/'expected.json').read_text())
    tiers=config['tiers'] if args.suite=='validation' else config['tiers'][:1]
    if args.conditions:
        if set(args.conditions)-{t['label'] for t in tiers}:parser.error('Conditions must belong to the selected suite')
        tiers=[t for t in tiers if t['label'] in args.conditions]
    args.output.mkdir(parents=True,exist_ok=False);results=[]
    for tier in tiers:
        for weight in config['weights']:
            row=run(config,tier,weight,args.backend);target=expected[tier['label']][str(weight)]
            pairs=[(row['excursions_m'][a],target['excursions_m'][a]) for a in ('single','coherent','incoherent')]
            pairs.extend((row[k],target[k]) for k in ('coherent_minus_single_m','coherent_minus_incoherent_m'))
            row['matches_archived_measurement']=bool(all(np.isclose(a,b,rtol=1e-7,atol=1e-12) for a,b in pairs))
            for half,detector in row['detector_windows'].items():
                for a,value in detector['excursions_m'].items():
                    if not np.isclose(value,target['detector_windows'][half]['excursions_m'][a],rtol=1e-7,atol=1e-12):row['matches_archived_measurement']=False
            results.append(row)
            (args.output/'results.json').write_text(json.dumps({'python':platform.python_version(),'numpy':np.__version__,
                'backend':args.backend,'reference_comparison_tolerance_m':1e-12,
                'note':'Archive comparison tolerance is a code-regression check; the paper target and 3.125e-6 m acceptance floor remain unchanged.',
                'results':results},indent=2)+'\n')
            with (args.output/'centroid_trajectories.csv').open('w',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(['tier','weight','arm','z_m','centroid_x_m','centroid_y_m'])
                for r in results:
                    for arm,path in r['centroid_paths_m'].items():
                        writer.writerows((r['tier'],r['weight'],arm,z,c[0],c[1]) for z,c in zip(r['z_m'],path))
            print(f"{tier['label']} weight={weight:g}: contrast={row['coherent_minus_single_m']:.12g} m; matches_archive={row['matches_archived_measurement']}; checks={all(row['checks'].values())}",flush=True)
            gc.collect()
            if args.backend=='cuda':
                import cupy as cp
                cp.get_default_memory_pool().free_all_blocks()
    if not all(r['matches_archived_measurement'] and all(r['checks'].values()) for r in results):raise SystemExit('A calculation did not reproduce its reference; inspect results.json')


if __name__=='__main__':main()
