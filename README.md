# Spatial Data Preparation - DRC 30 x 30 Planning

This repository prepares the per-planning-unit (1 km grid cell) data layers for the 30 x 30 planning project in the Democratic Republic of the Congo (DRC). It contains two **independent** workflows:

| Workflow | What it does | Runs on | Output |
|---|---|---|---|
| **A. GEE export** (`gee_grid_analysis/`, `scripts/gee/`) | Grid-level summary statistics of environmental, land-cover and species layers using the Google Earth Engine (GEE) Python API | Google Earth Engine (pixi `gee` environment) | `output/drc_1km_data_planning_units.csv` |
| **B. STAR biodiversity layer** (`star/`) | Per-species, per-cell STAR (Species Threat Abatement and Restoration) values from IUCN Red List range maps and BirdLife data | Local machine (pixi `default` environment) | `output/star/*.parquet`, `output/star/star_species.csv` |

The output of this repository can be used within the 30 x 30 optimization toolbox available [here](https://github.com/ClarkCGA/drc_30x30_opt).

## 🔧 Project Structure

```
drc_30x30_data_prep/
├── authenticate.ipynb          # A: GEE authentication
├── pixi.toml / pixi.lock       # A + B: environments (gee, default)
├── gee_grid_analysis/          # A: dataset definitions and GEE helpers
│   ├── datasets.py
│   └── utils.py
├── scripts/
│   └── gee/
│       ├── gee_export.py       # A: export all layers from GEE
│       └── merge_tables.py     # A: merge exports + neighbourhood info
├── star/                       # B: STAR pipeline (python -m star.run)
│   ├── run.py                  #    command-line entry point
│   ├── config.py               #    configuration loading
│   ├── grid.py                 #    1 km grid + DRC boundary clip
│   ├── ranges.py               #    IUCN range polygons (per species, streamed)
│   ├── aoh.py                  #    BirdLife Area of Habitat rasters
│   ├── categories.py           #    Red List categories and weights
│   └── pipeline.py             #    stages: iucn, birdlife, combine
├── config/
│   └── star_config.example.yaml
├── docs/
│   └── STAR_METHODS.md         # B: method description (for the report)
└── data/
    └── drc_1km_grid_reference_table.csv   # planning-unit grid (Git LFS)
```

`data/` (except the LFS-tracked grid table) and `output/` are not version controlled.

---

## Environment (both workflows)

Both workflows run in [pixi](https://pixi.sh) environments defined in `pixi.toml` and pinned in `pixi.lock`. pixi installs everything from conda-forge, including GDAL, and works natively on Linux, macOS and Windows, so neither Docker nor WSL is needed.

| Environment | Used for | Contents |
|---|---|---|
| `default` | B. STAR pipeline | Python 3.12, GDAL, geopandas, pyogrio, rasterio, exactextract, pyarrow, ... |
| `gee` | A. GEE export | everything in `default` + earthengine-api 1.x and JupyterLab |

```bash
# 1. install pixi (once): https://pixi.sh/latest/#installation
#    macOS/Linux:  curl -fsSL https://pixi.sh/install.sh | sh
#    Windows:      powershell -ExecutionPolicy ByPass -c "irm -useb https://pixi.sh/install.ps1 | iex"

# 2. clone the repository
git clone git@github.com:ClarkCGA/drc_30x30_data_prep.git
cd drc_30x30_data_prep
git lfs pull   # fetches data/drc_1km_grid_reference_table.csv (needs Git LFS)

# 3. create the environments
pixi install            # default (STAR)
pixi install -e gee     # GEE
```

---

## A. GEE export

### 1. Authenticate with GEE (once per machine)

Start Jupyter Lab in the `gee` environment:

```bash
pixi run -e gee gee-lab
```

Open `authenticate.ipynb` and run the cells. `ee.Authenticate()` opens Google's web sign-in; **select the Google Cloud project to use with Earth Engine on that page.** The credentials and that project are saved to `~/.config/earthengine/credentials` and reused by the export script, so no project ID is configured in this repository. The last (optional) cell checks that `ee.Initialize()` works.

If the export later fails with `ee.Initialize: no project found`, the saved credentials did not come from this web sign-in (e.g. they were created with `earthengine authenticate` in a terminal). Re-run the notebook with `ee.Authenticate(force=True)` and pick the project again.

### 2. Export Data from GEE

```bash
pixi run -e gee gee-export        # = python scripts/gee/gee_export.py
```

All exports are sent to your Google Drive, in a folder named `DRC_30x30`. You can monitor progress in the [Earth Engine Tasks tab](https://code.earthengine.google.com/tasks).

### 3. Add Neighborhood Information

After the completion of GEE data export, download all the exported CSV files from Google Drive to `data/gee`, and run the following to add spatial neighborhood information and merge all CSV files into a single file for further analysis:

```bash
pixi run -e gee gee-merge         # = python scripts/gee/merge_tables.py
```

This will generate a file named `drc_1km_data_planning_units.csv` in the `output` folder.

### ⚙️ Customization

To change/add datasets or export parameters, modify:

- `gee_grid_analysis/datasets.py`
- `gee_grid_analysis/utils.py`

---

## B. STAR biodiversity layer

The STAR pipeline is a **separate, local** process. It does not use GEE and does not change the GEE export. See [`docs/STAR_METHODS.md`](docs/STAR_METHODS.md) for the full method (formula, filters, weights, migratory-species rule, bird integration and outputs).

In short, for every species *s* and planning unit *c*:

    STAR(s, c) = weight(category_s) × area(range_s ∩ c) / global_range_area_s

with weights CR 5, EN 4, VU 3, DD 3, NT 2, LC 1 (EX/EW excluded).

### ⚠️ Raw data required (not included in this repository)

The pipeline needs the raw IUCN and BirdLife data. **These datasets are not distributed with this repository and must never be committed to GitHub** (size: ~80 GB; their licences do not allow redistribution). Request them from the providers and store them anywhere on your machine:

| Dataset | Where to get it | Config key |
|---|---|---|
| IUCN Red List spatial data: global group shapefiles (AMPHIBIANS, MAMMALS, REPTILES, FW_*, PLANTS, marine groups; ~49 GB) | [IUCN Red List spatial data download](https://www.iucnredlist.org/resources/spatial-data-download) | `iucn_dir` |
| HBW-BirdLife Checklist v10 (`.xlsx`, Red List categories of birds) | [BirdLife taxonomy](https://datazone.birdlife.org/about-our-science/taxonomy) | `birdlife_checklist` |
| BirdLife Area of Habitat rasters (`area-habitat.zip`, unzipped; `FRC_<id>_<season>.tif`); used for all birds | BirdLife International (on request) | `aoh_dir` |
| DRC national boundary: geoBoundaries gbOpen COD ADM0 | [geoBoundaries](https://www.geoboundaries.org/) | `drc_boundary` |
| Lake polygons (HydroLAKES / LakeATLAS v1.0), to add the DRC's share of border lakes back to the land boundary | [HydroATLAS](https://www.hydrosheds.org/hydroatlas) | `drc_boundary_add_water` |

Reading the IUCN shapefiles over a network share is slow. Copy them to a local disk first.

### 1. Set up the environment

Use the `default` pixi environment (see [Environment](#environment-both-workflows)):

```bash
pixi install
```

### 2. Configure the data paths

```bash
cp config/star_config.example.yaml config/star_config.yaml
# edit config/star_config.yaml: point every path to your local copy of the raw data
```

`config/star_config.yaml` is git-ignored. No raw-data path is hard-coded in the code. The config also holds the inclusion filters, category weights and the bird data mode.

### 3. Run

```bash
pixi run star-iucn       # all IUCN groups except birds
pixi run star-birdlife   # all birds: BirdLife Area of Habitat
pixi run star-combine    # apply weights and write the outputs
# or everything at once:
pixi run star-all
```

Every stage streams one file / one species at a time and logs progress (done / total, rate, ETA). Pass `--log-file` to keep a log, and test on a subset with `--limit`:

```bash
pixi run python -m star.run --config config/star_config.yaml all --limit 50 \
    --work-dir output/star_test/work --output-dir output/star_test --log-file output/star_test.log
```

The stages can be resumed: per-species results are cached as Parquet parts in `output/star/work/`. Delete that folder to start from scratch. Re-running only `star-combine` is enough after changing weights, the bird category override file or `min_drc_km2`.

### Outputs (`output/star/`)

| File | Content |
|---|---|
| `star_1km_species.parquet` | `grid_id` + one column `sp_<IUCN id_no>` per species, holding STAR(s, c) |
| `star_1km_summary.parquet` | `grid_id`, `star_total`, `star_threatened` (CR+EN+VU), `n_species` |
| `star_species.csv` | per-species table: id_no, name, class, category, weight, global km², DRC km², source (IUCN / BirdLife), filter decisions (`status`, `included`) |

`grid_id` matches the planning-unit `grid_id` in `data/drc_1km_grid_reference_table.csv` and `output/drc_1km_data_planning_units.csv`.

---

## Acknowledgements
This project is funded by the Wildlife Conservation Society (WCS) through a contract with Clark CGA.


## Support
If you run into any issues running this code, or if you have questions about it you can open a ticket on this GitHub repository or contact Clark CGA team at `cga@clarku.edu`.
