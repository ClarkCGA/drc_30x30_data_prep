"""STAR pipeline stages: iucn, birdlife, combine."""
import logging

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from . import aoh, ranges
from .categories import normalise_category, weight_of
from .store import Progress, load_species

log = logging.getLogger(__name__)

SPECIES_COLUMNS = [
    "id_no", "sci_name", "common_name", "kingdom", "class", "order", "family",
    "category", "category_raw", "category_source", "weight", "source", "included", "status",
    "global_km2", "global_breeding_km2", "global_nonbreeding_km2", "drc_km2", "drc_share",
    "n_cells", "migratory", "marine", "terrestrial", "freshwater", "marine_only",
    "n_polygons", "n_duplicate_polygons", "n_absent_polygons", "n_source_files", "source_files", "category_conflict",
]


# ---------------------------------------------------------------------------
# IUCN (all groups in the global shapefiles, incl. freshwater birds in FW_OTHER)
# ---------------------------------------------------------------------------

def run_iucn(cfg, grid):
    cfg.require("iucn_dir")
    feats = ranges.scan_iucn(cfg, grid)
    attrs = ranges.species_attributes(feats)
    log.info("IUCN: %d features, %d species world-wide", len(feats), len(attrs))

    touching = set(feats.loc[feats["in_bbox"], "id_no"])
    passing = ranges.apply_filters(feats, cfg.filters)
    touching_after_filters = set(feats.loc[feats["in_bbox"] & passing, "id_no"])

    sp = attrs.loc[sorted(touching)].copy()
    if cfg.bird_mode == "aoh_all":  # every bird is scored from BirdLife AOH instead
        sp = sp[sp["class"].str.upper() != "AVES"]
    sp["category_raw"] = sp["category"]
    sp["category"] = sp["category"].map(normalise_category)
    sp["status"] = None
    excl = set(c.upper() for c in cfg.filters["exclude_categories"])
    sp.loc[sp["category"].isin(excl), "status"] = "excluded_category"
    if cfg.filters["exclude_marine_only"]:
        sp.loc[sp["status"].isna() & sp["marine_only"], "status"] = "excluded_marine_only"
    no_w = sp["category"].map(lambda c: weight_of(c, cfg.weights) is None)
    sp.loc[sp["status"].isna() & no_w, "status"] = "excluded_no_weight"
    sp.loc[sp["status"].isna() & ~sp.index.isin(touching_after_filters), "status"] = "excluded_filters_no_drc_range"

    todo = sp.index[sp["status"].isna()]
    tasks = ranges.build_tasks(feats, todo, "iucn", cfg.iucn_dir, cfg.filters)
    summary = ranges.run_tasks(tasks, grid, cfg, "iucn", "IUCN")
    summary = summary.set_index("id_no")

    sp = sp.join(summary.drop(columns=["status"]), how="left")
    sp.loc[sp["status"].isna(), "status"] = summary["status"].reindex(sp.index)[sp["status"].isna()]
    sp = sp.rename(columns={"order_": "order", "n_files": "n_source_files"})
    sp["category_source"] = "IUCN shapefile"
    sp["source"] = "IUCN"
    sp.reset_index().to_csv(cfg.work_dir / "iucn_species.csv", index=False)
    log.info("IUCN species touching the DRC grid: %d; status counts:\n%s",
             len(sp), sp["status"].value_counts().to_string())
    return sp


# ---------------------------------------------------------------------------
# Birds (BirdLife)
# ---------------------------------------------------------------------------

def load_checklist(path):
    x = pd.read_excel(path, header=3)
    x = x[x["SISRecID"].notna()].copy()
    x["id_no"] = x["SISRecID"].astype(np.int64)
    out = pd.DataFrame({
        "id_no": x["id_no"],
        "sci_name": x["Scientific name"].str.strip(),
        "common_name": x["Common name"].str.strip(),
        "order": x["Order"].ffill().str.strip(),
        "family": x["Family name"].str.strip(),
        "category_raw": x["2025 IUCN Red List category"].astype("string").str.strip(),
    }).drop_duplicates("id_no").set_index("id_no")
    return out


def run_birds(cfg, grid):
    """Birds not covered by the IUCN group files: BirdLife Area of Habitat."""
    cfg.require("birdlife_checklist", "aoh_dir")
    checklist = load_checklist(cfg.birdlife_checklist)
    iucn_birds = set()
    if cfg.bird_mode == "iucn_first":
        cfg.require("iucn_dir")
        feats = ranges.scan_iucn(cfg, grid)  # cached feature index, no geometry
        iucn_birds = set(feats.loc[feats["class"].str.upper() == "AVES", "id_no"].astype(int))
        log.info("Birds: %d bird species have IUCN range maps and are handled by the IUCN stage",
                 len(iucn_birds))
    aoh_sum = aoh.run_aoh(cfg, grid, skip_ids=iucn_birds).set_index("id_no")

    rows = []
    for id_no, r in aoh_sum.iterrows():
        rec = r.to_dict()
        rec.update(id_no=id_no, source="BirdLife AOH", kingdom="ANIMALIA", **{"class": "AVES"})
        rows.append(rec)
    sp = pd.DataFrame(rows).set_index("id_no")
    sp = sp.join(checklist, how="left")

    # Category: override CSV > HBW-BirdLife checklist.
    sp["category"] = sp["category_raw"].map(normalise_category)
    sp["category_source"] = np.where(sp["category"].notna(), "HBW-BirdLife checklist v10", None)
    if cfg.bird_category_override is not None:
        ov = pd.read_csv(cfg.bird_category_override).set_index("id_no")["category"].map(normalise_category)
        hit = sp.index.intersection(ov.dropna().index)
        sp.loc[hit, "category"] = ov[hit]
        sp.loc[hit, "category_source"] = "override"
        log.info("Bird categories overridden for %d species", len(hit))

    excl = set(c.upper() for c in cfg.filters["exclude_categories"])
    ok = sp["status"] == "ok"
    sp.loc[ok & sp["category"].isin(excl), "status"] = "excluded_category"
    no_w = sp["category"].map(lambda c: weight_of(c, cfg.weights) is None)
    sp.loc[(sp["status"] == "ok") & no_w, "status"] = "excluded_no_weight"

    sp.reset_index().to_csv(cfg.work_dir / "bird_species.csv", index=False)
    log.info("Birds touching the DRC grid: %d; status counts:\n%s",
             len(sp), sp["status"].value_counts().to_string())
    return sp


# ---------------------------------------------------------------------------
# Combine
# ---------------------------------------------------------------------------

def _species_file(cfg, rec):
    sub, prefix = {"iucn": ("iucn", "iucn"), "birdlife_aoh": ("aoh", "birdlife_aoh")}[rec["range_source"]]
    return cfg.work_dir / sub / f"{prefix}_{int(rec['id_no'])}.parquet"


class _BlockBuckets:
    """Spill (grid_id, column, value) triplets to one Parquet file per row block."""

    def __init__(self, directory, n, step, flush_rows=2_000_000):
        self.dir, self.step, self.flush_rows = directory, step, flush_rows
        self.dir.mkdir(parents=True, exist_ok=True)
        for f in self.dir.glob("*.parquet"):
            f.unlink()
        self.nblocks = (n + step - 1) // step
        self.buf = [[] for _ in range(self.nblocks)]
        self.size = [0] * self.nblocks
        self.writers = [None] * self.nblocks
        self.schema = pa.schema([("grid_id", pa.int32()), ("col", pa.int32()), ("value", pa.float32())])

    def add(self, col, grid_id, value):
        edges = np.searchsorted(grid_id, np.arange(0, self.nblocks + 1) * self.step)
        for b in range(self.nblocks):
            i0, i1 = edges[b], edges[b + 1]
            if i1 > i0:
                self.buf[b].append((grid_id[i0:i1], np.full(i1 - i0, col, np.int32), value[i0:i1]))
                self.size[b] += i1 - i0
                if self.size[b] >= self.flush_rows:
                    self._flush(b)

    def _flush(self, b):
        if not self.buf[b]:
            return
        g, c, v = (np.concatenate(x) for x in zip(*self.buf[b]))
        if self.writers[b] is None:
            self.writers[b] = pq.ParquetWriter(self.dir / f"block_{b:04d}.parquet", self.schema)
        self.writers[b].write_table(pa.table([g, c, v], schema=self.schema))
        self.buf[b], self.size[b] = [], 0

    def close(self):
        for b in range(self.nblocks):
            self._flush(b)
            if self.writers[b] is not None:
                self.writers[b].close()

    def read(self, b):
        f = self.dir / f"block_{b:04d}.parquet"
        return pq.read_table(f) if f.exists() else None


def combine(cfg, grid):
    parts = []
    for name in ("iucn_species.csv", "bird_species.csv"):
        p = cfg.work_dir / name
        if p.exists():
            parts.append(pd.read_csv(p))
        else:
            log.warning("%s not found; run that stage first", p)
    sp = pd.concat(parts, ignore_index=True)
    # Safety net: an id_no present in both tables keeps the IUCN record.
    sp = sp.drop_duplicates("id_no", keep="first")
    sp["weight"] = sp["category"].map(lambda c: weight_of(c if isinstance(c, str) else None, cfg.weights))
    sliver = sp["status"].eq("ok") & (sp["drc_km2"] < cfg.filters["min_drc_km2"])
    sp.loc[sliver, "status"] = "excluded_drc_sliver"
    sp["included"] = sp["status"].eq("ok") & sp["weight"].notna()
    for c in SPECIES_COLUMNS:
        if c not in sp:
            sp[c] = np.nan
    sp = sp[SPECIES_COLUMNS + ["range_source"]].sort_values(["included", "class", "sci_name"],
                                                           ascending=[False, True, True])

    out = cfg.output_dir
    out.mkdir(parents=True, exist_ok=True)
    sp.drop(columns=["range_source"]).to_csv(out / "star_species.csv", index=False)

    inc = sp[sp["included"]].sort_values("id_no").reset_index(drop=True)
    n, step = grid.n, cfg.wide_row_group
    weights = inc["weight"].to_numpy(np.float32)
    threatened_cat = inc["category"].isin(["CR", "EN", "VU"]).to_numpy()

    # Pass 1: stream species one at a time -> per-cell summaries + row-block buckets.
    total = np.zeros(n, np.float64)
    threatened = np.zeros(n, np.float64)
    richness = np.zeros(n, np.int32)
    buckets = _BlockBuckets(cfg.work_dir / "combine_blocks", n, step)
    prog = Progress(len(inc), "combine pass 1 (species)", log)
    for j, rec in enumerate(inc.to_dict("records")):
        t = load_species(_species_file(cfg, rec))
        g = t["grid_id"].to_numpy()
        v = t["share"].to_numpy() * weights[j]
        total[g] += v
        richness[g] += 1
        if threatened_cat[j]:
            threatened[g] += v
        buckets.add(j, g, v.astype(np.float32))
        prog.step()
    buckets.close()
    pq.write_table(pa.table({
        "grid_id": grid.grid_id,
        "star_total": total.astype(np.float32),
        "star_threatened": threatened.astype(np.float32),
        "n_species": richness,
    }), out / "star_1km_summary.parquet")

    # Pass 2: one row block at a time -> dense (species x rows) block -> one row group.
    cols = [f"sp_{i}" for i in inc["id_no"]]
    schema = pa.schema([("grid_id", pa.int64())] + [(c, pa.float32()) for c in cols])
    prog = Progress(buckets.nblocks, "combine pass 2 (row blocks)", log)
    with pq.ParquetWriter(out / "star_1km_species.parquet", schema, compression="zstd") as w:
        for b in range(buckets.nblocks):
            lo, hi = b * step, min((b + 1) * step, n)
            dense = np.zeros((len(cols), hi - lo), np.float32)  # each species row is contiguous
            t = buckets.read(b)
            if t is not None:
                dense[t["col"].to_numpy(), t["grid_id"].to_numpy() - lo] = t["value"].to_numpy()
            arrays = [pa.array(grid.grid_id[lo:hi])] + [pa.array(dense[j]) for j in range(len(cols))]
            w.write_table(pa.Table.from_arrays(arrays, schema=schema))
            del dense, arrays, t
            prog.step()
    log.info("Outputs written to %s", out)
    return sp
