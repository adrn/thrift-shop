import pickle

import astropy.coordinates as coord
import astropy.table as at
import astropy.units as u
import gala.dynamics as gd
import gala.potential as gp
import numpy as np
from scipy.interpolate import interp1d
from scipy.optimize import minimize
from tqdm import tqdm

from .config import galcen_frame, cache_path
from .potentials import fiducial_mdisk, get_mw_potential, get_equivalent_galpy
from .actions_staeckel import StaeckelFudgeGrid
from .atm import AbundanceTorusMaschine


class TorusImagingObjective:

    def __init__(self, t, c, elem_name, tree_K=64):
        self.aaf_comp = StaeckelFudgeGrid()
        self.c = c
        self.t = t['APOGEE_ID', elem_name, f'{elem_name}_ERR']
        self.elem_name = elem_name

        self._vsun = galcen_frame.galcen_v_sun.d_xyz

        self._init_potential()

        self.tree_K = int(tree_K)

    def _init_potential(self):
        path = cache_path / 'potential-mhalo-interp.pkl'
        if not path.exists():
            print("Computing potential mhalo grid...")

            pot_grid = np.arange(0.35, 1.79+1e-3, 0.04)
            mhalos = []
            for mdisk_f in tqdm(pot_grid):
                pot = get_mw_potential(mdisk_f * fiducial_mdisk)
                mhalos.append(pot['halo'].parameters['m'] / fiducial_mdisk)
            mhalos = np.squeeze(mhalos)

            with open(path, 'wb') as f:
                pickle.dump((pot_grid, mhalos), f)

        else:
            with open(path, 'rb') as f:
                pot_grid, mhalos = pickle.load(f)

        self._mhalo_interp = interp1d(pot_grid, mhalos, kind='cubic',
                                      bounds_error=False, fill_value='extrapolate')

    def get_mw_potential(self, mdisk_f):
        mhalo = self._mhalo_interp(mdisk_f) * fiducial_mdisk
        mdisk = mdisk_f * fiducial_mdisk
        return gp.MilkyWayPotential(disk=dict(m=mdisk),
                                    halo=dict(m=mhalo))

    def get_coeffs(self, mdisk_f, zsun, vzsun):
        # get galcen frame for zsun, vzsun
        vsun = self._vsun.copy()
        vsun[2] = vzsun * u.km/u.s
        galcen_frame = coord.Galactocentric(z_sun=zsun*u.pc,
                                            galcen_v_sun=vsun)
        galcen = self.c.transform_to(galcen_frame)
        w0 = gd.PhaseSpacePosition(galcen.data)

        # get galpy potential for this mdisk_f
        pot = self.get_mw_potential(mdisk_f)
        galpy_pot = get_equivalent_galpy(pot)
        aaf = self.aaf_comp.get_aaf(w0, mdisk_f, galpy_pot)
        aaf = at.QTable(at.hstack((aaf, self.t)))

        atm = AbundanceTorusMaschine(aaf, tree_K=self.tree_K)
        coeff, coeff_cov = atm.get_coeffs_for_elem(self.elem_name)

        return coeff

    def __call__(self, p):
        mdisk_f, zsun, vzsun = p

        if not 0.4 < mdisk_f < 1.8:
            return np.inf

        coeff = self.get_coeffs(mdisk_f, zsun, vzsun)
        val = coeff[1]**2 + coeff[2]**2 + coeff[3]**2
        return val

    def minimize(self, x0=None, **kwargs):
        kwargs.setdefault('method', 'nelder-mead')

        if x0 is None:
            x0 = [1.0, 20.8, 7.78]  # Fiducial values

        res = minimize(self, x0=x0, **kwargs)

        return res