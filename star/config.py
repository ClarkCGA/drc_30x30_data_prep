"""Load and validate the STAR pipeline configuration (YAML)."""
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_FILTERS = {
    "presence": [1, 2],
    "origin": [1, 2],
    "seasonal": [1, 2, 3],
    "subtract_presence": [4, 5],
    "exclude_marine_only": True,
    "min_drc_km2": 1.0,
    "national_extinct_ratio": 0.01,
    "exclude_categories": ["EX", "EW"],
}

DEFAULT_WEIGHTS = {"CR": 5, "EN": 4, "VU": 3, "DD": 3, "NT": 2, "LC": 1}


def _resolve(p):
    if p is None or str(p).strip() == "":
        return None
    p = Path(os.path.expandvars(os.path.expanduser(str(p))))
    return p if p.is_absolute() else REPO_ROOT / p


@dataclass
class Config:
    grid_table: Path
    drc_boundary: Path | None
    drc_boundary_add_water: list
    iucn_dir: Path
    birdlife_checklist: Path | None
    bird_category_override: Path | None
    aoh_dir: Path | None
    work_dir: Path
    output_dir: Path
    iucn_exclude_dirs: list = field(default_factory=list)
    filters: dict = field(default_factory=lambda: dict(DEFAULT_FILTERS))
    weights: dict = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    bird_mode: str = "aoh_all"
    workers: int = 8
    wide_row_group: int = 50000
    limit: int = 0  # test mode: process at most this many species per stage (0 = all)

    def require(self, *names):
        """Fail early with a clear message if required inputs are missing."""
        missing = []
        for n in names:
            p = getattr(self, n)
            if p is None or not Path(p).exists():
                missing.append(f"  {n}: {p}")
        if missing:
            raise FileNotFoundError(
                "Raw input data not found. Set these paths in the config file "
                "(see config/star_config.example.yaml and the README):\n" + "\n".join(missing)
            )


def load_config(path):
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    paths = raw.get("paths", {})
    filters = {**DEFAULT_FILTERS, **(raw.get("filters") or {})}
    weights = {k.upper(): v for k, v in (raw.get("weights") or DEFAULT_WEIGHTS).items()}
    birds = raw.get("birds") or {}
    proc = raw.get("processing") or {}
    cfg = Config(
        grid_table=_resolve(paths.get("grid_table", "data/drc_1km_grid_reference_table.csv")),
        drc_boundary=_resolve(paths.get("drc_boundary")),
        drc_boundary_add_water=[_resolve(x) for x in (paths.get("drc_boundary_add_water") or []) if x],
        iucn_dir=_resolve(paths.get("iucn_dir")),
        birdlife_checklist=_resolve(paths.get("birdlife_checklist")),
        bird_category_override=_resolve(paths.get("bird_category_override")),
        aoh_dir=_resolve(paths.get("aoh_dir")),
        work_dir=_resolve(paths.get("work_dir", "output/star/work")),
        output_dir=_resolve(paths.get("output_dir", "output/star")),
        iucn_exclude_dirs=list(raw.get("iucn_exclude_dirs") or []),
        filters=filters,
        weights=weights,
        bird_mode=birds.get("mode", "aoh_all"),
        workers=int(proc.get("workers", 8)),
        wide_row_group=int(proc.get("wide_row_group", 50000)),
    )
    if cfg.bird_mode not in ("iucn_first", "aoh_all"):
        raise ValueError(f"birds.mode must be 'iucn_first' or 'aoh_all', got {cfg.bird_mode!r}")
    return cfg
