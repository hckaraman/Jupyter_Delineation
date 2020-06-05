import os
import pandas as pd
from shapely.geometry import mapping, Polygon
import fiona
import geopandas as gpd
from shapely.geometry import Point
import whitebox
import rasterio
from osgeo import osr
from rasterio.features import shapes as shp

wbt = whitebox.WhiteboxTools()
wbt.set_verbose_mode(False)


# start_time = datetime.datetime.now()


def bbox(lat, lng, margin):
    return Polygon([[lng - margin, lat - margin], [lng - margin, lat + margin],
                    [lng + margin, lat + margin], [lng + margin, lat - margin]])


def bound(x, y, margin, name, folder):
    target_epsg = 4326
    dst_file = os.path.join(folder, name)
    poly = bbox(x, y, margin)

    schema = {
        'geometry': 'Polygon',
        'properties': {'id': 'int'},
    }

    with fiona.open(dst_file, 'w', 'ESRI Shapefile', schema) as c:
        ## If there are multiple geometries, put the "for" loop here
        c.write({
            'geometry': mapping(poly),
            'properties': {'id': 123},
        })

    sr = osr.SpatialReference()
    sr.ImportFromEPSG(target_epsg)
    sr.MorphToESRI()
    with open(dst_file.replace('.shp', '.prj'), 'w') as prj:
        prj.write(sr.ExportToWkt())


def crop_raster(bbox_file, dem, dem_out):
    wbt.clip_raster_to_polygon(
        dem,
        bbox_file,
        dem_out,
        maintain_dimensions=False,
    )


def create_point(x, y, point_file, path):
    point_geom = Point(float(x), float(y))
    point = gpd.GeoDataFrame(
        index=[0], crs='epsg:4326', geometry=[point_geom])
    point.to_file(filename=os.path.join(
        path, point_file), driver="ESRI Shapefile")


def process(dem, point_file, snap_dist=0.05, threshold=3):
    wbt.breach_depressions(dem, "DEM_breach.tif")
    wbt.fill_depressions("DEM_breach.tif", "DEM_fill.tif")
    wbt.flow_accumulation_full_workflow(
        "DEM_fill.tif", "DEM_out.tif", "Flow_dir.tif", "Flow_acc.tif", log=False)
    wbt.extract_streams("Flow_acc.tif", "streams.tif", threshold=threshold)
    wbt.raster_streams_to_vector(
        "streams.tif", "Flow_dir.tif", "river.shp")

    wbt.snap_pour_points(point_file, "Flow_acc.tif",
                         "snap_point.shp", snap_dist=snap_dist)
    wbt.watershed("Flow_dir.tif", "snap_point.shp", "Watershed.tif")


def rastertopolygon(raster, polygon, folder):
    mask = None
    with rasterio.open(os.path.join(folder, "Watershed.tif")) as src:
        image = src.read(1)  # first band
        results = (
            {'properties': {'raster_val': v}, 'geometry': s}
            for i, (s, v)
            in enumerate(
            shp(image, mask=mask, transform=src.transform)))

    geoms = list(results)
    boundary = shp(geoms[0]['geometry'])
    gpd_polygonized_raster = gpd.GeoDataFrame.from_features(geoms)
    # Filter nodata value
    gpd_polygonized_raster = gpd_polygonized_raster[gpd_polygonized_raster['raster_val'] == 1]
    gpd_polygonized_raster.crs = "EPSG:4326"

    # gpd_polygonized_raster = gpd_polygonized_raster.to_crs(
    #     'epsg:4326')  # world.to_crs(epsg=3395) would also work
    gpd_polygonized_raster.to_file(
        driver='ESRI Shapefile', filename=os.path.join(folder, polygon))
    gpd_polygonized_raster.to_file(os.path.join(folder, 'basin_boundary.geojson'), driver='GeoJSON')
    myshpfile = gpd.read_file(os.path.join(folder, 'river.shp'))
    myshpfile.to_file(os.path.join(folder, 'river.geojson'), driver='GeoJSON')


def run(x, y, margin, treshold, snap_dist):
    path = '/home/cak/Desktop/Jupyter_Delineation/Data/DEM'
    wbt.work_dir = path
    bbox_file = 'box.shp'
    dem_file = 'DEM_90m.tif'
    dem_crop = 'DEM_clipped.tif'
    point_file = 'point.shp'
    basin_bound_file = 'basin_boundary.shp'
    bound(x, y, margin, bbox_file, path)
    crop_raster(bbox_file, dem_file, dem_crop)
    create_point(x, y, point_file, path)
    process(dem_crop, point_file, snap_dist=snap_dist, threshold=treshold)
    rastertopolygon("Watershed.tif", basin_bound_file, path)


if __name__ == '__main__':
    # lat,lon
    x, y = 40, 31
    margin = 0.25
    treshold = 2
    snap_dist = 0.05
    run(x, y, margin, treshold, snap_dist)
