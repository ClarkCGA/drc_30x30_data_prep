"""Per-species results as small Parquet parts, plus progress logging."""
import logging
import time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

SCHEMA = pa.schema([("grid_id", pa.int32()), ("share", pa.float32()), ("drc_km2", pa.float32())])


def save_species(path, grid_id, share, drc_km2):
    """Write one species' sparse cell values (sorted by grid_id) atomically."""
    order = np.argsort(grid_id, kind="stable")
    table = pa.table({
        "grid_id": np.asarray(grid_id, dtype=np.int32)[order],
        "share": np.asarray(share, dtype=np.float32)[order],
        "drc_km2": np.asarray(drc_km2, dtype=np.float32)[order],
    }, schema=SCHEMA)
    tmp = path.with_suffix(".tmp")
    pq.write_table(table, tmp, compression="zstd")
    tmp.rename(path)


def load_species(path):
    return pq.read_table(path)


class Progress:
    """Logs done/total, elapsed time, throughput and ETA at most every `every` seconds."""

    def __init__(self, total, label, log=None, every=30):
        self.total, self.label, self.every = total, label, every
        self.log = log or logging.getLogger(__name__)
        self.t0 = self.last = time.time()
        self.done = 0

    def step(self, n=1):
        self.done += n
        now = time.time()
        if now - self.last >= self.every or self.done == self.total:
            self.last = now
            el = now - self.t0
            rate = self.done / el if el > 0 else 0
            eta = (self.total - self.done) / rate if rate > 0 else float("nan")
            self.log.info("%s: %d/%d done | elapsed %.1f min | %.1f/min | ETA %.1f min",
                          self.label, self.done, self.total, el / 60, rate * 60, eta / 60)
