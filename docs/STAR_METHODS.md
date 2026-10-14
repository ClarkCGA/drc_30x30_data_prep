# STAR per-cell values: method

This document describes how `star/` computes the Species Threat Abatement and
Restoration (STAR)-style biodiversity layer for the 1 km DRC planning units.
It is written so it can be lifted into the project report.

## Formula

For species *s* and planning unit (1 km cell) *c*:

    STAR(s, c) = W(category_s) × A(s, c) / A_global(s)

* `A(s, c)`: area (km²) of the species' range (or Area of Habitat) inside
  cell *c*, clipped to the DRC boundary.
* `A_global(s)`: area (km²) of the species' entire global range (or AOH),
  computed with the same inclusion rules.
* `W`: category weight (project scheme, "+1 on all classes"):

| Category | CR | EN | VU | DD | NT | LC | EX / EW |
|---|---|---|---|---|---|---|---|
| Weight | 5 | 4 | 3 | 3 | 2 | 1 | excluded |

Legacy categories are mapped as LR/nt → NT, LR/cd → NT, LR/lc → LC. "CR(PE)"
and "CR(PEW)" are treated as CR. BirdLife "NR" (not recognised by IUCN) has no
weight, so those birds are not scored.

The per-cell total is `Σ_s STAR(s, c)`. Each species' values summed over
all cells equal `W × (share of its global range inside the DRC)`. A DRC
endemic of a given category therefore always outscores a widespread species of
the same category.

Weights are applied in the final `combine` step. A category change (e.g. new
bird categories) only needs `combine` to be re-run.

## Species inclusion (applied identically to global and DRC ranges)

| Rule | Value | Notes |
|---|---|---|
| Presence | 1 Extant, 2 Probably extant | 3 (possibly extant), 4, 5, 6 dropped |
| Origin | 1 Native, 2 Reintroduced | introduced, vagrant, uncertain, assisted colonisation dropped |
| Seasonality | 1 Resident, 2 Breeding, 3 Non-breeding | 4 passage, 5 uncertain dropped |
| Extinct areas | polygons with presence 4 (possibly extinct) or 5 (extinct) are **subtracted** from the same-season extant range | stops extant polygons in neighbouring countries leaking across a border where the species is nationally extinct (e.g. black rhino in the DRC) |
| Category | EX and EW excluded | |
| Marine-only | species with `marine = true` and `terrestrial = false` and `freshwater = false` excluded | euryhaline / coastal species with a terrestrial or freshwater system are kept |
| Border slivers | species with < 1 km² of filtered range inside the DRC excluded | sub-cell digitising artefacts (`min_drc_km2`) |

All filters are set in the config file (`filters:`).

## Duplicates and dissolving

Some species appear in more than one IUCN group file (e.g. a fish in both
`FW_FISH` and `MARINEFISH`). Some polygons are also repeated within a file.
For each `id_no`:

1. All polygons are collected from **every** group file.
2. Exact duplicates (identical geometry, presence and season) are dropped and
   counted (`n_duplicate_polygons`).
3. The polygons passing the filters are repaired (`make_valid`) and dissolved
   (unioned) into one (multi)polygon per season set. Overlapping polygons
   are never counted twice.

Areas are **never** taken from `SHAPE_Area` (which is in square degrees).

## Areas

* Global range area: the dissolved polygon is projected to a WGS84
  cylindrical equal-area projection (EPSG:6933), then its planar area is taken.
* Processing is streamed: a scan builds an attribute-only index (no geometry)
  of every group file, one file per worker. Then each species is a separate
  task. A worker reads only that species' polygons (by feature id, from every
  file it appears in), writes a small Parquet part and is recycled regularly.
  AOH rasters are summed block by block. The final wide table is assembled
  one row block at a time. Every stage is resumable.
* Per-cell area: the dissolved range is clipped to the DRC region and
  projected to the grid CRS (DRC Mercator, standard parallel 5°). It is then
  intersected with the DRC boundary, and the exact coverage fraction of every
  1 km cell is computed with `exactextract`. Mercator is conformal and a cell
  is tiny relative to the scale change, so the coverage fraction of a cell is
  its true area fraction. Each cell's true ground area is computed exactly
  (cells are lon/lat rectangles, which map to rectangles in EPSG:6933), and
  coverage × cell area gives km².

### DRC boundary

Border planning units are full 1 km squares that extend into neighbouring
countries. Ranges that stop at a neighbour's side of the border would
otherwise leak into DRC cells. Each range is therefore intersected with the
DRC boundary before gridding:

* Land boundary: geoBoundaries `gbOpen` COD ADM0 (OpenStreetMap-derived,
  ODbL).
* That boundary is land-only, so the DRC's share of the border lakes
  (Tanganyika, Albert, Edward, Kivu, Mweru) is added back from HydroLAKES
  (LakeATLAS v1.0) polygons, limited to the area covered by grid cells.
* About 2,000 grid cells (0.09 %) lie wholly outside the result (Congo estuary
  and Atlantic coast, and cells beyond border rivers). They get no STAR.

## Migratory species (breeding / non-breeding rule)

Following the STAR methodology (Mair et al. 2021, *Nature Ecology &
Evolution*), each season of a migrant carries half of the species' weight:

* Breeding range = Resident (1) + Breeding (2) polygons.
* Non-breeding range = Resident (1) + Non-breeding (3) polygons.
* `STAR(s, c) = W × ½ × [A_breed(s, c)/A_breed_global(s) + A_nonbreed(s, c)/A_nonbreed_global(s)]`.
* If a migrant has only one of the two seasons mapped, that season carries the
  full weight.
* Non-migrants (only resident polygons) use the whole range.

The same rule is applied to BirdLife AOH rasters (Resident / Breeding /
Nonbreeding files).

## Data sources and bird integration

| Group | Source | Global denominator |
|---|---|---|
| Amphibians, mammals, reptiles, freshwater groups, plants, marine groups | IUCN Red List spatial data (2025-2) global group shapefiles | dissolved global range |
| Freshwater-associated birds (~2,300 species world-wide, ranges in `FW_OTHER`). This includes all 538 birds of the IUCN DRC download | same IUCN shapefiles (ranges supplied to IUCN by BirdLife) | dissolved global range |
| All other birds with habitat in the DRC | BirdLife Area of Habitat v2023.1 (1 km, Behrmann equal-area, habitat fraction 0–1) | global AOH = Σ pixel fraction × pixel area |

For AOH birds, the per-cell AOH is the mean habitat fraction over the cell
(GDAL area-weighted "average" warp onto the planning-unit grid, with nodata
set to 0 first) × the cell's area inside the DRC.

Bird Red List categories come from the HBW-BirdLife Checklist v10 (column
"2025 IUCN Red List category", joined on `SISRecID` = IUCN `id_no`). A CSV
(`id_no,category`) given as `bird_category_override` takes precedence.

`birds.mode: aoh_all` switches every bird to AOH.

## Outputs (`output/star/`)

| File | Content |
|---|---|
| `star_species.csv` | one row per species touching the DRC: id_no, names, class, category (+ source), weight, data source, global / breeding / non-breeding km², DRC km², DRC share, cells, migratory, marine/terrestrial/freshwater flags, polygon and duplicate counts, source files, `status` (inclusion decision) and `included` |
| `star_1km_species.parquet` | `grid_id` + one float32 column `sp_<id_no>` per included species = STAR(s, c) |
| `star_1km_summary.parquet` | `grid_id`, `star_total`, `star_threatened` (CR+EN+VU only), `n_species` |

`status` values: `ok`, `excluded_category`, `excluded_marine_only`,
`excluded_no_weight`, `excluded_filters_no_drc_range` (no filtered polygon
reaches the DRC), `no_drc_overlap` (touches the DRC bounding box only),
`excluded_drc_sliver`, `error: …`.

## Differences from the earlier `IUCN_STAR_values.xlsx`

1. The denominator is now the species' **global** range, not its DRC range
   divided by the DRC area.
2. Weights are 5/4/3/3/2/1 (CR/EN/VU/DD/NT/LC); EX/EW are excluded.
3. Marine-only species are excluded.
4. Extinct / uncertain polygons are removed (and subtracted). Duplicate
   polygons and species split across group files are deduplicated and
   dissolved before any area is measured.
