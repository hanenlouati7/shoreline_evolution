#!/usr/bin/env python3
# =========================================================
# Flood Depth Visualization - MSL Combined Script
#   Part A: Full-extent static maps (OSM raster background + roads)
#   Part B: Zoomed ROI maps (OSM tiled basemap via contextily)
# Variant: +36.7 cm vertical correction dataset (TAG=VLM_tsl_corr36_7cm)
# =========================================================
#
# Counterpart to plot.py (the ESL version). Matches the MSL GRASS
# workflow script (main_msl.sh) for TAG / FLOOD_DIR conventions.
# Run this file directly to generate BOTH the full-extent maps and
# the zoomed ROI maps, one after another.

import os
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

# Must match TAG in the MSL r.cost/flood-modeling shell script (main_msl.sh).
# NOTE: this TAG string differs slightly from the ESL scripts
# (here it's "VLM_tsl_corr36_7cm", vs "tsl_corr36_7cm" for ESL) - keep
# them in sync manually since they come from separate GRASS runs.
TAG = "VLM_tsl_corr36_7cm"

# --- Shared input path ---
# Root folder holding all exported MSL GeoTIFFs from the GRASS workflow.
# Must match EXPORT_DIR in main_msl.sh.
FLOOD_DIR = f"/Volumes/WD/MSL_{TAG}"

# Shared background files (same as the ESL plotting scripts)
OSM_BACKGROUND = "/Users/hlouati/Library/CloudStorage/Dropbox-CMCC/hanen louati/shoreline_evolution/osm/osm_7792.tif"
LECCE_ROADS = "/Users/hlouati/Library/CloudStorage/Dropbox-CMCC/hanen louati/shoreline_evolution/backgound_files/lecce_roads.shp"

FLOOD_OPACITY = 0.65
DPI = 300

TARGET_YEARS = [2020, 2040, 2060, 2080]
SCENARIOS = ["SSP245", "SSP585"]
MODES = ["FULL"]
DEPTH_TYPES = ["advanced_depth_cost"]


# =========================================================
# PART A CONFIGURATION - FULL-EXTENT MSL MAPS
# =========================================================

# --- Output path (Part A only) ---
FULL_OUTPUT_DIR = os.path.join(FLOOD_DIR, "flood_maps_python1_0")
os.makedirs(FULL_OUTPUT_DIR, exist_ok=True)

# --- Depth classification (Part A) ---
# Older color-scale attempts kept below for reference (not used) before
# settling on the current 11-bin scale.
"""DEPTH_BINS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]

DEPTH_COLORS = [
    '#c6dbef', '#9ecae1','#6baed6', '#4292c6', '#2171b5', '#08519c', '#08306b'
]
"""
"""
DEPTH_BINS = [0.0, 0.02, 0.04, 0.06, 0.08,0.1,0.12,0.14,0.16,0.18,0.2]
DEPTH_COLORS = [
    '#f7fbff', '#eff8ff', '#deebf7', '#c6dbef', '#9ecae1',
    '#6baed6', '#4292c6', '#2171b5', '#08519c', '#08306b'
]

"""
"""
DEPTH_BINS = [
    0.0, 0.025, 0.05, 0.075, 0.10, 0.125, 0.15, 0.175,
    0.20, 0.225, 0.25, 0.275, 0.30, 0.325, 0.35, 0.375, 0.40
]

DEPTH_COLORS = [
    '#f7fbff', '#eff8ff', '#deebf7', '#c6dbef',
    '#bdd7e7', '#9ecae1', '#7db8da', '#6baed6',
    '#5aa2cf', '#4292c6', '#3182bd', '#2171b5',
    '#1361a9', '#08519c', '#084594', '#08306b'
]

"""
"""
DEPTH_BINS = [
    0.0, 0.1, 0.2, 0.3, 0.4,
    0.5, 0.6, 0.7, 0.8, 0.9, 1.0
]

DEPTH_COLORS = [
    '#f7fbff', '#deebf7', '#c6dbef', '#9ecae1', '#6baed6',
    '#4292c6', '#2171b5', '#08519c', '#084594', '#06306b'
]

"""
FULL_DEPTH_BINS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 2.0]

FULL_DEPTH_COLORS = [
    '#f7fbff', '#eff8ff', '#deebf7', '#c6dbef', '#9ecae1',
    '#6baed6', '#4292c6', '#2171b5', '#08519c', '#08306b', '#041e5e'
]

FULL_ROADS_OPACITY = 0.6
FULL_ROADS_COLOR = 'gray'
FULL_ROADS_LINEWIDTH = 0.5

FULL_FIGSIZE = (16, 12)

FULL_TITLE_FONTSIZE = 20
FULL_LABEL_FONTSIZE = 14
FULL_LEGEND_FONTSIZE = 14

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
FULL_LOCATION_TEXT_SIZE = 10


# =========================================================
# PART B CONFIGURATION - ZOOM / ROI MSL MAPS
# =========================================================

# --- Output path (Part B only) ---
ZOOM_OUTPUT_DIR = os.path.join(FLOOD_DIR, "flood_maps_python_zoom")
os.makedirs(ZOOM_OUTPUT_DIR, exist_ok=True)

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

ZOOM_LOCATIONS = {
    "Frigole": (18.242426463650784, 40.42524239321438),
    "Idume": (18.186394748512967, 40.46723804789989)
}

# Output grouping logic (zoom maps only - full-extent script writes flat per-scenario folders)
OUTPUT_GROUP = {
    "advanced_depth_cost": "with_damping"
}

# --- Depth classification (Part B) ---
# Older color-scale attempts kept below for reference (not used).
"""
DEPTH_BINS = [0.0, 0.02, 0.04, 0.06, 0.08, 0.1, 0.12, 0.14, 0.16, 0.18, 0.2]
DEPTH_COLORS = [
    '#f7fbff', '#eff8ff', '#deebf7', '#c6dbef', '#9ecae1',
    '#6baed6', '#4292c6', '#2171b5', '#08519c', '#08306b'
]
"""
"""
DEPTH_BINS = [
    0.0, 0.025, 0.05, 0.075, 0.10, 0.125, 0.15, 0.175,
    0.20, 0.225, 0.25, 0.275, 0.30, 0.325, 0.35, 0.375, 0.40
]

DEPTH_COLORS = [
    '#f7fbff', '#eff8ff', '#deebf7', '#c6dbef',
    '#bdd7e7', '#9ecae1', '#7db8da', '#6baed6',
    '#5aa2cf', '#4292c6', '#3182bd', '#2171b5',
    '#1361a9', '#08519c', '#084594', '#08306b']
"""
"""
DEPTH_BINS = [
    0.0, 0.025, 0.05, 0.075, 0.10, 0.125, 0.15, 0.175,
    0.20, 0.225, 0.25, 0.275, 0.30, 0.325, 0.35, 0.375, 0.40
]

DEPTH_COLORS = [
    '#f7fbff', '#eff8ff', '#deebf7', '#c6dbef',
    '#bdd7e7', '#9ecae1', '#7db8da', '#6baed6',
    '#5aa2cf', '#4292c6', '#3182bd', '#2171b5',
    '#1361a9', '#08519c', '#084594', '#08306b'
]
"""

ZOOM_DEPTH_BINS = [
    0.0, 0.1, 0.2, 0.3, 0.4,
    0.5, 0.6, 0.7, 0.8, 0.9, 1.0
]

ZOOM_DEPTH_COLORS = [
    '#f7fbff', '#deebf7', '#c6dbef', '#9ecae1', '#6baed6',
    '#4292c6', '#2171b5', '#08519c', '#084594', '#08306b'
]

ZOOM_FIGSIZE = (12, 10)


# =========================================================
# PART A - HELPER FUNCTIONS (full-extent MSL maps)
# =========================================================

def load_raster(path):
    print(f"Loading: {path}")
    with rasterio.open(path) as src:
        data = src.read(1)
        bounds = src.bounds
        return data, bounds


def create_cmap_full():
    cmap = ListedColormap(FULL_DEPTH_COLORS)
    norm = BoundaryNorm(FULL_DEPTH_BINS, len(FULL_DEPTH_COLORS))
    return cmap, norm


def plot_map_full(data, bounds, title, out_path, cmap, norm, roads_gdf=None):

    fig, ax = plt.subplots(figsize=FULL_FIGSIZE, dpi=DPI)

    # ---------------- OSM ----------------
    # --- Input path used here: OSM_BACKGROUND (raster basemap) ---
    with rasterio.open(OSM_BACKGROUND) as src:
        show(src, ax=ax, alpha=0.4)

    # ---------------- ROADS ----------------
    if roads_gdf is not None:
        roads_gdf.plot(
            ax=ax,
            color=FULL_ROADS_COLOR,
            linewidth=FULL_ROADS_LINEWIDTH,
            alpha=FULL_ROADS_OPACITY,
            zorder=2
        )

    # ---------------- LOCATIONS ----------------
    transformer_points = Transformer.from_crs(
        "EPSG:4326",
        "EPSG:7792",
        always_xy=True
    )

    for name, (lon, lat) in FULL_LOCATIONS.items():
        x, y = transformer_points.transform(lon, lat)

        ax.scatter(
            x, y,
            s=FULL_LOCATION_SIZE,
            color=FULL_LOCATION_COLOR,
            edgecolor="black",
            zorder=5
        )

        ax.text(
            x, y,
            f" {name}",
            fontsize=FULL_LOCATION_TEXT_SIZE,
            va="center",
            zorder=6
        )

    # ---------------- FLOOD ----------------
    data = np.ma.masked_where(data == 0, data)


    ax.imshow(
        data,
        cmap=cmap,
        norm=norm,
        extent=[bounds.left, bounds.right, bounds.bottom, bounds.top],
        origin="upper",
        zorder=3
    )

    # ---------------- AXES ----------------
    ax.set_title(title, fontsize=FULL_TITLE_FONTSIZE, fontweight='bold')
    ax.set_xlabel("Longitude (degE)", fontsize=FULL_LABEL_FONTSIZE)
    ax.set_ylabel("Latitude (degN)", fontsize=FULL_LABEL_FONTSIZE)

    transformer_axis = Transformer.from_crs(
        "EPSG:7792",
        "EPSG:4326",
        always_xy=True
    )

    center_x = (bounds.left + bounds.right) / 2
    center_y = (bounds.bottom + bounds.top) / 2

    def format_lon(x, pos):
        lon, _ = transformer_axis.transform(x, center_y)
        return f"{lon:.3f}°"

    def format_lat(y, pos):
        _, lat = transformer_axis.transform(center_x, y)
        return f"{lat:.3f}°"

    ax.xaxis.set_major_formatter(FuncFormatter(format_lon))
    ax.yaxis.set_major_formatter(FuncFormatter(format_lat))

    # ---------------- LEGEND ----------------
    legend = []
    for i in range(len(FULL_DEPTH_BINS) - 1):
        legend.append(
            mpatches.Patch(
                color=FULL_DEPTH_COLORS[i],
                label=f"{FULL_DEPTH_BINS[i]}–{FULL_DEPTH_BINS[i+1]} m"
            )
        )

    ax.legend(handles=legend, loc="upper right", title=" Flood Depth [m]", fontsize=FULL_LEGEND_FONTSIZE)

    plt.tight_layout()
    plt.savefig(out_path, dpi=DPI, bbox_inches="tight")
    plt.close()

    print(f"Saved: {out_path}")


def run_full():
    """PART A entry point: generate full-extent MSL flood maps for every
    scenario / year combination."""

    cmap, norm = create_cmap_full()

    # --- Input path: roads shapefile ---
    try:
        roads_gdf = gpd.read_file(LECCE_ROADS)
    except:
        roads_gdf = None

    for scen in SCENARIOS:
        scen_l = scen.lower()

        for year in TARGET_YEARS:
            for mode in MODES:
                for depth_type in DEPTH_TYPES:

                    raster_name = f"{mode}_base_msl_{TAG}_{scen_l}_{year}_{depth_type}"

                    # =================================================
                    # INPUT PATH (under FLOOD_DIR = MSL_<TAG>, from main_msl.sh)
                    # =================================================
                    raster_path = os.path.join(
                        FLOOD_DIR,
                        f"projection_{scen_l}",
                        f"{raster_name}.tif"
                    )

                    if not os.path.exists(raster_path):
                        print(f"Missing: {raster_path}")
                        continue

                    data, bounds = load_raster(raster_path)

                    # =================================================
                    # OUTPUT PATH (under tagged FULL_OUTPUT_DIR)
                    # =================================================
                    out_dir = os.path.join(
                        FULL_OUTPUT_DIR,
                        f"projection_{scen_l}"
                    )
                    os.makedirs(out_dir, exist_ok=True)

                    out_path = os.path.join(out_dir, f"{raster_name}.png")

                    title = f"MSL (+36.7cm) | {scen} | {year} | {depth_type}"

                    plot_map_full(data, bounds, title, out_path, cmap, norm, roads_gdf)


# =========================================================
# PART B - HELPER FUNCTIONS (zoom / ROI MSL maps)
# =========================================================

def load_raster_roi(path, roi):

    print(f"🔍 Loading: {path}")

    if not os.path.exists(path):
        print(f"❌ Missing file: {path}")
        return None, None

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


def create_cmap_zoom():
    cmap = ListedColormap(ZOOM_DEPTH_COLORS)
    norm = BoundaryNorm(ZOOM_DEPTH_BINS, len(ZOOM_DEPTH_COLORS))
    return cmap, norm


def plot_map_zoom(data, bounds_7792, title, output_path, cmap, norm):
    fig, ax = plt.subplots(figsize=ZOOM_FIGSIZE, dpi=DPI)

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
        alpha=FLOOD_OPACITY,
        zorder=2
    )

    ax.set_xlim(left, right)
    ax.set_ylim(bottom, top)

    ax.xaxis.set_major_formatter(FuncFormatter(format_lon))
    ax.yaxis.set_major_formatter(FuncFormatter(format_lat))

    ax.set_xlabel("Longitude(degE)")
    ax.set_ylabel("Latitude(degN)")

    # -----------------------------------------------------
    # OSM basemap (fetched live via contextily tiles, not from
    # the local OSM_BACKGROUND file used in Part A)
    # -----------------------------------------------------
    ctx.add_basemap(
        ax,
        crs="EPSG:7792",
        source=ctx.providers.OpenStreetMap.Mapnik,
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

    # Legend
    legend = [
        mpatches.Patch(
            color=ZOOM_DEPTH_COLORS[i],
            label=f"{ZOOM_DEPTH_BINS[i]}–{ZOOM_DEPTH_BINS[i+1]} m"
        )
        for i in range(len(ZOOM_DEPTH_BINS) - 1)
    ]

    ax.legend(
        handles=legend,
        loc="upper left",
        fontsize=13,
        title="Flood depth (m)",
        title_fontsize=14,
        frameon=True,
        framealpha=0.9,
        borderpad=0.8,
        labelspacing=0.4
    )

    ax.set_title(title)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()

    print(f"✅ Saved: {output_path}")


def run_zoom():
    """PART B entry point: generate zoomed ROI MSL flood maps for every
    scenario / year / ROI combination."""

    if not os.path.isdir(FLOOD_DIR):
        print(f"❌ FLOOD_DIR not found: {FLOOD_DIR}")
        print("   Check that the drive is mounted and TAG is correct.")
        return

    cmap, norm = create_cmap_zoom()

    total = len(SCENARIOS) * len(TARGET_YEARS) * len(MODES) * len(DEPTH_TYPES) * len(ROIS)
    count = 0

    for scen in SCENARIOS:
        scen_l = scen.lower()

        for year in TARGET_YEARS:
            for mode in MODES:
                for depth_type in DEPTH_TYPES:

                    # =================================================
                    # MSL FILE NAMING (must match run_full() above)
                    # =================================================
                    raster_name = f"{mode}_base_msl_{TAG}_{scen_l}_{year}_{depth_type}"

                    # =================================================
                    # INPUT PATH (under FLOOD_DIR = MSL_<TAG>, from main_msl.sh)
                    # =================================================
                    raster_path = os.path.join(
                        FLOOD_DIR,
                        f"projection_{scen_l}",
                        f"{raster_name}.tif"
                    )

                    if not os.path.exists(raster_path):
                        print(f"❌ Missing: {raster_path}")
                        continue

                    for roi_name, roi in ROIS.items():

                        count += 1
                        print(f"\n[{count}/{total}] {raster_name} | {roi_name}")

                        data, bounds = load_raster_roi(raster_path, roi)

                        if data is None:
                            continue

                        data = np.ma.masked_where(data == 0, data)

                        # =================================================
                        # OUTPUT PATH (under tagged ZOOM_OUTPUT_DIR, grouped by ROI)
                        # =================================================
                        out_dir = os.path.join(
                            ZOOM_OUTPUT_DIR,
                            OUTPUT_GROUP[depth_type],
                            f"projection_{scen_l}",
                            ROI_LABELS[roi_name]
                        )

                        os.makedirs(out_dir, exist_ok=True)

                        out_path = os.path.join(
                            out_dir,
                            f"{raster_name}_{ROI_LABELS[roi_name]}.png"
                        )

                        title = (
                            f"MSL (+36.7cm) | {scen} | {year} | "
                            f"{depth_type} | {ROI_LABELS[roi_name]}"
                        )

                        plot_map_zoom(
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
    print("\n==============================")
    print("MSL FLOOD MAPS - PART A: FULL-EXTENT")
    print("==============================\n")

    run_full()

    print("\n==============================")
    print("MSL ZOOM FLOOD MAPS + OSM + GROUPED OUTPUT - PART B")
    print("==============================\n")

    run_zoom()

    print("\nDONE - ALL MSL VISUALIZATIONS COMPLETED (FULL + ZOOM)")