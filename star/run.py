"""Command-line entry point for the STAR pipeline.

    python -m star.run --config config/star_config.yaml {iucn,birdlife,combine,all}
"""
import argparse
import logging
import time
from pathlib import Path

from .config import load_config
from .grid import attach_boundary, load_grid
from .pipeline import combine, run_birds, run_iucn


def main(argv=None):
    ap = argparse.ArgumentParser(description="Compute per-cell STAR values for the DRC 1 km grid.")
    ap.add_argument("--config", default="config/star_config.yaml")
    ap.add_argument("stage", choices=["iucn", "birdlife", "combine", "all"])
    ap.add_argument("--limit", type=int, default=0,
                    help="test mode: process at most N species per stage")
    ap.add_argument("--work-dir", help="override paths.work_dir (e.g. for a test run)")
    ap.add_argument("--output-dir", help="override paths.output_dir")
    ap.add_argument("--log-file", help="also write the log to this file")
    args = ap.parse_args(argv)

    handlers = [logging.StreamHandler()]
    if args.log_file:
        handlers.append(logging.FileHandler(args.log_file))
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config(args.config)
    cfg.limit = args.limit
    if args.work_dir:
        cfg.work_dir = Path(args.work_dir).resolve()
    if args.output_dir:
        cfg.output_dir = Path(args.output_dir).resolve()
    cfg.work_dir.mkdir(parents=True, exist_ok=True)
    cfg.require("grid_table")
    t0 = time.time()
    grid = load_grid(cfg.grid_table)
    logging.info("Grid: %d cells, raster %s", grid.n, grid.shape)
    if cfg.drc_boundary is not None:
        cfg.require("drc_boundary")
        attach_boundary(grid, cfg.drc_boundary, cfg.drc_boundary_add_water)
        f = grid.inside_frac
        logging.info("Boundary clip: %d border cells, %d cells outside, %.0f km2 of grid inside boundary",
                     ((f > 0) & (f < 1)).sum(), (f == 0).sum(), (grid.cell_area_km2 * f).sum())
    else:
        logging.info("No drc_boundary configured: full 1 km cells are used (border cells extend "
                     "beyond the DRC)")

    if args.stage in ("iucn", "all"):
        run_iucn(cfg, grid)
    if args.stage in ("birdlife", "all"):
        run_birds(cfg, grid)
    if args.stage in ("combine", "all"):
        combine(cfg, grid)
    logging.info("Done in %.1f min", (time.time() - t0) / 60)


if __name__ == "__main__":
    main()
