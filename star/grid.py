"""The 1 km DRC planning-unit grid, as a raster template for exact overlay.

The reference table stores the cell centres (x_native, y_native) in the
"DRC Mercator" projection (Mercator, standard parallel 5 deg, WGS84). Cells
are 1000 x 1000 m in that projection. Mercator is not equal-area, so the true
ground area of each cell (which depends on latitude) is computed separately
in an equal-area projection.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pyproj

GRID_CRS = pyproj.CRS("+proj=merc +lat_ts=5 +lon_0=0 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs")
CELL_SIZE = 1000.0
EQUAL_AREA_CRS = pyproj.CRS("EPSG:6933")  # WGS84 cylindrical equal-area (EASE-Grid 2.0)


@dataclass
class Grid:
    grid_id: np.ndarray       # (n,) int64, in table order
    row: np.ndarray           # (n,) raster row of each cell
    col: np.ndarray           # (n,) raster column of each cell
    id_raster: np.ndarray     # (height, width) int32 grid_id, -1 outside the grid
    xmin: float
    ymin: float
    xmax: float
    ymax: float
    cell_area_km2: np.ndarray  # (n,) true ground area, indexed like grid_id
    bounds_lonlat: tuple       # (minx, miny, maxx, maxy) of the grid in EPSG:4326
    # Optional national-boundary clip (see attach_boundary).
    boundary: object = None                 # boundary (multi)polygon in the grid CRS
    inside_frac: np.ndarray | None = None   # (n,) share of each cell inside the boundary

    @property
    def shape(self):
        return self.id_raster.shape

    @property
    def n(self):
        return len(self.grid_id)

    @property
    def transform(self):
        from rasterio.transform import from_origin
        return from_origin(self.xmin, self.ymax, CELL_SIZE, CELL_SIZE)


def load_grid(table_path):
    df = pd.read_csv(table_path, encoding="utf-8-sig",
                     usecols=["grid_id", "x_native", "y_native", "longitude", "latitude"])
    gid = df["grid_id"].to_numpy()
    if not np.all(gid == np.round(gid)):
        raise ValueError("grid_id values are not integers")
    gid = gid.astype(np.int64)
    if not (gid == np.arange(len(gid))).all():
        raise ValueError("Expected grid_id to be 0..n-1 in table order")

    # Sanity check: the stored centres must be the DRC Mercator projection of lon/lat.
    tr = pyproj.Transformer.from_crs("EPSG:4326", GRID_CRS, always_xy=True)
    x, y = tr.transform(df["longitude"].to_numpy(), df["latitude"].to_numpy())
    if max(np.abs(x - df["x_native"]).max(), np.abs(y - df["y_native"]).max()) > 1.0:
        raise ValueError("Grid table coordinates do not match the expected DRC Mercator CRS")

    xs, ys = df["x_native"].to_numpy(), df["y_native"].to_numpy()
    xmin = xs.min() - CELL_SIZE / 2
    ymax = ys.max() + CELL_SIZE / 2
    col = np.rint((xs - xmin) / CELL_SIZE - 0.5).astype(np.int64)
    row = np.rint((ymax - ys) / CELL_SIZE - 0.5).astype(np.int64)
    width, height = col.max() + 1, row.max() + 1
    xmax = xmin + width * CELL_SIZE
    ymin = ymax - height * CELL_SIZE

    id_raster = np.full((height, width), -1, dtype=np.int32)
    id_raster[row, col] = gid

    # Cells are lon/lat rectangles (Mercator is cylindrical), which map to exact
    # rectangles in a cylindrical equal-area projection: area = dx * dy there.
    to_ll = pyproj.Transformer.from_crs(GRID_CRS, "EPSG:4326", always_xy=True)
    to_ea = pyproj.Transformer.from_crs("EPSG:4326", EQUAL_AREA_CRS, always_xy=True)
    y_edges = ymax - np.arange(height + 1) * CELL_SIZE
    lon_edges, _ = to_ll.transform(np.array([xmin, xmin + CELL_SIZE]), np.array([0.0, 0.0]))
    _, lat_edges = to_ll.transform(np.full(height + 1, xmin), y_edges)
    ex, _ = to_ea.transform(lon_edges, [0.0, 0.0])
    _, ey = to_ea.transform(np.zeros(height + 1), lat_edges)
    row_area_km2 = np.abs(ex[1] - ex[0]) * np.abs(np.diff(ey)) / 1e6
    cell_area_km2 = row_area_km2[row]

    lon, lat = df["longitude"].to_numpy(), df["latitude"].to_numpy()
    pad = 0.05  # degrees; cell centres -> cell edges
    bounds_lonlat = (lon.min() - pad, lat.min() - pad, lon.max() + pad, lat.max() + pad)

    return Grid(gid, row, col, id_raster, xmin, ymin, xmax, ymax, cell_area_km2, bounds_lonlat)


def attach_boundary(grid, path, water_paths=()):
    """Clip planning units to a national boundary polygon.

    Border cells are full 1 km squares that stick out of the country. With a
    boundary, only the part of each cell inside it counts towards range areas,
    so species ranges that stop at a neighbouring country's side of the
    border do not leak into DRC planning units.

    Land-only boundaries (e.g. OpenStreetMap / geoBoundaries) leave out the
    country's share of border lakes. ``water_paths`` are lake polygons that
    are added back where they fall inside grid cells, so the grid itself
    defines where the DRC's share of each lake ends.
    """
    import geopandas as gpd
    import shapely

    def read(p):
        g = gpd.read_file(p, bbox=grid.bounds_lonlat).to_crs(GRID_CRS)
        return shapely.union_all(shapely.make_valid(g.geometry.to_numpy()))

    boundary = read(path)
    x0 = grid.xmin + grid.col * CELL_SIZE
    y1 = grid.ymax - grid.row * CELL_SIZE
    cells = shapely.box(x0, y1 - CELL_SIZE, x0 + CELL_SIZE, y1)
    if water_paths:
        shapely.prepare(boundary)
        edge = ~shapely.contains_properly(boundary, cells)
        footprint = shapely.union_all(cells[edge])  # grid cells not fully on land
        water = shapely.union_all([read(p) for p in water_paths])
        boundary = shapely.union_all([boundary, shapely.intersection(water, footprint)])
    shapely.prepare(boundary)
    inside = shapely.contains_properly(boundary, cells)
    frac = inside.astype(np.float64)
    border = np.flatnonzero(~inside & shapely.intersects(boundary, cells))
    frac[border] = shapely.area(shapely.intersection(cells[border], boundary)) / CELL_SIZE ** 2
    grid.boundary = boundary
    grid.inside_frac = frac
    return grid
