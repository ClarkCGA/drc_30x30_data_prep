import ee
from gee_grid_analysis.datasets import load_grid_and_projection, load_gen_datasets, load_iucn_datasets
from gee_grid_analysis.utils import get_image_stats, get_image_max, export_table

ee.Initialize()

def rasterize(fc):
    return ee.Image(0).byte().paint(fc, 1)

def species_richness(fc):
    """Count overlapping species range polygons per pixel using reduceToImage.
    Assigns a constant value of 1 to each feature then sums across all overlapping
    features, yielding a per-pixel species richness count. Scales efficiently to
    large FeatureCollections."""
    return fc.map(lambda f: f.set('presence', 1)).reduceToImage(['presence'], ee.Reducer.sum())

def rasterize_property(fc, property_name):
    """
    Burn a numeric property from a FeatureCollection into a float raster.
    Use with get_image_stats() to compute per-grid-cell mean of that property.
    """
    return ee.Image(0).float().paint(fc, property_name)

def export_gen(grid, projection, datasets):
    scale = 30

    # Protected areas and land designations
    rasters = {
        'protected_frac': rasterize(datasets['pa']),
        'kba_frac': rasterize(datasets['kba']),
        'cf_frac': rasterize(datasets['cf']),
        'gc_frac': rasterize(datasets['gc']),
        'oil_frac': rasterize(datasets['oil'])
    }

    export_names = {
        'protected_frac': 'DRC_1km_ProtectedAreas_Fractional',
        'kba_frac': 'DRC_1km_KBA_Fractional',
        'cf_frac': 'DRC_1km_CF_Fractional',
        'gc_frac': 'DRC_1km_GreenCorridor_Fractional',
        'oil_frac': 'DRC_1km_OilBlocks_Fractional', 
    }

    for name, image in rasters.items():
        result = get_image_stats(image, grid, projection, name, scale)
        export_table(result, export_names[name], ['grid_id', name])

    # Continuous variables
    continuous = {
        'mean_climate_vulnerability': (datasets['climate'], 1000, 'DRC_1km_Climate_Vulnerability'),
        'mean_GSOC': (datasets['gsoc'], 1000, 'DRC_1km_GSOC'),
        'mean_FLII': (datasets['flii'], 300, 'DRC_1km_FLII'),
        'mean_GCP_Jung': (datasets['gcp_jung'], 1000, 'DRC_1km_GCP_Jung'),
        'mean_GCP_Dinerstein': (datasets['gcp_dinerstein'], 300, 'DRC_1km_GCP_Dinerstein'),
        'mean_ESP': (datasets['esp'], 1000, 'DRC_1km_ESP'),
        'mean_esa_agb': (datasets['esa_agb'], 100, 'DRC_1km_ESA_AGB_mean'),
    }

    for name, (image, scl, export_name) in continuous.items():
        result = get_image_stats(image, grid, projection, name, scl)
        export_table(result, export_name, ['grid_id', name])

    # Tropical Moist Forest classes
    tmf = datasets['tmf']
    tmf_classes = {
        'TMF_undisturbed_frac': (tmf.eq(10), 'DRC_1km_TMF_Undisturbed_Fractional'),
        'TMF_degraded_frac': (tmf.eq(20), 'DRC_1km_TMF_Degraded_Fractional'),
        'TMF_regrowth_frac': (tmf.eq(30), 'DRC_1km_TMF_Regrowth_Fractional'),
        'TMF_deforested_frac': (tmf.remap([41, 42, 43], [1, 1, 1]).neq(0).unmask().clip(grid), 'DRC_1km_TMF_Deforested_Fractional'),
        'TMF_ongoing_dd_frac': (tmf.eq(50), 'DRC_1km_TMF_Ongoing_DD_Fractional')
    }

    for name, (img, export_name) in tmf_classes.items():
        result = get_image_stats(img, grid, projection, name, scale)
        export_table(result, export_name, ['grid_id', name])

    # FACET Land Cover classes
    facet = datasets['facet']
    facet_classes = {
        'FACET_water_frac': (facet.eq(2), 'DRC_1km_FACET_Water_Fractional'),
        'FACET_savanna_frac': (facet.eq(4), 'DRC_1km_FACET_Savanna_Fractional'),
        'FACET_primary_forest_frac': (facet.eq(5), 'DRC_1km_FACET_Primary_Forest_Fractional'),
        'FACET_secondary_forest_frac': (facet.eq(6), 'DRC_1km_FACET_Secondary_Forest_Fractional')
    }

    for name, (img, export_name) in facet_classes.items():
        result = get_image_stats(img, grid, projection, name, 60)
        export_table(result, export_name, ['grid_id', name])

    # Degree of Urbanization classes
    dou = datasets['dou']
    dou_classes = {
        'urban_center_frac': (dou.eq(30), 'DRC_1km_DoU_UC_Fractional'),
        'dense_urban_cluster_frac': (dou.eq(23), 'DRC_1km_DoU_DUC_Fractional'),
        'semidense_urban_cluster_frac': (dou.eq(22), 'DRC_1km_DoU_SUC_Fractional'),
        'suburban_periurban_frac': (dou.eq(21), 'DRC_1km_DoU_SUB_Fractional'),
        'rural_cluster_frac': (dou.eq(13), 'DRC_1km_DoU_RC_Fractional'),
        'low_density_rural_frac': (dou.eq(12), 'DRC_1km_DoU_LDR_Fractional'),
        'very_low_density_rural_frac': (dou.eq(11), 'DRC_1km_DoU_VLDR_Fractional')
    }

    for name, (img, export_name) in dou_classes.items():
        result = get_image_stats(img, grid, projection, name, 1000)
        export_table(result, export_name, ['grid_id', name])

    # Population (sum)
    pop = datasets['pop']
    pop_stats = pop.reduceRegions(
        collection=grid,
        reducer=ee.Reducer.sum(),
        scale=100,
        crs=projection
    ).map(lambda f: f.set('pop_sum', f.get('sum')))
    export_table(pop_stats, 'DRC_1km_GHS_Population_sum', ['grid_id', 'pop_sum'])
    
    # Peat Thickness
    result = get_image_stats(datasets['peat_thickness'], grid, projection, 'mean_PeatThickness', 50)
    export_table(result, 'DRC_1km_PeatThickness', ['grid_id', 'mean_PeatThickness'])

    # Human Impact Index
    result = get_image_stats(datasets['human_impact_index'], grid, projection, 'mean_HumanImpactIndex', 300)
    export_table(result, 'DRC_1km_HumanImpactIndex', ['grid_id', 'mean_HumanImpactIndex'])

    # Global Human Modification
    result = get_image_stats(datasets['global_human_modification'], grid, projection, 'mean_GlobalHumanModification', 1000)
    export_table(result, 'DRC_1km_GlobalHumanModification', ['grid_id', 'mean_GlobalHumanModification'])

    # Anthropogenic Pressure (Current and Future)
    current_anthro = datasets['anthropogenic_pressure'].select('b1')
    future_anthro = datasets['anthropogenic_pressure'].select('b2')
    
    result = get_image_stats(current_anthro, grid, projection, 'mean_Anthropogenic_current_pressure', 1000)
    export_table(result, 'DRC_1km_Current_Anthropogenic_Pressure', ['grid_id', 'mean_Anthropogenic_current_pressure'])
    
    result = get_image_stats(future_anthro, grid, projection, 'mean_Anthropogenic_future_pressure', 1000)
    export_table(result, 'DRC_1km_Future_Anthropogenic_Pressure', ['grid_id', 'mean_Anthropogenic_future_pressure'])

    # Natural semi grassland probability
    nat_semi_grassland = datasets['nat_semi_grassland'].eq(22)
    result = get_image_stats(nat_semi_grassland, grid, projection, 'natural_semi_grassland_frac', 30)
    export_table(result, 'DRC_1km_natural_semi_grassland_Fractional', ['grid_id', 'natural_semi_grassland_frac'])

    # Peat Carbon
    result = get_image_stats(datasets['peat_carbon'], grid, projection, 'mean_PeatCarbon', 50)
    export_table(result, 'DRC_1km_PeatCarbon', ['grid_id', 'mean_PeatCarbon'])

    # Forest Ecosystems (7 classes)
    forest_eco = datasets['forest_ecosystems']
    forest_eco_classes = {
        'DenseEvergreen_frac': (forest_eco.eq(1), 'DRC_1km_ForestEcosystems_DenseEvergreen_Fractional'),
        'SemiDeciduous_frac': (forest_eco.eq(2), 'DRC_1km_ForestEcosystems_SemiDeciduous_Fractional'),
        'SemiDeciduousPioneer_frac': (forest_eco.eq(3), 'DRC_1km_ForestEcosystems_SemiDeciduousPioneer_Fractional'),
        'Maranthaceae_frac': (forest_eco.eq(4), 'DRC_1km_ForestEcosystems_Maranthacea_Fractional'),
        'SwampForest_frac': (forest_eco.eq(5), 'DRC_1km_ForestEcosystems_SwampForest_Fractional'),
        'Mangrove_frac': (forest_eco.eq(6), 'DRC_1km_ForestEcosystems_Mangrove_Fractional'),
        'OpenForest_frac': (forest_eco.eq(7), 'DRC_1km_ForestEcosystems_OpenForest_Fractional')
    }

    for name, (img, export_name) in forest_eco_classes.items():
        result = get_image_stats(img, grid, projection, name, 30)
        export_table(result, export_name, ['grid_id', name])

    # Marine Pressure
    result = get_image_stats(datasets['marine_pressure'], grid, projection, 'mean_MarinePressure', 50)
    export_table(result, 'DRC_1km_MarinePressure', ['grid_id', 'mean_MarinePressure'])

    # Biomass Carbon (NASA ORNL - AGB and BGB)
    biomass_carbon = datasets['biomass_carbon']
    agb_nasa = biomass_carbon.select('agb')
    bgb_nasa = biomass_carbon.select('bgb')
    
    result = get_image_stats(agb_nasa, grid, projection, 'mean_ornl_agb', 300)
    export_table(result, 'DRC_1km_ORNL_AGB_mean', ['grid_id', 'mean_ornl_agb'])
    
    result = get_image_stats(bgb_nasa, grid, projection, 'mean_ornl_bgb', 300)
    export_table(result, 'DRC_1km_ORNL_BGB_mean', ['grid_id', 'mean_ornl_bgb'])

    # Soil Erosion
    erosion = rasterize_property(datasets['basin'], "ero_kh_sav")
    result = get_image_stats(erosion, grid, projection, 'mean_erosion', 1000)
    export_table(result, 'DRC_1km_Erosion_mean', ['grid_id', 'mean_erosion'])
    
    # Natural Discharge
    discharge = rasterize_property(datasets['basin'], "dis_m3_pyr")
    result = get_image_stats(discharge, grid, projection, 'mean_discharge', 1000)
    export_table(result, 'DRC_1km_Discharge_mean', ['grid_id', 'mean_discharge'])
    
    # Surface Runoff
    runoff = rasterize_property(datasets['basin'], "run_mm_syr")
    result = get_image_stats(runoff, grid, projection, 'mean_runoff_depth', 1000)
    export_table(result, 'DRC_1km_Surface_Runoff_Depth_mean', ['grid_id', 'mean_runoff_depth'])

    # Recharge
    recharge = datasets['recharge'].select('b1')
    result = get_image_stats(recharge, grid, projection, 'mean_recharge', 1000)
    export_table(result, 'DRC_1km_Recharge_mean', ['grid_id', 'mean_recharge'])

    # Lake and Wetland Presence
    lake_wetland = datasets['lake_wetland'].select('b1').gt(0)
    result = get_image_stats(lake_wetland, grid, projection, 'lake_wetland_frac', 464)
    export_table(result, 'DRC_1km_LakeWetland_Fractional', ['grid_id', 'lake_wetland_frac'])

    # River Network — density and max stream order
    river_density = rasterize(datasets['river_network'])
    result = get_image_stats(river_density, grid, projection, 'river_density_frac', 30)
    export_table(result, 'DRC_1km_RiverDensity_Fractional', ['grid_id', 'river_density_frac'])

    river_order = rasterize_property(datasets['river_network'], 'RIV_ORD')
    result = get_image_max(river_order, grid, projection, 'max_river_order', 30)
    export_table(result, 'DRC_1km_MaxRiverOrder', ['grid_id', 'max_river_order'])

    # Bird Species Richness (BirdLife — 1286 species range polygons)
    birds_richness = species_richness(datasets['birds'])
    result = get_image_max(birds_richness, grid, projection, 'bird_species_richness', 30)
    export_table(result, 'DRC_1km_BirdSpecies_Richness', ['grid_id', 'bird_species_richness'])

def export_iucn(grid, projection, datasets):
    # IUCN Threatened Species — species richness (count of overlapping range polygons per pixel)
    iucn_groups = {
        'amphibians': datasets['amphibians'],
        'freshwater_crabs': datasets['fw_crabs'],
        'freshwater_crayfish': datasets['fw_crayfish'],
        'freshwater_fish': datasets['fw_fish'],
        'freshwater_molluscs': datasets['fw_molluscs'],
        'freshwater_odonata': datasets['fw_odonata'],
        'freshwater_other': datasets['fw_other'],
        'freshwater_plants': datasets['fw_plants'],
        'freshwater_shrimps': datasets['fw_shrimps'],
        'reptiles': datasets['reptiles']
    }

    richness_images = []
    for group_name, fc in iucn_groups.items():
        raster = species_richness(fc)
        richness_images.append(raster)
        result = get_image_max(raster, grid, projection, f'{group_name}_richness', 30)
        export_table(result, f'DRC_1km_IUCN_{group_name}_Richness', ['grid_id', f'{group_name}_richness'])

    # Combined species richness across all groups
    combined = ee.ImageCollection(richness_images).sum()
    result = get_image_max(combined, grid, projection, 'total_species_richness', 30)
    export_table(result, 'DRC_1km_IUCN_Total_Species_Richness', ['grid_id', 'total_species_richness'])



def main():
    grid, projection = load_grid_and_projection()
    gen_datasets = load_gen_datasets(grid)
    iucn_datasets = load_iucn_datasets(grid)
    export_gen(grid, projection, gen_datasets)
    export_iucn(grid, projection, iucn_datasets)

if __name__ == "__main__":
    main()
