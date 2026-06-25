#!/usr/bin/env python3
# =========================================================
# Flood Zoom Maps + OSM Basemap (CRS-safe + Output grouping)
# =========================================================

import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import BoundaryNorm, ListedColormap
import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds
import contextily as ctx
from pyproj import Transformer
from matplotlib.ticker import FuncFormatter
import warnings
import numpy.ma as ma
warnings.filterwarnings('ignore')

# =========================================================
# INPUT / OUTPUT PATHS (UNCHANGED - YOUR STRUCTURE)
# =========================================================

FLOOD_DIR = "/Users/hlouati/Desktop/ESL"

OUTPUT_DIR = "/Users/hlouati/Desktop/ESL/flood_maps_python_zoom"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# =========================================================
# ROIS (EPSG:7792)
# =========================================================

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
LOCATIONS = {
    "Frigole": (18.242426463650784, 40.42524239321438),

    "Idume": (18.186394748512967, 40.46723804789989)
}
# =========================================================
# OUTPUT STRUCTURE (YOUR REQUEST)
# =========================================================

OUTPUT_GROUP = {
    "advanced_depth_cost": "with_damping"
}

# =========================================================
# MODEL STRUCTURE
# =========================================================

SCENARIOS = ["SSP245", "SSP585"]
VARIABLES = ["rl10", "rl50", "rl100"]
YEARS = [2020, 2040, 2060, 2080]
MODES = ["FULL"]

DEPTH_TYPES = ["advanced_depth_cost"]

# =========================================================
# STYLE
# =========================================================

DEPTH_BINS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 2.0]

DEPTH_COLORS = [
    '#f7fbff', '#eff8ff', '#deebf7', '#c6dbef', '#9ecae1',
    '#6baed6', '#4292c6', '#2171b5', '#08519c', '#08306b', '#041e5e'
]

FLOOD_OPACITY = 0.65
DPI = 300
FIGSIZE = (12, 10)

# =========================================================
# LOAD RASTER (ROI WINDOW)
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

# =========================================================
# COLOR MAP
# =========================================================

def create_cmap():
    cmap = ListedColormap(DEPTH_COLORS)
    norm = BoundaryNorm(DEPTH_BINS, len(DEPTH_COLORS))
    return cmap, norm

# =========================================================
# PLOT (CRS CORRECT + OSM)
# =========================================================

def plot_map(data, bounds_7792, title, output_path, cmap, norm):

    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
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
    # OSM basemap (correct CRS)
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

    for name, (lon, lat) in LOCATIONS.items():
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

# =========================================================
# MAIN LOOP
# =========================================================

def run():

    cmap, norm = create_cmap()

    total = len(SCENARIOS) * len(VARIABLES) * len(YEARS) * len(MODES) * len(DEPTH_TYPES) * len(ROIS)
    count = 0

    for scen in SCENARIOS:
        for var in VARIABLES:
            for year in YEARS:
                for mode in MODES:
                    for depth_type in DEPTH_TYPES:

                        # -------------------------------------------------
                        # FILE NAME (matches your real dataset)
                        # -------------------------------------------------
                        base = f"base_{scen}_{var}yr_{year}"
                        raster_name = f"{mode}_{base}_{depth_type}"

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
                            # OUTPUT GROUP LOGIC (YOUR REQUEST)
                            # -------------------------------------------------
                            out_dir = os.path.join(
                                OUTPUT_DIR,
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

                            title = f"{scen} | {var} | {year} | {depth_type} | {ROI_LABELS[roi_name]}"

                            plot_map(
                                data,
                                bounds,
                                title,
                                out_path,
                                cmap,
                                norm
                            )

# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    print("\n==============================")
    print("ZOOM FLOOD MAPS + OSM + GROUPED OUTPUT")
    print("==============================\n")

    run()

    print("\nDONE")