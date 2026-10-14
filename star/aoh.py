"""BirdLife Area of Habitat (AOH) STAR inputs.

Each raster FRC_<id_no>_<Resident|Breeding|Nonbreeding>.tif holds, per 1 km
pixel of an equal-area (Behrmann, ESRI:54017) grid, the fraction of the pixel
that is suitable habitat inside the species' range. Therefore

    global AOH (km2)   = sum of pixel values x pixel area
    AOH in DRC cell c  = mean habitat fraction over cell c x true area of c

The mean fraction over each 1 km DRC Mercator cell is obtained by warping the
raster onto the planning-unit grid with area-weighted averaging (GDAL
"average", which weights partially overlapping source pixels), after setting
nodata to 0 so that pixels outside the range count as "no habitat".

Seasons follow the same rule as range maps (see ranges.season_sets):
breeding AOH = Resident + Breeding, non-breeding AOH = Resident + Nonbreeding,
and the per-cell share is the mean of the two seasonal shares.
"""
import logging
import multiprocessing as mp
import re
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import Window

from .grid import GRID_CRS
from .ranges import append_summary, read_summary, walk_files
from .store import Progress, save_species

log = logging.getLogger(__name__)

NAME_RE = re.compile(r"^FRC_(\d+)_(Resident|Breeding|Nonbreeding)\.tif$", re.IGNORECASE)


def list_aoh(aoh_dir):
    """DataFrame (id_no, season, path) of every AOH raster in aoh_dir."""
    rows = []
    for p in walk_files(aoh_dir, ".tif"):
        m = NAME_RE.match(p.name)
        if m:
            rows.append((int(m.group(1)), m.group(2).capitalize(), str(p)))
    df = pd.DataFrame(rows, columns=["id_no", "season", "path"]).drop_duplicates(["id_no", "season"])
    if df.empty:
        raise FileNotFoundError(f"No FRC_<id>_<season>.tif rasters found under {aoh_dir}")
    return df.sort_values(["id_no", "season"]).reset_index(drop=True)


def drc_species(files, grid, cache):
    """Keep only rasters whose extent intersects the DRC grid."""
    if cache.exists():
        return pd.read_parquet(cache)
    keep = []
    bbox_cache = {}
    for r in files.itertuples():
        with rasterio.open(r.path) as src:
            key = src.crs.to_wkt()
            if key not in bbox_cache:
                bbox_cache[key] = transform_bounds("EPSG:4326", src.crs, *grid.bounds_lonlat, densify_pts=50)
            l, b, rt, t = bbox_cache[key]
            sb = src.bounds
            keep.append(not (sb.right <= l or sb.left >= rt or sb.top <= b or sb.bottom >= t))
    out = files[np.array(keep, dtype=bool)]
    out = files[files["id_no"].isin(out["id_no"])]  # keep all seasons of those species
    cache.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(cache)
    return out


_W = {}


def _init_worker(shape, transform, row, col, cell_area_km2, bounds_lonlat, out_dir):
    # cell_area_km2 already includes the boundary clip (area inside the DRC).
    _W.update(shape=shape, transform=transform, row=row, col=col, cell_area=cell_area_km2,
              bounds=bounds_lonlat, out_dir=Path(out_dir))


def _raster_km2(path):
    """(global AOH km2, per-grid-cell AOH km2 array) for one raster."""
    with rasterio.open(path) as src:
        px_km2 = abs(src.transform.a * src.transform.e) / 1e6
        nod = src.nodata
        total = 0.0
        for _, win in src.block_windows(1):
            a = src.read(1, window=win)
            valid = np.isfinite(a)
            if nod is not None:
                valid &= a != nod
            total += float(a[valid].sum(dtype=np.float64))
        total *= px_km2

        cell = np.zeros(len(_W["row"]), dtype=np.float64)
        l, b, r, t = transform_bounds("EPSG:4326", src.crs, *_W["bounds"], densify_pts=50)
        inv = ~src.transform
        c0, r0 = inv * (l, t)
        c1, r1 = inv * (r, b)
        c0, r0 = max(int(np.floor(c0)) - 1, 0), max(int(np.floor(r0)) - 1, 0)
        c1, r1 = min(int(np.ceil(c1)) + 1, src.width), min(int(np.ceil(r1)) + 1, src.height)
        if c1 <= c0 or r1 <= r0:
            return total, cell
        win = Window(c0, r0, c1 - c0, r1 - r0)
        a = src.read(1, window=win).astype(np.float32)
        a[~np.isfinite(a)] = 0
        if nod is not None:
            a[a == nod] = 0
        if not a.any():
            return total, cell
        dst = np.zeros(_W["shape"], dtype=np.float32)
        reproject(a, dst, src_transform=src.window_transform(win), src_crs=src.crs,
                  dst_transform=_W["transform"], dst_crs=GRID_CRS.to_wkt(),
                  resampling=Resampling.average, src_nodata=None, dst_nodata=None)
        frac = dst[_W["row"], _W["col"]].astype(np.float64)
        cell = np.clip(frac, 0, 1) * _W["cell_area"]
    return total, cell



def process_aoh(task):
    id_no = task["id_no"]
    out = {"id_no": id_no, "range_source": "birdlife_aoh"}
    try:
        per = {s: _raster_km2(p) for s, p in task["files"].items()}
        seasons = set(per)
        if seasons & {"Breeding", "Nonbreeding"}:
            sets = {}
            if seasons & {"Resident", "Breeding"}:
                sets["breeding"] = [s for s in ("Resident", "Breeding") if s in per]
            if seasons & {"Resident", "Nonbreeding"}:
                sets["nonbreeding"] = [s for s in ("Resident", "Nonbreeding") if s in per]
        else:
            sets = {"all": ["Resident"]}
        out["migratory"] = "all" not in sets
        out["aoh_files"] = ";".join(sorted(per))

        glob_km2 = {n: sum(per[s][0] for s in ss) for n, ss in sets.items()}
        cell_km2 = {n: sum(per[s][1] for s in ss) for n, ss in sets.items()}
        out["global_km2"] = sum(v[0] for v in per.values())
        for n in ("breeding", "nonbreeding"):
            out[f"global_{n}_km2"] = glob_km2.get(n, np.nan)
        whole = sum(v[1] for v in per.values())
        used = [n for n in sets if glob_km2[n] > 0]
        share = sum(cell_km2[n] / glob_km2[n] for n in used) / max(len(used), 1)

        nz = np.flatnonzero(whole > 0)
        out["drc_km2"] = float(whole[nz].sum())
        out["n_cells"] = int(len(nz))
        if len(nz) == 0:
            out["status"] = "no_drc_overlap"
            return out
        out["drc_share"] = float(share[nz].sum())
        save_species(_W["out_dir"] / f"birdlife_aoh_{id_no}.parquet", nz, share[nz], whole[nz])
        out["status"] = "ok"
    except Exception as e:
        log.exception("AOH species %s failed", id_no)
        out["status"] = f"error: {type(e).__name__}: {e}"
    return out


def run_aoh(cfg, grid, skip_ids=()):
    files = list_aoh(cfg.aoh_dir)
    log.info("AOH: %d rasters; checking which touch the DRC (cached after first run)", len(files))
    files = drc_species(files, grid, cfg.work_dir / "aoh_drc_files.parquet")
    if skip_ids:
        files = files[~files["id_no"].isin(skip_ids)]
    tasks = [{"id_no": int(i), "files": dict(zip(g["season"], g["path"]))}
             for i, g in files.groupby("id_no")]
    out_dir = cfg.work_dir / "aoh"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = cfg.work_dir / "aoh_summary.csv"
    done = set(read_summary(summary_path)["id_no"].astype(int))
    todo = [t for t in tasks if t["id_no"] not in done]
    if cfg.limit:
        todo = todo[: max(cfg.limit - len(done), 0)]
    log.info("AOH: %d species touching the DRC (%d already done)", len(tasks), len(done))
    if todo:
        # grid_id == table position, so row/col arrays index cells by grid_id.
        # With a boundary, a border cell's AOH is its mean habitat fraction times
        # the cell area inside the boundary (habitat assumed even within the cell).
        area = grid.cell_area_km2 if grid.inside_frac is None else grid.cell_area_km2 * grid.inside_frac
        initargs = (grid.shape, grid.transform, grid.row, grid.col, area,
                    grid.bounds_lonlat, str(out_dir))
        ctx = mp.get_context("spawn")
        prog = Progress(len(todo), "AOH", log)
        with ctx.Pool(cfg.workers, initializer=_init_worker, initargs=initargs, maxtasksperchild=20) as pool:
            for res in pool.imap_unordered(process_aoh, todo):
                append_summary(summary_path, res)
                prog.step()
    return read_summary(summary_path)
