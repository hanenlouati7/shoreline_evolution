#!/usr/bin/env python3
# =========================================================
# Flood Depth Visualization - Static Maps with Python
# =========================================================

import os
import sys
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import BoundaryNorm, ListedColormap
import rasterio
from rasterio.plot import show
import geopandas as gpd
import warnings
from pyproj import Transformer
from matplotlib.ticker import FuncFormatter
warnings.filterwarnings('ignore')

# =========================================================
# CONFIGURATION
# =========================================================

OSM_BACKGROUND = "/Users/hlouati/Library/CloudStorage/Dropbox-CMCC/hanen louati/shoreline_evolution/osm/osm_7792.tif"
LECCE_ROADS = "/Users/hlouati/Library/CloudStorage/Dropbox-CMCC/hanen louati/shoreline_evolution/backgound_files/lecce_roads.shp"

FLOOD_DIR = "/Users/hlouati/Desktop/ESL"
OUTPUT_DIR = "/Users/hlouati/Desktop/ESL/flood_maps_python"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# =========================================================
# VISUALIZATION PARAMETERS
# =========================================================

DEPTH_BINS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 2.0]

DEPTH_COLORS = [
    '#f7fbff', '#eff8ff', '#deebf7', '#c6dbef', '#9ecae1',
    '#6baed6', '#4292c6', '#2171b5', '#08519c', '#08306b', '#041e5e'
]

FLOOD_OPACITY = 0.6
ROADS_OPACITY = 0.6
ROADS_COLOR = 'gray'
ROADS_LINEWIDTH = 0.5

DPI = 300
FIGSIZE = (16, 12)

TITLE_FONTSIZE = 20
LABEL_FONTSIZE = 14
LEGEND_FONTSIZE = 14

# =========================================================
# LOCATION POINTS
# =========================================================

LOCATIONS = {
    "Torre Chianca": (18.200761298918547, 40.46193515580539),
"Torre Rinalda": (18.157135322761643, 40.48219021937831),
"Frigole": (18.242426463650784, 40.42524239321438),
"Acquatina": (18.236891846566042, 40.4438667811714),
"Idume": (18.186394748512967, 40.46723804789989)
}

LOCATION_MARKER = "o"
LOCATION_SIZE = 50
LOCATION_COLOR = "red"
LOCATION_TEXT_SIZE = 11


TARGET_YEARS = [2020, 2040, 2060, 2080]
SCENARIOS = ["SSP245", "SSP585"]

VARIABLES = ["rl_10yr", "rl_50yr", "rl_100yr"]

VARIABLE_FOLDERS = {
    "rl_10yr": "rl10",
    "rl_50yr": "rl50",
    "rl_100yr": "rl100"
}

MODES = ["FULL"]

# =========================================================
# HELPER FUNCTIONS
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

    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)

    print(f"  ✓ Figure created: {FIGSIZE} at {DPI} DPI")

    print(f"  ✓ Plotting OSM background...")
    with rasterio.open(OSM_BACKGROUND) as src:
        show(src, ax=ax, alpha=0.4)

    if roads_gdf is not None:
        try:
            print(f"  ✓ Plotting roads...")
            roads_gdf.plot(ax=ax, color=ROADS_COLOR,
                           linewidth=ROADS_LINEWIDTH,
                           alpha=ROADS_OPACITY, zorder=2)
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

    for name, (lon, lat) in LOCATIONS.items():

        x, y = transformer_points.transform(lon, lat)

        ax.scatter(
            x,
            y,
            s=LOCATION_SIZE,
            marker=LOCATION_MARKER,
            color=LOCATION_COLOR,
            edgecolor="black",
            linewidth=0.8,
            zorder=5
        )

        ax.text(
            x,
            y,
            f"  {name}",
            fontsize=LOCATION_TEXT_SIZE,
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
        alpha=FLOOD_OPACITY,
        extent=[
            flood_bounds.left,
            flood_bounds.right,
            flood_bounds.bottom,
            flood_bounds.top
        ],
        origin="upper",
        zorder=3
    )

    ax.set_title(title, fontsize=TITLE_FONTSIZE, fontweight='bold')
    ax.set_xlabel('Longitude (degE)', fontsize=LABEL_FONTSIZE)
    ax.set_ylabel('Latitude (degN)', fontsize=LABEL_FONTSIZE)
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
              fontsize=LEGEND_FONTSIZE,
              title='Flood Depth [m]')

    ax.grid(True, alpha=0.3, linestyle='--')
    plt.tight_layout()

    plt.savefig(output_path, dpi=DPI, bbox_inches='tight')
    print(f"✅ Saved: {output_path}")
    plt.close()


# =========================================================
# MAIN PROCESSING
# =========================================================

def process_all_scenarios():

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

    OUTPUT_GROUP = {
        "advanced_depth_cost": "with_damping"
    }

    for depth_type in OUTPUT_GROUP.keys():

        for scen in SCENARIOS:
            scen_lower = scen.lower()

            for var in VARIABLES:
                folder = VARIABLE_FOLDERS[var]

                for year in TARGET_YEARS:
                    for mode in MODES:

                        base = f"base_{scen}_{var.replace('_','')}_{year}"
                        raster_name = f"{mode}_{base}_{depth_type}"

                        # =================================================
                        # INPUT PATH (FIXED: NO damping folders)
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
                            f"{scen} - {var.upper()} - {year} - {depth_type}"
                        )

                        # =================================================
                        # OUTPUT PATH (WITH damping hierarchy)
                        # =================================================
                        output_folder = os.path.join(
                            OUTPUT_DIR,
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
# RUN
# =========================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🌊 FLOOD DEPTH VISUALIZATION - PYTHON STATIC MAPS")
    print("="*60)

    process_all_scenarios()

    print("\n" + "="*60)
    print("✅ ALL VISUALIZATIONS COMPLETED")
    print("="*60)