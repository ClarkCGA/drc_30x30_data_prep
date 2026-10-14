"""Range-map (polygon) STAR inputs from the IUCN Red List group shapefiles.

For every species whose range touches the DRC grid this module

1. collects ALL of its polygons world-wide, across every group file it
   appears in (some species are duplicated across files, e.g. FW_FISH and
   MARINEFISH),
2. keeps only polygons passing the STAR filters (presence / origin /
   seasonal),
3. drops exact-duplicate geometries and dissolves the rest into one
   (multi)polygon per season set, so overlaps are never double counted,
   then subtracts the species' own "possibly extinct"/"extinct" polygons
   (presence 4/5) for that season,
4. computes the GLOBAL range area in an equal-area projection, and
5. overlays the dissolved range on the 1 km grid (exact cell coverage) to get
   the range area in each DRC cell.

The per-cell output is the unweighted range share
    share_c = area(range ∩ cell c) / global range area
(season-averaged for migrants, see ``season_sets``). Category weights are
applied later in ``combine`` so a category update needs no re-run.
"""
import logging
import multiprocessing as mp
import os
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import pyproj
import shapely
from exactextract import exact_extract
from exactextract.raster import NumPyRasterSource

from .grid import EQUAL_AREA_CRS, GRID_CRS
from .store import Progress, save_species

log = logging.getLogger(__name__)

IUCN_FIELDS = ["id_no", "sci_name", "presence", "origin", "seasonal", "kingdom", "phylum",
               "class", "order_", "family", "category", "marine", "terrestria", "freshwater"]

# Seasonal codes: 1 resident, 2 breeding, 3 non-breeding.
BREEDING = (1, 2)
NONBREEDING = (1, 3)


def season_sets(seasonal_codes):
    """Season sets to evaluate for a species.

    Non-migrants (only resident polygons): one set, the whole range.
    Migrants (any breeding or non-breeding polygon): the breeding range
    (resident + breeding) and the non-breeding range (resident +
    non-breeding) are scored separately and the species' per-cell share is
    the mean over the seasons, so each season carries half the species'
    weight (Mair et al. 2021, STAR). A season with no polygons is skipped.
    """
    codes = set(int(s) for s in seasonal_codes)
    if codes & {2, 3}:
        sets = {}
        if codes & set(BREEDING):
            sets["breeding"] = BREEDING
        if codes & set(NONBREEDING):
            sets["nonbreeding"] = NONBREEDING
        return sets
    return {"all": (1, 2, 3)}


# ---------------------------------------------------------------------------
# Scanning the source files
# ---------------------------------------------------------------------------

def _truthy(s):
    return s.astype(str).str.strip().str.lower().isin(["true", "t", "1", "yes", "y"])


def walk_files(root, suffix):
    """Recursive file listing that follows symlinked folders."""
    for dirpath, _, names in os.walk(root, followlinks=True):
        for n in names:
            if n.lower().endswith(suffix) and not n.startswith("."):
                yield Path(dirpath) / n


def iucn_shapefiles(iucn_dir, exclude_dirs):
    exclude = {d.upper() for d in exclude_dirs}
    files = []
    for p in sorted(walk_files(iucn_dir, ".shp")):
        rel = p.relative_to(iucn_dir)
        if any(part.upper() in exclude for part in rel.parts[:-1]):
            continue
        files.append(p)
    return files


def _scan_file(args):
    """Attributes (no geometry) of one shapefile + which features touch the grid bbox."""
    path, rel, bbox, out = args
    info = pyogrio.read_info(path)
    cols = [c for c in IUCN_FIELDS if c in info["fields"]]
    df = pyogrio.read_dataframe(path, columns=cols, read_geometry=False, fid_as_index=True)
    df.index.name = "fid"
    df = df.reset_index()
    fids_in, _ = pyogrio.read_bounds(path, bbox=bbox)  # streams shapes, keeps only fids
    df["in_bbox"] = df["fid"].isin(fids_in)
    df["file"] = rel
    for c in ("marine", "terrestria", "freshwater"):
        if c in df:
            df[c] = _truthy(df[c])
    df.to_parquet(out)
    return rel, len(df), int(df["in_bbox"].sum())


def scan_iucn(cfg, grid):
    """Feature index (attributes only, no geometry) of every IUCN group file.

    Each file is scanned on its own (in parallel) and cached as a Parquet part,
    so the scan is resumable and never holds more than one file's attributes
    per worker. Geometries are only read later, one species at a time.
    """
    scan_dir = cfg.work_dir / "scan_iucn"
    scan_dir.mkdir(parents=True, exist_ok=True)
    files = iucn_shapefiles(cfg.iucn_dir, cfg.iucn_exclude_dirs)
    if not files:
        raise FileNotFoundError(f"No IUCN shapefiles found under {cfg.iucn_dir}")
    jobs = []
    for p in files:
        rel = str(p.relative_to(cfg.iucn_dir))
        out = scan_dir / (rel.replace("/", "__") + ".parquet")
        if not out.exists():
            jobs.append((str(p), rel, grid.bounds_lonlat, str(out)))
    log.info("IUCN scan: %d files (%d cached)", len(files), len(files) - len(jobs))
    if jobs:
        jobs.sort(key=lambda j: -Path(j[0]).stat().st_size)
        prog = Progress(len(jobs), "IUCN scan (files)", log, every=0)
        with mp.get_context("spawn").Pool(min(cfg.workers, len(jobs))) as pool:
            for rel, n, n_in in pool.imap_unordered(_scan_file, jobs):
                log.info("  scanned %s: %d features, %d touch the DRC bbox", rel, n, n_in)
                prog.step()
    parts = [scan_dir / (str(p.relative_to(cfg.iucn_dir)).replace("/", "__") + ".parquet") for p in files]
    return pd.concat([pd.read_parquet(x) for x in parts], ignore_index=True)


def species_attributes(feats):
    """One row per id_no from the IUCN feature table."""
    g = feats.groupby("id_no")
    first = g[["sci_name", "kingdom", "phylum", "class", "order_", "family"]].first()
    cats = g["category"].agg(lambda s: sorted(set(s.dropna())))
    out = first.assign(
        category=cats.map(lambda c: c[0] if len(c) == 1 else (",".join(c) if c else None)),
        category_conflict=cats.map(len) > 1,
        marine=g["marine"].any(),
        terrestrial=g["terrestria"].any(),
        freshwater=g["freshwater"].any(),
        n_files=g["file"].nunique(),
        source_files=g["file"].agg(lambda s: ";".join(sorted(set(s)))),
    )
    out["marine_only"] = out["marine"] & ~out["terrestrial"] & ~out["freshwater"]
    return out


def apply_filters(feats, filters):
    return (feats["presence"].isin(filters["presence"])
            & feats["origin"].isin(filters["origin"])
            & feats["seasonal"].isin(filters["seasonal"]))


# ---------------------------------------------------------------------------
# Per-species processing (runs in worker processes)
# ---------------------------------------------------------------------------

_W = {}


def _init_worker(id_raster, xmin, ymin, xmax, ymax, cell_area_km2, bounds_lonlat, out_dir,
                 boundary=None):
    if boundary is not None:
        shapely.prepare(boundary)
    _W.update(
        boundary=boundary,
        src=NumPyRasterSource(id_raster, xmin, ymin, xmax, ymax, nodata=-1, srs_wkt=GRID_CRS.to_wkt()),
        cell_area=cell_area_km2,
        bounds=bounds_lonlat,
        out_dir=Path(out_dir),
        to_grid=pyproj.Transformer.from_crs("EPSG:4326", GRID_CRS, always_xy=True),
        to_ea=pyproj.Transformer.from_crs("EPSG:4326", EQUAL_AREA_CRS, always_xy=True),
    )


def _polygonal(geoms):
    """make_valid and keep only polygon parts."""
    geoms = shapely.make_valid(geoms)
    parts = shapely.get_parts(geoms)
    keep = np.isin(shapely.get_type_id(parts), [3, 6])  # Polygon, MultiPolygon
    return parts[keep]


def _clean(geom):
    """Valid (Multi)Polygon made of the polygonal parts of geom, or None."""
    if geom is None or geom.is_empty:
        return None
    parts = shapely.get_parts(_polygonal(np.array([geom])))
    if len(parts) == 0:
        return None
    return parts[0] if len(parts) == 1 else shapely.multipolygons(parts)


def _dissolve(geoms):
    """Union polygons; retry on a fine precision grid if GEOS hits a topology error."""
    try:
        return shapely.union_all(geoms)
    except shapely.errors.GEOSException:
        return shapely.union_all(geoms, grid_size=1e-7)


def _project(geom, transformer):
    return shapely.transform(geom, lambda xy: np.column_stack(transformer.transform(xy[:, 0], xy[:, 1])))


def _equal_area_km2(geom):
    if geom is None or geom.is_empty:
        return 0.0
    return shapely.area(_project(geom, _W["to_ea"])) / 1e6


def _overlay(geom):
    """(grid_id, km2) of the geometry's area in each grid cell."""
    empty = np.empty(0, np.int64), np.empty(0, np.float64)
    g = _clean(shapely.clip_by_rect(geom, *_W["bounds"]))
    if g is None:
        return empty
    # Re-validate after projecting (reprojection can create self-intersections).
    g = _clean(_project(g, _W["to_grid"]))
    if g is not None and _W["boundary"] is not None:
        g = _clean(shapely.intersection(g, _W["boundary"]))
    if g is None:
        return empty
    res = exact_extract(_W["src"], gpd.GeoDataFrame(geometry=[g], crs=GRID_CRS),
                        ["values", "coverage"], output="pandas")
    ids = np.asarray(res["values"].iloc[0], dtype=np.int64)
    cov = np.asarray(res["coverage"].iloc[0], dtype=np.float64)
    keep = cov > 0
    ids, cov = ids[keep], cov[keep]
    return ids, cov * _W["cell_area"][ids]


def process_species(task):
    """Dissolve, measure and grid one species. Returns a summary dict."""
    id_no, source = task["id_no"], task["source"]
    out = {"id_no": id_no, "range_source": source}
    try:
        geoms, seas, pres = [], [], []
        for part in task["parts"]:
            gdf = pyogrio.read_dataframe(part["path"], layer=part.get("layer"), fids=part["fids"],
                                         columns=["presence", "seasonal"])
            geoms.append(gdf.geometry.to_numpy())
            seas.append(gdf["seasonal"].to_numpy())
            pres.append(gdf["presence"].to_numpy())
        geoms = np.concatenate(geoms)
        seas = np.concatenate(seas).astype(int)
        pres = np.concatenate(pres).astype(int)

        # Exact duplicates (same polygon repeated in one or several files).
        dup = pd.Series(list(zip(shapely.to_wkb(geoms), seas, pres))).duplicated().to_numpy()
        absent = np.isin(pres, task["presence_absent"])
        out["n_polygons"] = int((~absent).sum())
        out["n_duplicate_polygons"] = int((dup & ~absent).sum())
        out["n_absent_polygons"] = int((absent & ~dup).sum())
        geoms, seas, absent = geoms[~dup], seas[~dup], absent[~dup]

        sets = season_sets(seas[~absent])
        out["migratory"] = "all" not in sets
        unions, global_km2 = {}, {}
        for name, codes in sets.items():
            sel = _polygonal(geoms[~absent & np.isin(seas, codes)])
            unions[name] = _dissolve(sel) if len(sel) else None
            # Remove areas the species' own map marks as (possibly) extinct for
            # this season, so extant polygons from neighbouring countries that
            # bleed across a border do not override a national extinction.
            mask = _polygonal(geoms[absent & np.isin(seas, codes)])
            if unions[name] is not None and len(mask):
                unions[name] = shapely.difference(unions[name], _dissolve(mask))
                if unions[name].is_empty:
                    unions[name] = None
            global_km2[name] = _equal_area_km2(unions[name])
        whole = unions["all"] if "all" in unions else _dissolve(
            np.array([u for u in unions.values() if u is not None]))
        out["global_km2"] = _equal_area_km2(whole) if "all" not in unions else global_km2["all"]
        for name in ("breeding", "nonbreeding"):
            out[f"global_{name}_km2"] = global_km2.get(name, np.nan)

        # Area of the DRC that the species' own map marks as (possibly) extinct;
        # used to flag national extinctions whose extant remainder is only a
        # boundary artefact (see filters.national_extinct_ratio).
        gone = _polygonal(geoms[absent])
        out["drc_absent_km2"] = float(_overlay(_dissolve(gone))[1].sum()) if len(gone) else 0.0

        ids_all, km2_all = _overlay(whole)
        out["drc_km2"] = float(km2_all.sum())
        out["n_cells"] = int(len(ids_all))
        if len(ids_all) == 0:
            out["status"] = "no_drc_overlap"
            return out

        share = np.zeros(len(ids_all))
        pos = {g: i for i, g in enumerate(ids_all)}
        used = [n for n in unions if unions[n] is not None and global_km2[n] > 0]
        for name in used:
            if name == "all":
                ids, km2 = ids_all, km2_all
            else:
                ids, km2 = _overlay(unions[name])
            idx = np.array([pos.get(g, -1) for g in ids], dtype=np.int64)
            ok = idx >= 0  # season cells are a subset of the whole range's cells
            share[idx[ok]] += km2[ok] / global_km2[name] / len(used)
        out["drc_share"] = float(share.sum())
        save_species(_W["out_dir"] / f"{source}_{id_no}.parquet", ids_all, share, km2_all)
        out["status"] = "ok"
    except Exception as e:  # keep going; the species is reported as failed
        log.exception("species %s failed", id_no)
        out["status"] = f"error: {type(e).__name__}: {e}"
    return out


SUMMARY_COLUMNS = ["id_no", "range_source", "status", "n_polygons", "n_duplicate_polygons",
                   "n_absent_polygons", "drc_absent_km2", "migratory",
                   "global_km2", "global_breeding_km2", "global_nonbreeding_km2", "drc_km2", "n_cells",
                   "drc_share", "aoh_files"]


def append_summary(path, res):
    """Append one result row with a fixed column order (resume-safe log)."""
    if path.exists():
        with open(path) as f:
            header = f.readline().strip().split(",")
        if header != SUMMARY_COLUMNS:  # log written by an older version: migrate it
            old = pd.read_csv(path, on_bad_lines="skip")
            old.reindex(columns=SUMMARY_COLUMNS).to_csv(path, index=False)
    row = pd.DataFrame([res]).reindex(columns=SUMMARY_COLUMNS)
    row.to_csv(path, mode="a", header=not path.exists(), index=False)


def read_summary(path):
    if not path.exists():
        return pd.DataFrame(columns=SUMMARY_COLUMNS)
    return pd.read_csv(path).drop_duplicates("id_no", keep="last")


def run_tasks(tasks, grid, cfg, out_subdir, label):
    """Process species tasks in a worker pool, one species per task.

    Each worker reads only the polygons of its species, writes a Parquet part
    and returns a small summary row, which is appended to a CSV log at once.
    Species already in the log are skipped, so runs can be resumed.
    """
    out_dir = cfg.work_dir / out_subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = cfg.work_dir / f"{out_subdir}_summary.csv"
    done_ids = set(read_summary(summary_path)["id_no"].astype(int))
    todo = [t for t in tasks if int(t["id_no"]) not in done_ids]
    if cfg.limit:
        todo = todo[: max(cfg.limit - len(done_ids), 0)]
    # Biggest jobs first so stragglers don't serialise the tail.
    todo.sort(key=lambda t: -sum(len(p["fids"]) for p in t["parts"]))
    log.info("%s: %d species to process (%d already done)", label, len(todo), len(done_ids))
    if todo:
        initargs = (grid.id_raster, grid.xmin, grid.ymin, grid.xmax, grid.ymax,
                    grid.cell_area_km2, grid.bounds_lonlat, str(out_dir), grid.boundary)
        prog = Progress(len(todo), label, log)
        ctx = mp.get_context("spawn")
        # maxtasksperchild recycles workers so memory from a huge range is released.
        with ctx.Pool(cfg.workers, initializer=_init_worker, initargs=initargs, maxtasksperchild=20) as pool:
            for res in pool.imap_unordered(process_species, todo):
                append_summary(summary_path, res)
                prog.step()
    return read_summary(summary_path)


def absence_mask(feats, filters):
    """Polygons the species' own map marks as possibly extinct / extinct."""
    return (feats["presence"].isin(filters["subtract_presence"])
            & feats["origin"].isin(filters["origin"])
            & feats["seasonal"].isin(filters["seasonal"]))


def build_tasks(feats, keep_ids, source, base_dir, filters):
    """Group the selected species' features (extant + absence masks) into tasks."""
    use = apply_filters(feats, filters) | absence_mask(feats, filters)
    ok = feats[use & feats["id_no"].isin(keep_ids)]
    tasks = {}
    for (id_no, file), grp in ok.groupby(["id_no", "file"]):
        t = tasks.setdefault(int(id_no), {"id_no": int(id_no), "source": source, "parts": [],
                                          "presence_absent": list(filters["subtract_presence"])})
        part = {"path": str(Path(base_dir) / file), "fids": grp["fid"].to_numpy()}
        if "layer" in grp:
            part["layer"] = grp["layer"].iloc[0]
        t["parts"].append(part)
    return list(tasks.values())
