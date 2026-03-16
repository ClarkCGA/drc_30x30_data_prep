
import ee

def load_grid_and_projection():
    grid = ee.FeatureCollection("projects/earth-engine-071095/assets/Clark_Labs/WCS_Congo/drc_1km_grid_reference_poly_final")
    grid_raster = ee.Image("projects/earth-engine-071095/assets/Clark_Labs/WCS_Congo/drc_1km_grid_reference_drc_mercator")
    projection = grid_raster.projection()
    return grid, projection

def load_gen_datasets(grid):
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
        'biomass_carbon': ee.ImageCollection("NASA/ORNL/biomass_carbon_density/v1").mean().clip(grid),
        'basin': ee.FeatureCollection("projects/earth-engine-071095/assets/Clark_Labs/WCS_Congo/Congo_BasinATLAS_v10_lev12"),
        'recharge': ee.Image("projects/earth-engine-071095/assets/Clark_Labs/WCS_Congo/Africa_recharge").clip(grid),
        'lake_wetland': ee.Image("projects/earth-engine-071095/assets/Clark_Labs/WCS_Congo/GLWD_v2_0_main_class").clip(grid),
        'river_network': ee.FeatureCollection("projects/earth-engine-071095/assets/Clark_Labs/WCS_Congo/congo_river_network"),
        'birds': ee.FeatureCollection("projects/earth-engine-071095/assets/Clark_Labs/WCS_Congo/congo_bird_species_range_all")
    }


def load_iucn_datasets():
    base = "projects/earth-engine-071095/assets/Clark_Labs/WCS_Congo/IUCN_Threatened_Species/"

    def fc(name):
        return ee.FeatureCollection(base + name)

    amphibians = fc("Congo_AMPHIBIANS_PART1").merge(fc("Congo_AMPHIBIANS_PART2"))
    fw_fish = fc("Congo_FW_FISH_PART1").merge(fc("Congo_FW_FISH_PART2")).merge(fc("Congo_FW_FISH_PART3"))
    fw_other = (fc("Congo_FW_OTHER_PART1").merge(fc("Congo_FW_OTHER_PART2"))
                .merge(fc("Congo_FW_OTHER_PART3")).merge(fc("Congo_FW_OTHER_PART4")))
    fw_plants = fc("Congo_FW_PLANTS_PART1").merge(fc("Congo_FW_PLANTS_PART2"))
    reptiles = fc("Congo_REPTILES_PART1").merge(fc("Congo_REPTILES_PART2"))

    return {
        'amphibians': amphibians,
        'fw_crabs': fc("Congo_FW_CRABS"),
        'fw_crayfish': fc("Congo_FW_CRAYFISH"),
        'fw_fish': fw_fish,
        'fw_molluscs': fc("Congo_FW_MOLLUSCS"),
        'fw_odonata': fc("Congo_FW_ODONATA"),
        'fw_other': fw_other,
        'fw_plants': fw_plants,
        'fw_shrimps': fc("Congo_FW_SHRIMPS"),
        'reptiles': reptiles,
    }
