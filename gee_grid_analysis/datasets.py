
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
        'esa_agb': ee.Image("projects/sat-io/open-datasets/ESA/ESA_CCI_AGB/CCI_BIOMASS_100m_AGB_2021_V6").clip(grid).select('AGB'),
        'gsoc': ee.Image("projects/earth-engine-071095/assets/Clark_Labs/WCS_Congo/GSOC_MAP_1-5-0").clip(grid),
        'flii': ee.Image("projects/flii-pipeline/assets/final_metric/FLII_final_metric_300m_2022").clip(grid),
        'gcp_jung': ee.Image("projects/ee-madibipacifique/assets/jung").clip(grid),
        'gcp_dinerstein': ee.Image("projects/ee-madibipacifique/assets/Dinesrtein").clip(grid),
        'esp': ee.Image("projects/ee-madibipacifique/assets/ncp").unmask().clip(grid),
        'climate': ee.Image("projects/ee-madibipacifique/assets/ClimateVulnerability_VF").clip(grid).select('b4'),
        'pa': ee.FeatureCollection("projects/earth-engine-071095/assets/Clark_Labs/WCS_Congo/DRC_Protected_Areas"),
        'kba': ee.FeatureCollection("projects/earth-engine-071095/assets/Clark_Labs/WCS_Congo/DRC_Key_Biodiversity_Areas"),
        'cf': ee.FeatureCollection("projects/earth-engine-071095/assets/Clark_Labs/WCS_Congo/DRC_Community_Forests"),
        'gc': ee.FeatureCollection("projects/ee-madibipacifique/assets/Green_Corridor_DRC"),
        'oil': ee.FeatureCollection("projects/ee-madibipacifique/assets/Bloc_petrolier"),
        'peat_thickness': ee.Image("projects/ee-pelsen-wcs/assets/ROC/Forest_properties/Crezee_2022_Median_Peat_thickness_RF_100runs").clip(grid),
        'human_impact_index': ee.Image("projects/ee-pelsen-wcs/assets/ROC/Forest_properties/hii_roc_clip_2020").clip(grid),
        'global_human_modification': ee.Image(ee.ImageCollection("CSP/HM/GlobalHumanModification").first()).clip(grid),
        'anthropogenic_pressure': ee.Image("projects/ee-madibipacifique/assets/Anthropogenicpressure").clip(grid),
        'nat_semi_grassland': ee.Image("projects/global-pasture-watch/assets/ggc-30m/v1/nat-semi-grassland_p/2022").clip(grid),
        'peat_carbon': ee.Image("projects/ee-pelsen-wcs/assets/ROC/Forest_properties/Crezee_2022_Median_Carbon_density_2000runs").clip(grid),
        'forest_ecosystems': ee.Image("projects/ee-pelsen-wcs/assets/ROC/Ecosystems_ecoregions/Shapiro_ecosystems").clip(grid),
        'marine_pressure': ee.Image("users/pelsen_WCS/MCI/global_cumul_impact_2013_all_layers").clip(grid),
        'biomass_carbon': ee.ImageCollection("NASA/ORNL/biomass_carbon_density/v1").mean().clip(grid)
    }
