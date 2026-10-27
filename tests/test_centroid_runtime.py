"""Falsification checks for the downloadable fixed centroid calculation."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

try:
    import numpy as np
    import scipy
except ImportError:
    np=None

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'reproducibility/pgcd-5c2846632a64'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


@unittest.skipIf(np is None,'Optional numerical runtime dependencies are absent')
class CentroidRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.solver=load('paper_centroid_solver',PACKAGE/'solver.py')
        with mock.patch.dict(sys.modules,{'solver':cls.solver}):
            cls.runtime=load('paper_centroid_runtime',PACKAGE/'reproduce.py')
        cls.config=json.loads((PACKAGE/'config.json').read_text())

    def test_detector_truncation_changes_centroid_for_identical_propagated_intensity(self):
        sim=self.solver.AngularSpectrum(self.solver.OpticalSetup(n=128),[.02,.06])
        intensity=np.exp(-2*((sim.x-.4e-3)**2+sim.y**2)/(200e-6)**2)
        full=self.runtime.moment(intensity,sim)
        cropped=self.runtime.moment(intensity,sim,.3e-3)
        self.assertAlmostEqual(full[0],.4e-3,delta=1e-8)
        self.assertLess(cropped[0],.3e-3)

    def test_zero_weight_identity_equal_power_and_symmetric_limit_are_computed(self):
        tier={**self.config['tiers'][0],'n':64,'planes':5}
        zero=self.runtime.run(self.config,tier,0.,'numpy')
        self.assertAlmostEqual(zero['coherent_minus_single_m'],0.,delta=1e-15)
        self.assertAlmostEqual(zero['coherent_minus_incoherent_m'],0.,delta=1e-15)
        self.assertTrue(all(zero['checks'].values()))
        equal=self.runtime.run(self.config,tier,1.,'numpy')
        self.assertLess(equal['excursions_m']['coherent'],1e-10)
        self.assertLess(equal['excursions_m']['incoherent'],1e-10)
        self.assertGreater(equal['excursions_m']['single'],1e-6)
        # Runtime code must compute without reading expected.json; a condition
        # reproduces physics before any archive comparison in the CLI.
        self.assertNotIn('matches_archived_measurement',equal)


if __name__=='__main__':unittest.main()
