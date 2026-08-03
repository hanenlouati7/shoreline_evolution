#!/usr/bin/env python3
# =========================================================
# Flood Depth Visualization - Combined Script
#   Part A: Full-extent static maps (OSM raster background + roads)
#   Part B: Zoomed ROI maps (OSM tiled basemap via contextily)
# =========================================================
#
# Both parts share the same TAG / FLOOD_DIR convention as the GRASS
# workflow script (main_esl.sh). Run this file directly to generate
# BOTH the full-extent maps and the zoomed ROI maps, one after another.

import os
import sys
import numpy as np
import numpy.ma as ma
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.ticker import FuncFormatter
import rasterio
from rasterio.plot import show
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds
import geopandas as gpd
import contextily as ctx
from pyproj import Transformer
import warnings
warnings.filterwarnings('ignore')

# =========================================================
# SHARED CONFIGURATION (used by both Part A and Part B)
# =========================================================

# NOTE: this must match the TAG used in the GRASS/bash workflow script
# (main_esl.sh), since that's what determines both the input folder name
# and the raster/file naming pattern (e.g. base_esl_<TAG>_<SCEN>_<VAR>_<YEAR>).
TAG = "tsl_corr36_7cm"

# --- Shared input path ---
# Root folder holding all exported GeoTIFFs from the GRASS workflow.
# Must match EXPORT_DIR in main_esl.sh.
FLOOD_DIR = f"/Volumes/WD/ESL_{TAG}"

# Shared depth classification (identical in both original scripts)
DEPTH_BINS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 2.0]
DEPTH_COLORS = [
    '#f7fbff', '#eff8ff', '#deebf7', '#c6dbef', '#9ecae1',
    '#6baed6', '#4292c6', '#2171b5', '#08519c', '#08306b', '#041e5e'
]

# Shared output grouping logic (which depth-type folder to export into)
OUTPUT_GROUP = {
    "advanced_depth_cost": "with_damping"
}

SCENARIOS = ["SSP245", "SSP585"]
TARGET_YEARS = [2020, 2040, 2060, 2080]


# =========================================================
# PART A CONFIGURATION - FULL-EXTENT MAPS
# =========================================================

# --- Input paths (Part A only) ---
# Background OSM raster and roads shapefile used behind the full-extent maps.
# Update these if the files move or you're running on a different machine.
OSM_BACKGROUND = "/Users/hlouati/Library/CloudStorage/Dropbox-CMCC/hanen louati/shoreline_evolution/osm/osm_7792.tif"
LECCE_ROADS = "/Users/hlouati/Library/CloudStorage/Dropbox-CMCC/hanen louati/shoreline_evolution/backgound_files/lecce_roads.shp"

# --- Output path (Part A only) ---
# Full-extent PNGs are written here, tagged so different runs don't overwrite each other.
FULL_OUTPUT_DIR = f"/Volumes/WD/ESL_{TAG}/flood_maps_python"
os.makedirs(FULL_OUTPUT_DIR, exist_ok=True)

FULL_FLOOD_OPACITY = 0.6
FULL_ROADS_OPACITY = 0.6
FULL_ROADS_COLOR = 'gray'
FULL_ROADS_LINEWIDTH = 0.5

FULL_DPI = 300
FULL_FIGSIZE = (16, 12)

FULL_TITLE_FONTSIZE = 20
FULL_LABEL_FONTSIZE = 14
FULL_LEGEND_FONTSIZE = 14

# Named locations plotted as markers on the full-extent maps
FULL_LOCATIONS = {
    "Torre Chianca": (18.200761298918547, 40.46193515580539),
    "Torre Rinalda": (18.157135322761643, 40.48219021937831),
    "Frigole": (18.242426463650784, 40.42524239321438),
    "Acquatina": (18.236891846566042, 40.4438667811714),
    "Idume": (18.186394748512967, 40.46723804789989)
}

FULL_LOCATION_MARKER = "o"
FULL_LOCATION_SIZE = 50
FULL_LOCATION_COLOR = "red"
FULL_LOCATION_TEXT_SIZE = 11

FULL_VARIABLES = ["rl_10yr", "rl_50yr", "rl_100yr"]
FULL_VARIABLE_FOLDERS = {
    "rl_10yr": "rl10",
    "rl_50yr": "rl50",
    "rl_100yr": "rl100"
}

FULL_MODES = ["FULL", "ROUGH", "SLOPE", "DISTANCE"]


# =========================================================
# PART B CONFIGURATION - ZOOM / ROI MAPS
# =========================================================

# --- Output path (Part B only) ---
# Zoomed ROI PNGs are written here (separate folder from the full-extent maps).
ZOOM_OUTPUT_DIR = f"/Volumes/WD/ESL_{TAG}/flood_maps_python_zoom"
os.makedirs(ZOOM_OUTPUT_DIR, exist_ok=True)

# Regions of interest, in EPSG:7792 coordinates, used to crop each raster before plotting
ROIS = {
    "ROI_1": {
        "xmin": 769148.5586592179,
        "xmax": 770497.7206703911,
        "ymin": 4483980.92670618,
        "ymax": 4485283.636871509
    },
    "ROI_2": {
        "xmin": 774639.0614525140,
        "xmax": 776646.3663238430,
        "ymin": 4479662.30713602,
        "ymax": 4481236.15083799
    }
}
ROI_LABELS = {
    "ROI_1": "Idume",
    "ROI_2": "Frigole"
}

# Named locations plotted as markers on the zoom maps (subset relevant to the ROIs above)
ZOOM_LOCATIONS = {
    "Frigole": (18.242426463650784, 40.42524239321438),
    "Idume": (18.186394748512967, 40.46723804789989)
}

ZOOM_VARIABLES = ["rl10", "rl50", "rl100"]
ZOOM_MODES = ["FULL"]
ZOOM_DEPTH_TYPES = ["advanced_depth_cost"]

ZOOM_FLOOD_OPACITY = 0.65
ZOOM_DPI = 300
ZOOM_FIGSIZE = (12, 10)


# =========================================================
# PART A - HELPER FUNCTIONS (full-extent maps)
# =========================================================

def load_raster(filepath):
    try:
        print(f"  🔍 DEBUG: Loading raster from: {filepath}")
        with rasterio.open(filepath) as src:
            data = src.read(1)
            meta = src.meta
            bounds = src.bounds
            transform = src.transform

            print(f"     ✓ Shape: {data.shape}")
            print(f"     ✓ Data type: {data.dtype}")
            print(f"     ✓ Min value: {np.nanmin(data):.4f}, Max value: {np.nanmax(data):.4f}")
            print(f"     ✓ NaN count: {np.isnan(data).sum()}")
            print(f"     ✓ Bounds: {bounds}")
            print(f"     ✓ CRS: {src.crs}")

            return data, meta, bounds, transform

    except Exception as e:
        print(f"  ❌ DEBUG: Error loading {filepath}: {e}")
        return None, None, None, None


def create_discrete_colormap(bins, colors):
    print(f"  🔍 DEBUG: Creating colormap")
    cmap = ListedColormap(colors)
    norm = BoundaryNorm(bins, len(colors))
    return cmap, norm


def plot_flood_map(osm_data, osm_transform, osm_bounds,
                   flood_data, flood_transform, flood_bounds,
                   cmap, norm, title, output_path, roads_gdf=None):

    print(f"  🔍 DEBUG: Creating flood map")
    print(f"     ✓ Title: {title}")
    print(f"     ✓ Output: {output_path}")
    print(f"     ✓ Flood data shape: {flood_data.shape}")
    print(f"     ✓ Roads available: {roads_gdf is not None}")

    fig, ax = plt.subplots(figsize=FULL_FIGSIZE, dpi=FULL_DPI)

    print(f"  ✓ Figure created: {FULL_FIGSIZE} at {FULL_DPI} DPI")

    print(f"  ✓ Plotting OSM background...")
    # --- Input path used here: OSM_BACKGROUND (raster basemap) ---
    with rasterio.open(OSM_BACKGROUND) as src:
        show(src, ax=ax, alpha=0.4)

    if roads_gdf is not None:
        try:
            print(f"  ✓ Plotting roads...")
            roads_gdf.plot(ax=ax, color=FULL_ROADS_COLOR,
                           linewidth=FULL_ROADS_LINEWIDTH,
                           alpha=FULL_ROADS_OPACITY, zorder=2)
        except Exception as e:
            print(f"  ⚠️ DEBUG roads error: {e}")
    # =====================================================
    # PLOT LOCATION POINTS
    # =====================================================

    transformer_points = Transformer.from_crs(
        "EPSG:4326",
        "EPSG:7792",
        always_xy=True
    )

    for name, (lon, lat) in FULL_LOCATIONS.items():

        x, y = transformer_points.transform(lon, lat)

        ax.scatter(
            x,
            y,
            s=FULL_LOCATION_SIZE,
            marker=FULL_LOCATION_MARKER,
            color=FULL_LOCATION_COLOR,
            edgecolor="black",
            linewidth=0.8,
            zorder=5
        )

        ax.text(
            x,
            y,
            f"  {name}",
            fontsize=FULL_LOCATION_TEXT_SIZE,
            zorder=6,
            ha="left",
            va="center",
            fontweight="bold"
        )

    ########################################    
    print(f"  ✓ Plotting flood layer...")
    flood_data = np.ma.masked_where(flood_data == 0, flood_data)

    ax.imshow(
        flood_data,
        cmap=cmap,
        norm=norm,
        alpha=FULL_FLOOD_OPACITY,
        extent=[
            flood_bounds.left,
            flood_bounds.right,
            flood_bounds.bottom,
            flood_bounds.top
        ],
        origin="upper",
        zorder=3
    )

    ax.set_title(title, fontsize=FULL_TITLE_FONTSIZE, fontweight='bold')
    ax.set_xlabel('Longitude (degE)', fontsize=FULL_LABEL_FONTSIZE)
    ax.set_ylabel('Latitude (degN)', fontsize=FULL_LABEL_FONTSIZE)
    # =====================================================
    # FORMAT AXIS LABELS AS DEGREES (WITHOUT REPROJECTING)
    # =====================================================

    transformer = Transformer.from_crs(
    "EPSG:7792",
    "EPSG:4326",
    always_xy=True)

    center_x = (flood_bounds.left + flood_bounds.right) / 2
    center_y = (flood_bounds.bottom + flood_bounds.top) / 2


    def format_lon(x, pos):
        lon, _ = transformer.transform(x, center_y)
        return f"{lon:.3f}°"


    def format_lat(y, pos):
        _, lat = transformer.transform(center_x, y)
        return f"{lat:.3f}°"

    ax.xaxis.set_major_formatter(FuncFormatter(format_lon))
    ax.yaxis.set_major_formatter(FuncFormatter(format_lat))


    # =====================================================
    # LEGEND (UNCHANGED -
    # =====================================================
    legend_labels = []
    for i, (lower, upper) in enumerate(zip(DEPTH_BINS[:-1], DEPTH_BINS[1:])):
        legend_labels.append(
            mpatches.Patch(color=DEPTH_COLORS[i],
                           label=f"{lower:.2f} - {upper:.2f} m")
        )


    ax.legend(handles=legend_labels,
              loc='upper right',
              fontsize=FULL_LEGEND_FONTSIZE,
              title='Flood Depth [m]')

    ax.grid(True, alpha=0.3, linestyle='--')
    plt.tight_layout()

    plt.savefig(output_path, dpi=FULL_DPI, bbox_inches='tight')
    print(f"✅ Saved: {output_path}")
    plt.close()


def process_all_scenarios():
    """PART A entry point: generate full-extent flood maps for every
    scenario / variable / year / mode combination."""

    print("\n📍 Loading OSM background:", OSM_BACKGROUND)
    osm_data, osm_meta, osm_bounds, osm_transform = load_raster(OSM_BACKGROUND)

    print("\n🛣️ Loading roads:", LECCE_ROADS)
    try:
        roads_gdf = gpd.read_file(LECCE_ROADS)
        print(f"✅ Roads loaded: {len(roads_gdf)} features")
    except Exception as e:
        print(f"⚠️ Could not load roads: {e}")
        roads_gdf = None

    cmap, norm = create_discrete_colormap(DEPTH_BINS, DEPTH_COLORS)

    # =========================================================
    # OUTPUT STRUCTURE ONLY (NOT INPUT)
    # =========================================================

    for depth_type in OUTPUT_GROUP.keys():

        for scen in SCENARIOS:
            scen_lower = scen.lower()

            for var in FULL_VARIABLES:
                folder = FULL_VARIABLE_FOLDERS[var]

                for year in TARGET_YEARS:
                    for mode in FULL_MODES:

                        # NOTE: raster naming now includes TAG, matching the
                        # bash script's BASE="base_esl_${TAG}_${SCEN}_${VAR//_/}_${YEAR}"
                        base = f"base_esl_{TAG}_{scen}_{var.replace('_','')}_{year}"
                        raster_name = f"{mode}_{base}_{depth_type}"

                        # =================================================
                        # INPUT PATH (under FLOOD_DIR = ESL_<TAG>, from main_esl.sh)
                        # =================================================
                        raster_path = os.path.join(
                            FLOOD_DIR,
                            f"projection_{scen_lower}",
                            folder,
                            f"{raster_name}.tif"
                        )

                        if not os.path.exists(raster_path):
                            print(f"⚠️ Missing: {raster_path}")
                            continue

                        print(f"\n📊 Processing: {raster_name}")

                        flood_data, _, flood_bounds, _ = load_raster(raster_path)

                        if flood_data is None:
                            continue

                        flood_data = np.nan_to_num(flood_data, nan=0.0)

                        title = (
                            f"Flood Depth Map\n"
                            f"{scen} - {var.upper()} - {year} - {depth_type} - {TAG}"
                        )

                        # =================================================
                        # OUTPUT PATH (under tagged FULL_OUTPUT_DIR)
                        # =================================================
                        output_folder = os.path.join(
                            FULL_OUTPUT_DIR,
                            OUTPUT_GROUP[depth_type],
                            f"projection_{scen_lower}",
                            folder
                        )

                        os.makedirs(output_folder, exist_ok=True)

                        output_path = os.path.join(
                            output_folder,
                            f"{raster_name}_visualization.png"
                        )

                        plot_flood_map(
                            osm_data, osm_transform, osm_bounds,
                            flood_data, None, flood_bounds,
                            cmap, norm,
                            title,
                            output_path,
                            roads_gdf
                        )


# =========================================================
# PART B - HELPER FUNCTIONS (zoom / ROI maps)
# =========================================================

def load_raster_roi(path, roi):

    print(f"🔍 Loading: {path}")

    with rasterio.open(path) as src:

        window = from_bounds(
            roi["xmin"], roi["ymin"],
            roi["xmax"], roi["ymax"],
            transform=src.transform
        )

        data = src.read(1, window=window)
        bounds = rasterio.windows.bounds(window, src.transform)

        print(f"   ✓ shape: {data.shape}")
        print(f"   ✓ bounds: {bounds}")

        return data, bounds


def create_cmap():
    cmap = ListedColormap(DEPTH_COLORS)
    norm = BoundaryNorm(DEPTH_BINS, len(DEPTH_COLORS))
    return cmap, norm


def plot_map(data, bounds_7792, title, output_path, cmap, norm):

    fig, ax = plt.subplots(figsize=ZOOM_FIGSIZE, dpi=ZOOM_DPI)
    left, bottom, right, top = bounds_7792

    center_x = (left + right) / 2
    center_y = (bottom + top) / 2

    transformer_axis = Transformer.from_crs(
        "EPSG:7792",
        "EPSG:4326",
        always_xy=True
    )

    def format_lon(x, pos):
        lon, _ = transformer_axis.transform(x, center_y)
        return f"{lon:.3f}°"

    def format_lat(y, pos):
        _, lat = transformer_axis.transform(center_x, y)
        return f"{lat:.3f}°"

        

    ax.imshow(
        data,
        cmap=cmap,
        norm=norm,
        extent=[left, right, bottom, top],
        origin="upper",
        alpha=ZOOM_FLOOD_OPACITY,
        zorder=2
    )

    ax.set_xlim(left, right)
    ax.set_ylim(bottom, top)

    

    ax.xaxis.set_major_formatter(FuncFormatter(format_lon))
    ax.yaxis.set_major_formatter(FuncFormatter(format_lat))

    ax.set_xlabel("Longitude(degE)")
    ax.set_ylabel("Latitude(degN)")

    # -----------------------------------------------------
    # OSM basemap (correct CRS) - fetched live via contextily tiles,
    # not from a local file like Part A's OSM_BACKGROUND.
    # -----------------------------------------------------
    ctx.add_basemap(
        ax,
        crs="EPSG:7792", 
        source=ctx.providers.OpenStreetMap.Mapnik,
        zoom=18,
        zorder=1,
        alpha=0.4

    )
        # -----------------------------------------------------
    # LOCATION POINTS
    # -----------------------------------------------------
    to_7792 = Transformer.from_crs("EPSG:4326", "EPSG:7792", always_xy=True)

    for name, (lon, lat) in ZOOM_LOCATIONS.items():
        x, y = to_7792.transform(lon, lat)

        ax.scatter(
            x, y,
            s=60,
            color="red",
            edgecolor="black",
            linewidth=0.8,
            zorder=5
        )

        ax.text(
            x, y,
            f" {name}",
            fontsize=10,
            color="black",
            zorder=6,
            va="center"
        )
    # -----------------------------------------------------
    # Legend
    # -----------------------------------------------------
    legend = [
        mpatches.Patch(
            color=DEPTH_COLORS[i],
            label=f"{DEPTH_BINS[i]}–{DEPTH_BINS[i+1]} m"
        )
        for i in range(len(DEPTH_BINS) - 1)
    ]
    ax.legend(
    handles=legend,
    loc="upper right",
    fontsize=13,
    title="Flood depth (m)",
    title_fontsize=14,
    frameon=True,
    framealpha=0.9,
    borderpad=0.8,
    labelspacing=0.4)

    ax.set_title(title)

    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()

    print(f"✅ Saved: {output_path}")


def run():
    """PART B entry point: generate zoomed ROI flood maps for every
    scenario / variable / year / mode / ROI combination."""

    cmap, norm = create_cmap()

    total = len(SCENARIOS) * len(ZOOM_VARIABLES) * len(TARGET_YEARS) * len(ZOOM_MODES) * len(ZOOM_DEPTH_TYPES) * len(ROIS)
    count = 0

    for scen in SCENARIOS:
        for var in ZOOM_VARIABLES:
            for year in TARGET_YEARS:
                for mode in ZOOM_MODES:
                    for depth_type in ZOOM_DEPTH_TYPES:

                        # -------------------------------------------------
                        # FILE NAME (matches your real dataset, with TAG)
                        # -------------------------------------------------
                        base = f"base_esl_{TAG}_{scen}_{var.replace('_','')}yr_{year}"
                        raster_name = f"{mode}_{base}_{depth_type}"

                        # =================================================
                        # INPUT PATH (under FLOOD_DIR = ESL_<TAG>, from main_esl.sh)
                        # =================================================
                        raster_path = os.path.join(
                            FLOOD_DIR,
                            f"projection_{scen.lower()}",
                            var,
                            f"{raster_name}.tif"
                        )

                        if not os.path.exists(raster_path):
                            print(f"❌ Missing: {raster_path}")
                            continue

                        for roi_name, roi in ROIS.items():

                            count += 1
                            print(f"\n[{count}/{total}] {raster_name} | {roi_name}")

                            data, bounds = load_raster_roi(raster_path, roi)

                            data = np.ma.masked_where(data == 0, data)


                            # -------------------------------------------------
                            # OUTPUT PATH (under tagged ZOOM_OUTPUT_DIR, grouped by ROI)
                            # -------------------------------------------------
                            out_dir = os.path.join(
                                ZOOM_OUTPUT_DIR,
                                OUTPUT_GROUP[depth_type],
                                f"projection_{scen.lower()}",
                                var,
                                ROI_LABELS[roi_name]
                            )

                            os.makedirs(out_dir, exist_ok=True)

                            out_path = os.path.join(
                                out_dir,
                                f"{raster_name}_{ROI_LABELS[roi_name]}.png"
                            )

                            title = f"ESL (+36.7cm) |{scen} | {var} | {year} | {depth_type} | {ROI_LABELS[roi_name]}"

                            plot_map(
                                data,
                                bounds,
                                title,
                                out_path,
                                cmap,
                                norm
                            )


# =========================================================
# RUN - executes Part A (full-extent) then Part B (zoom/ROI)
# =========================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🌊 FLOOD DEPTH VISUALIZATION - PART A: FULL-EXTENT MAPS")
    print(f"   TAG: {TAG}")
    print("="*60)

    process_all_scenarios()

    print("\n" + "="*60)
    print("✅ PART A COMPLETED")
    print("="*60)

    print("\n==============================")
    print("ZOOM FLOOD MAPS + OSM + GROUPED OUTPUT - PART B")
    print("==============================\n")

    run()

    print("\nDONE - ALL VISUALIZATIONS COMPLETED (FULL + ZOOM)")