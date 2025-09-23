import ee
from gee_grid_analysis.datasets import load_grid_and_projection, load_datasets
from gee_grid_analysis.utils import get_image_stats, export_table

ee.Initialize()

def rasterize(fc):
    return ee.Image(0).byte().paint(fc, 1)

def export_all(grid, projection, datasets):
    scale = 30

    rasters = {
        'protected_frac': rasterize(datasets['pa']),
        'kba_frac': rasterize(datasets['kba']),
        'cf_frac': rasterize(datasets['cf']),
        'gc_frac': rasterize(datasets['gc']),
        'oil_frac': rasterize(datasets['oil']),
    }

    for name, image in rasters.items():
        result = get_image_stats(image, grid, projection, name, scale)
        export_table(result, f'DRC_1km_{name.upper()}', 'GEE_Downloads', ['grid_id', name])

    continuous = {
        'mean_climate_vulnerability': (datasets['climate'], 1000),
        'mean_GSOC': (datasets['gsoc'], 1000),
        'mean_FLII': (datasets['flii'], 300),
        'mean_GCP_Jung': (datasets['gcp_jung'], 1000),
        'mean_GCP_Dinerstein': (datasets['gcp_dinerstein'], 300),
        'mean_ESP': (datasets['esp'], 1000),
        'mean_agb': (datasets['agb'], 1000),
    }

    for name, (image, scl) in continuous.items():
        result = get_image_stats(image, grid, projection, name, scl)
        export_table(result, f'DRC_1km_{name.upper()}', 'GEE_Downloads', ['grid_id', name])

    tmf = datasets['tmf']
    tmf_classes = {
        'TMF_undisturbed_frac': tmf.eq(10),
        'TMF_degraded_frac': tmf.eq(20),
        'TMF_regrowth_frac': tmf.eq(30),
        'TMF_deforested_frac': tmf.remap([41, 42, 43], [1, 1, 1]).neq(0).unmask().clip(grid),
        'TMF_ongoing_dd_frac': tmf.eq(50)
    }

    for name, img in tmf_classes.items():
        result = get_image_stats(img, grid, projection, name, scale)
        export_table(result, f'DRC_1km_{name.upper()}', 'GEE_Downloads', ['grid_id', name])

    facet = datasets['facet']
    facet_classes = {
        'FACET_water_frac': facet.eq(2),
        'FACET_savanna_frac': facet.eq(4),
        'FACET_primary_forest_frac': facet.eq(5),
        'FACET_secondary_forest_frac': facet.eq(6)
    }

    for name, img in facet_classes.items():
        result = get_image_stats(img, grid, projection, name, 60)
        export_table(result, f'DRC_1km_{name.upper()}', 'GEE_Downloads', ['grid_id', name])

    dou = datasets['dou']
    dou_classes = {
        'urban_center_frac': dou.eq(30),
        'dense_urban_cluster_frac': dou.eq(23),
        'semidense_urban_cluster_frac': dou.eq(22),
        'suburban_periurban_frac': dou.eq(21),
        'rural_cluster_frac': dou.eq(13),
        'low_density_rural_frac': dou.eq(12),
        'very_low_density_rural_frac': dou.eq(11)
    }

    for name, img in dou_classes.items():
        result = get_image_stats(img, grid, projection, name, 1000)
        export_table(result, f'DRC_1km_{name.upper()}', 'GEE_Downloads', ['grid_id', name])

    pop = datasets['pop']
    pop_stats = pop.reduceRegions(
        collection=grid,
        reducer=ee.Reducer.sum(),
        scale=100,
        crs=projection
    ).map(lambda f: f.set('pop_sum', f.get('sum')))

    export_table(pop_stats, 'DRC_1km_GHS_Population_sum', 'GEE_Downloads', ['grid_id', 'pop_sum'])

def main():
    grid, projection = load_grid_and_projection()
    datasets = load_datasets(grid)
    export_all(grid, projection, datasets)

if __name__ == "__main__":
    main()
