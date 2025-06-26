
import ee

def load_grid_and_projection():
    grid = ee.FeatureCollection("projects/earth-engine-071095/assets/Clark_Labs/WCS_Congo/drc_1km_grid_reference_poly_final")
    grid_raster = ee.Image("projects/earth-engine-071095/assets/Clark_Labs/WCS_Congo/drc_1km_grid_reference_drc_mercator")
    projection = grid_raster.projection()
    return grid, projection

def load_datasets(grid):
    return {
        'pop': ee.Image("JRC/GHSL/P2023A/GHS_POP/2020").clip(grid),
        'dou': ee.Image("JRC/GHSL/P2023A/GHS_SMOD_V2-0/2020").clip(grid),
        'facet': ee.Image("projects/ee-madibipacifique/assets/sdsu_10").clip(grid),
        'tmf': ee.ImageCollection("projects/JRC/TMF/v1_2024/TransitionMap_MainClasses").mosaic().clip(grid),
        'agb': ee.Image("projects/sat-io/open-datasets/ESA/ESA_CCI_AGB/CCI_BIOMASS_100m_AGB_2021_v51").clip(grid).select('AGB'),
        'gsoc': ee.Image("projects/earth-engine-071095/assets/Clark_Labs/WCS_Congo/GSOC_MAP_1-5-0").clip(grid),
        'flii': ee.Image("projects/flii-pipeline/assets/final_metric/FLII_final_metric_300m_2022").clip(grid),
        'gcp_jung': ee.Image("projects/ee-madibipacifique/assets/jung").clip(grid),
        'gcp_dinerstein': ee.Image("projects/ee-madibipacifique/assets/Dinesrtein").clip(grid),
        'esp': ee.Image("projects/ee-madibipacifique/assets/ncp").clip(grid),
        'climate': ee.Image("projects/ee-madibipacifique/assets/ClimateVulnerability_VF").clip(grid).select('b4'),
        'pa': ee.FeatureCollection("projects/earth-engine-071095/assets/Clark_Labs/WCS_Congo/DRC_Protected_Areas"),
        'kba': ee.FeatureCollection("projects/earth-engine-071095/assets/Clark_Labs/WCS_Congo/DRC_Key_Biodiversity_Areas"),
        'cf': ee.FeatureCollection("projects/earth-engine-071095/assets/Clark_Labs/WCS_Congo/DRC_Community_Forests"),
        'gc': ee.FeatureCollection("projects/ee-madibipacifique/assets/Green_Corridor_DRC"),
        'oil': ee.FeatureCollection("projects/ee-madibipacifique/assets/Bloc_petrolier")
    }
