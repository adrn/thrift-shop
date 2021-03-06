# Third-party
from astropy.utils import iers
iers.conf.auto_download = False
import gala.dynamics as gd

# This project
from totoro.config import cache_path, galcen_frame
from totoro.data import datasets
from totoro.potentials import potentials, galpy_potentials
from totoro.actions_staeckel import get_staeckel_aaf


def worker(task):
    data_name, potential_name, aaf_filename = task

    # Read APOGEE sample and do parallax & plx s/n cut:
    d = datasets[data_name]
    galcen = d.c.transform_to(galcen_frame)
    w0 = gd.PhaseSpacePosition(galcen.data)

    aaf = get_staeckel_aaf(galpy_potentials[potential_name],
                           w=w0,
                           gala_potential=potentials[potential_name])
    aaf[d._id_column] = d.t[d._id_column]
    aaf.write(aaf_filename, overwrite=True)


def main(pool, overwrite=False):

    tasks = []
    for data_name in datasets.keys():
        for potential_name in potentials:
            filename = cache_path / data_name / f'aaf-{potential_name}.fits'
            if filename.exists() and not overwrite:
                continue

            tasks.append((
                data_name,
                potential_name,
                filename
            ))

    for _ in pool.map(worker, tasks):
        pass


if __name__ == '__main__':
    import sys
    from argparse import ArgumentParser

    # Define parser object
    parser = ArgumentParser()

    parser.add_argument("-o", "--overwrite", dest="overwrite", default=False,
                        action="store_true")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--procs", dest="n_procs", default=1,
                       type=int, help="Number of processes.")
    group.add_argument("--mpi", dest="mpi", default=False,
                       action="store_true", help="Run with MPI.")

    parsed = parser.parse_args()

    # deal with multiproc:
    if parsed.mpi:
        from schwimmbad.mpi import MPIPool
        Pool = MPIPool
        kw = dict()
    elif parsed.n_procs > 1:
        from schwimmbad import MultiPool
        Pool = MultiPool
        kw = dict(processes=parsed.n_procs)
    else:
        from schwimmbad import SerialPool
        Pool = SerialPool
        kw = dict()
    Pool = Pool
    Pool_kwargs = kw

    with Pool(**Pool_kwargs) as pool:
        main(pool=pool, overwrite=parsed.overwrite)

    sys.exit(0)
