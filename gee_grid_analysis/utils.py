
import ee

def get_image_stats(image, grid, projection, property_name, scale):
    fractions = image.reduceRegions(
        collection=grid,
        reducer=ee.Reducer.mean(),
        scale=scale,
        crs=projection
    )
    return fractions.map(lambda f: f.set(property_name, f.get('mean')))

def export_table(feature_collection, description, folder, selectors):
    task = ee.batch.Export.table.toDrive(
        collection=feature_collection,
        description=description,
        folder=folder,
        fileFormat='CSV',
        selectors=selectors
    )
    task.start()
