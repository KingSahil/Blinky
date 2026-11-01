"""Bound native numerical worker pools before importing numpy/torch/pandas."""
import os


def configure_worker_threads() -> None:
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ.setdefault(name, "1")
