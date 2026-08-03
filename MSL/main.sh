#!/usr/bin/env bash
# =========================================================
#  Automated Flood Modeling Workflow (Mean Sea Level)
#  Based on r.cost with MSL anomaly data
#  Variant: +36.7 cm vertical correction dataset
# ==========#!/usr/bin/env bash
# =========================================================
#  Automated Flood Modeling Workflow (Mean Sea Level)
#  Based on r.cost with MSL anomaly data
#  Variant: +36.7 cm vertical correction dataset
# =========================================================

set -euo pipefail

# -------------------------------
# USER CONFIGURATION
# the files below will be put inside a new mapset created in grass gis interface
# in grass gis terminal we switch to our mapset using this command: g.mapset mapset=#mapset_name ,
# then we run the script
# -------------------------------

# --- GRASS map names (NOT filesystem paths) ---
# These must already exist as raster/vector layers inside the active GRASS mapset
# (imported beforehand via r.import / v.import). Change these if your mapset uses
# different layer names. Same layers as used in main_esl.sh.
DTM="dtm"                       # GRASS raster: digital terrain model
ROUGHNESS="roughness_papaio"     # GRASS raster: land-cover roughness layer
SHORELINE_RAST="shoreline_rast"  # GRASS raster: shoreline start points for r.cost
LAND_MASK="landmask"             # GRASS vector: land boundary used for masking


TAG="tsl_corr36_7cm"  # short label identifying this VLM/TSL correction + DTM version; used to tag output map names and the export folder

# --- Filesystem output path ---
# Root folder (on external drive) where all GeoTIFF exports for this MSL run are written.
# Update this if running on a different machine or drive.
EXPORT_DIR="/Volumes/WD/MSL_${TAG}"

mkdir -p "${EXPORT_DIR}"

MODES=(FULL)

# -------------------------------
# SET COMPUTATIONAL REGION
# -------------------------------

# Remove existing mask if any
if g.list type=raster pattern=MASK | grep -q MASK; then
    r.mask -r
fi
####################################

TARGET_YEARS=(2020 2040 2060 2080)


SCENARIOS=( "SSP245" "SSP585")

# --- Filesystem input path ---
# Root folder containing the source MSL/TSL point files (.gpkg), organized as:
#   <BASE_DIR>/projection<scenario>/tsl/tsl_<year>.gpkg
# Update this path if the data has been moved or you're running on another machine/user account.
# NOTE: different folder from the ESL workflow's BASE_DIR (this one ends in
# reprojected_7792_tsl_36_7_cm, without "esl").
BASE_DIR="/Users/hlouati/Library/CloudStorage/Dropbox-CMCC/hanen louati/shoreline_evolution/water_levels/reprojected_7792_tsl_36_7_cm"

# Set region to match DTM
g.region raster=${DTM}

# ========================================
# STEP 1: IMPORT AND RASTERIZE MSL DATA
# ========================================

for SCEN in "${SCENARIOS[@]}"; do
    SCEN_LOWER=$(echo "$SCEN" | tr '[:upper:]' '[:lower:]')

    for YEAR in "${TARGET_YEARS[@]}"; do

        # --- Constructed input file path ---
        # Points to the specific .gpkg file for this scenario/year combo, built from BASE_DIR above.
        GPKG="${BASE_DIR}/projection${SCEN_LOWER}/tsl/tsl_${YEAR}.gpkg"
        NAME="msl_pts_${TAG}_${SCEN}_${YEAR}"

        # Check if file exists before importing
        if [ ! -f "${GPKG}" ]; then
            echo "⚠️  File not found, skipping: ${GPKG}"
            continue
        fi

        echo ">>> Importing: ${GPKG}"

        # Import vector points
        v.import --overwrite input="${GPKG}" \
            output="${NAME}" \
            layer=msl_points

        g.region vector="${NAME}"

        # Rasterize using value column
        v.to.rast input="${NAME}" \
            output="${NAME}_rast" \
            use=attr \
            attribute_column=value \
            --overwrite

        # Propagate nearest coastal point value to every cell
        r.grow.distance input="${NAME}_rast" \
            value="MSL_${TAG}_${SCEN}_${YEAR}" \
            --overwrite

        echo ">>> MSL raster ready: MSL_${TAG}_${SCEN}_${YEAR}"

    done
done

# Set region to match DTM
g.region raster=${DTM}

# ========================================
# STEP 2: FLOOD MODELING WITH MSL DATA
# ========================================

for SCEN in "${SCENARIOS[@]}"; do
    SCEN_LOWER=$(echo "$SCEN" | tr '[:upper:]' '[:lower:]')

    # --- Constructed output directory path ---
    # Per-scenario export subfolder under EXPORT_DIR, e.g.
    #   /Volumes/WD/MSL_tsl_corr36_7cm_new_dtm/projection_ssp245/
    # NOTE: unlike the ESL workflow, there's no return-period subfolder level here,
    # since MSL has no return periods (rl10/rl50/rl100).
    OUTPUT_SUBDIR="${EXPORT_DIR}/projection_${SCEN_LOWER}"
    mkdir -p "${OUTPUT_SUBDIR}"

    for YEAR in "${TARGET_YEARS[@]}"; do

        MSL_RAST="MSL_${TAG}_${SCEN}_${YEAR}"
        BASE="base_msl_${TAG}_${SCEN_LOWER}_${YEAR}"


        # --- Create flooded areas where DTM < MSL ---
        r.mapcalc --overwrite "${BASE}_grid1 = if(${DTM} < ${MSL_RAST}, 1, 0)"
        r.mapcalc --overwrite "${BASE}_grid2 = if(${BASE}_grid1 == 1, 1, null())"

        r.mask raster=${BASE}_grid2
        r.mapcalc --overwrite "${BASE}_dtm_masked = ${DTM}"
        r.mask -r

        r.mask vector=${LAND_MASK}
        r.mapcalc --overwrite "${BASE}_dtm_masked = ${BASE}_dtm_masked"
        r.mask -r

        # 2. Slope, aspect, curvature on masked DTM
        r.slope.aspect --overwrite -e elevation=${BASE}_dtm_masked \
            slope=${BASE}_slope aspect=${BASE}_aspect \
            pcurvature=${BASE}_pcurv tcurvature=${BASE}_tcurv



        # 3. Roughness factor
        rough_min=$(r.univar -g map=${ROUGHNESS} | grep min= | cut -d'=' -f2)
        rough_max=$(r.univar -g map=${ROUGHNESS} | grep max= | cut -d'=' -f2)
        r.mapcalc --overwrite "${BASE}_rough_norm = (${ROUGHNESS} - ${rough_min}) / (${rough_max} - ${rough_min})"

        # 4. Compute slope factor (P95)
        p95_slope=$(r.quantile input=${BASE}_slope percentiles=95 --overwrite | awk -F':' '{print $3}')
        r.mapcalc --overwrite "${BASE}_slope_norm = min(${BASE}_slope / ${p95_slope}, 1.0)"

        # Combine slope and roughness factors
        r.mapcalc --overwrite "${BASE}_slope_factor = ${BASE}_slope_norm"
        r.mapcalc --overwrite "${BASE}_rough_factor = ${BASE}_rough_norm"

        for MODE in "${MODES[@]}"; do
            PREFIX="${MODE}_${BASE}"

            # Create friction surface
            r.mapcalc --overwrite "${PREFIX}_friction = ${BASE}_slope_factor * ${BASE}_rough_factor"

            # Apply r.cost from shoreline
            r.cost --overwrite -k input=${PREFIX}_friction \
                start_raster=${SHORELINE_RAST} \
                output=${PREFIX}_cost

            # --- Calculate flood depth using MSL ---
            r.mask raster=${PREFIX}_cost
            r.mapcalc --overwrite "${PREFIX}_flooded_areas = ${DTM}"
            r.mask -r

            r.mapcalc --overwrite "${PREFIX}_grid9 = ${MSL_RAST} - ${PREFIX}_flooded_areas"
            r.mapcalc --overwrite "${PREFIX}_flood_depth = if(${PREFIX}_grid9 > 0, ${PREFIX}_grid9, null())"

            # --- Output file path: basic flood depth GeoTIFF ---
            # Written to OUTPUT_SUBDIR (see path comment above), named after PREFIX
            r.out.gdal input="${PREFIX}_flood_depth" \
                output="${OUTPUT_SUBDIR}/${PREFIX}_flood_depth.tif" \
                format=GTiff \
                --overwrite

            ############################################
            # Weighted Depth Reduction using cost
            ############################################

            # Define flooded zone for percentile calculation
            r.mapcalc --overwrite "${PREFIX}_zone_cost = if(!isnull(${PREFIX}_cost), 1, null())"

            # Compute 95th percentile of flood_cost for normalization
            r.stats.quantile --overwrite base=${PREFIX}_zone_cost cover=${PREFIX}_cost percentiles=95 output=${PREFIX}_p95_cost_cost

            # Normalize least-cost to 0–1 range
            r.mapcalc --overwrite "${PREFIX}_cost_norm_cost = min(${PREFIX}_cost / ${PREFIX}_p95_cost_cost, 1.0)"

            eval $(r.univar -g map=${PREFIX}_cost)

            r.mapcalc --overwrite "${PREFIX}_cost_norm_max = min(${PREFIX}_cost / ${max}, 1.0)"

            # Create damping factor reducing depth for harder-to-reach cells
            r.mapcalc --overwrite "${PREFIX}_damp_factor_cost = 1 - ${PREFIX}_cost_norm_cost"
            r.mapcalc --overwrite "${PREFIX}_damp_factor_max = 1 - ${PREFIX}_cost_norm_max"

            # Apply damping to raw depth to get final "advanced" depth map
            r.mapcalc --overwrite "${PREFIX}_advanced_depth_cost = ${PREFIX}_flood_depth * ${PREFIX}_damp_factor_cost"
            r.mapcalc --overwrite "${PREFIX}_advanced_depth_max = ${PREFIX}_flood_depth * ${PREFIX}_damp_factor_max"

            # Verify Mask using raster
            r.mask vector=${LAND_MASK}
            # Do your calculation
            r.mapcalc --overwrite "${PREFIX}_advanced_depth_cost = if(${PREFIX}_advanced_depth_cost > 0, ${PREFIX}_advanced_depth_cost, null())"
            r.mapcalc --overwrite "${PREFIX}_advanced_depth_max = if(${PREFIX}_advanced_depth_max > 0, ${PREFIX}_advanced_depth_max, null())"
            # Remove the mask
            r.mask -r

            # --- Output file path: damped depth GeoTIFF (percentile-normalized) ---
            r.out.gdal input=${PREFIX}_advanced_depth_cost \
                output="${OUTPUT_SUBDIR}/${PREFIX}_advanced_depth_cost.tif" \
                format=GTiff \
                --overwrite

            # --- Output file path: damped depth GeoTIFF (max-normalized) ---
            r.out.gdal input=${PREFIX}_advanced_depth_max \
                output="${OUTPUT_SUBDIR}/${PREFIX}_advanced_depth_max.tif" \
                format=GTiff \
                --overwrite

            echo ">>> Completed: ${PREFIX} (${YEAR})"

        done
    done
done

echo "=============================================="
echo "✅ MSL flood modeling completed (${TAG})"
echo "✅ Exports saved in: ${EXPORT_DIR}/projection_*/"
echo "=============================================="==============================================

set -euo pipefail

# -------------------------------
# USER CONFIGURATION
# the files below will be put inside a new mapset created in grass gis interface
# in grass gis terminal we switch to our mapset using this command: g.mapset mapset=#mapset_name ,
# then we run the script
# -------------------------------
DTM="dtm"
ROUGHNESS="roughness_papaio"
SHORELINE_RAST="shoreline_rast"
LAND_MASK="landmask"


TAG="tsl_corr36_7cm_new_dtm"

EXPORT_DIR="/Volumes/WD/MSL_${TAG}"

mkdir -p "${EXPORT_DIR}"

MODES=(FULL)

# -------------------------------
# SET COMPUTATIONAL REGION
# -------------------------------

# Remove existing mask if any
if g.list type=raster pattern=MASK | grep -q MASK; then
    r.mask -r
fi
####################################

TARGET_YEARS=(2020 2040 2060 2080)


SCENARIOS=( "SSP245" "SSP585")
BASE_DIR="/Users/hlouati/Library/CloudStorage/Dropbox-CMCC/hanen louati/shoreline_evolution/water_levels/reprojected_7792_tsl_36_7_cm"

# Set region to match DTM
g.region raster=${DTM}

# ========================================
# STEP 1: IMPORT AND RASTERIZE MSL DATA
# ========================================

for SCEN in "${SCENARIOS[@]}"; do
    SCEN_LOWER=$(echo "$SCEN" | tr '[:upper:]' '[:lower:]')

    for YEAR in "${TARGET_YEARS[@]}"; do

        GPKG="${BASE_DIR}/projection${SCEN_LOWER}/tsl/tsl_${YEAR}.gpkg"
        NAME="msl_pts_${TAG}_${SCEN}_${YEAR}"

        # Check if file exists before importing
        if [ ! -f "${GPKG}" ]; then
            echo "⚠️  File not found, skipping: ${GPKG}"
            continue
        fi

        echo ">>> Importing: ${GPKG}"

        # Import vector points
        v.import --overwrite input="${GPKG}" \
            output="${NAME}" \
            layer=msl_points

        g.region vector="${NAME}"

        # Rasterize using value column
        v.to.rast input="${NAME}" \
            output="${NAME}_rast" \
            use=attr \
            attribute_column=value \
            --overwrite

        # Propagate nearest coastal point value to every cell
        r.grow.distance input="${NAME}_rast" \
            value="MSL_${TAG}_${SCEN}_${YEAR}" \
            --overwrite

        echo ">>> MSL raster ready: MSL_${TAG}_${SCEN}_${YEAR}"

    done
done

# Set region to match DTM
g.region raster=${DTM}

# ========================================
# STEP 2: FLOOD MODELING WITH MSL DATA
# ========================================

for SCEN in "${SCENARIOS[@]}"; do
    SCEN_LOWER=$(echo "$SCEN" | tr '[:upper:]' '[:lower:]')

    # Create output directory structure: projection_${scenario}/
    OUTPUT_SUBDIR="${EXPORT_DIR}/projection_${SCEN_LOWER}"
    mkdir -p "${OUTPUT_SUBDIR}"

    for YEAR in "${TARGET_YEARS[@]}"; do

        MSL_RAST="MSL_${TAG}_${SCEN}_${YEAR}"
        BASE="base_msl_${TAG}_${SCEN_LOWER}_${YEAR}"


        # --- Create flooded areas where DTM < MSL ---
        r.mapcalc --overwrite "${BASE}_grid1 = if(${DTM} < ${MSL_RAST}, 1, 0)"
        r.mapcalc --overwrite "${BASE}_grid2 = if(${BASE}_grid1 == 1, 1, null())"

        r.mask raster=${BASE}_grid2
        r.mapcalc --overwrite "${BASE}_dtm_masked = ${DTM}"
        r.mask -r

        r.mask vector=${LAND_MASK}
        r.mapcalc --overwrite "${BASE}_dtm_masked = ${BASE}_dtm_masked"
        r.mask -r

        # 2. Slope, aspect, curvature on masked DTM
        r.slope.aspect --overwrite -e elevation=${BASE}_dtm_masked \
            slope=${BASE}_slope aspect=${BASE}_aspect \
            pcurvature=${BASE}_pcurv tcurvature=${BASE}_tcurv



        # 3. Roughness factor
        rough_min=$(r.univar -g map=${ROUGHNESS} | grep min= | cut -d'=' -f2)
        rough_max=$(r.univar -g map=${ROUGHNESS} | grep max= | cut -d'=' -f2)
        r.mapcalc --overwrite "${BASE}_rough_norm = (${ROUGHNESS} - ${rough_min}) / (${rough_max} - ${rough_min})"

        # 4. Compute slope factor (P95)
        p95_slope=$(r.quantile input=${BASE}_slope percentiles=95 --overwrite | awk -F':' '{print $3}')
        r.mapcalc --overwrite "${BASE}_slope_norm = min(${BASE}_slope / ${p95_slope}, 1.0)"

        # Combine slope and roughness factors
        r.mapcalc --overwrite "${BASE}_slope_factor = ${BASE}_slope_norm"
        r.mapcalc --overwrite "${BASE}_rough_factor = ${BASE}_rough_norm"

        for MODE in "${MODES[@]}"; do
            PREFIX="${MODE}_${BASE}"

            # Create friction surface
            r.mapcalc --overwrite "${PREFIX}_friction = ${BASE}_slope_factor * ${BASE}_rough_factor"

            # Apply r.cost from shoreline
            r.cost --overwrite -k input=${PREFIX}_friction \
                start_raster=${SHORELINE_RAST} \
                output=${PREFIX}_cost

            # --- Calculate flood depth using MSL ---
            r.mask raster=${PREFIX}_cost
            r.mapcalc --overwrite "${PREFIX}_flooded_areas = ${DTM}"
            r.mask -r

            r.mapcalc --overwrite "${PREFIX}_grid9 = ${MSL_RAST} - ${PREFIX}_flooded_areas"
            r.mapcalc --overwrite "${PREFIX}_flood_depth = if(${PREFIX}_grid9 > 0, ${PREFIX}_grid9, null())"

            # Export raw flood depth
            r.out.gdal input="${PREFIX}_flood_depth" \
                output="${OUTPUT_SUBDIR}/${PREFIX}_flood_depth.tif" \
                format=GTiff \
                --overwrite

            ############################################
            # Weighted Depth Reduction using cost
            ############################################

            # Define flooded zone for percentile calculation
            r.mapcalc --overwrite "${PREFIX}_zone_cost = if(!isnull(${PREFIX}_cost), 1, null())"

            # Compute 95th percentile of flood_cost for normalization
            r.stats.quantile --overwrite base=${PREFIX}_zone_cost cover=${PREFIX}_cost percentiles=95 output=${PREFIX}_p95_cost_cost

            # Normalize least-cost to 0–1 range
            r.mapcalc --overwrite "${PREFIX}_cost_norm_cost = min(${PREFIX}_cost / ${PREFIX}_p95_cost_cost, 1.0)"

            eval $(r.univar -g map=${PREFIX}_cost)

            r.mapcalc --overwrite "${PREFIX}_cost_norm_max = min(${PREFIX}_cost / ${max}, 1.0)"

            # Create damping factor reducing depth for harder-to-reach cells
            r.mapcalc --overwrite "${PREFIX}_damp_factor_cost = 1 - ${PREFIX}_cost_norm_cost"
            r.mapcalc --overwrite "${PREFIX}_damp_factor_max = 1 - ${PREFIX}_cost_norm_max"

            # Apply damping to raw depth to get final "advanced" depth map
            r.mapcalc --overwrite "${PREFIX}_advanced_depth_cost = ${PREFIX}_flood_depth * ${PREFIX}_damp_factor_cost"
            r.mapcalc --overwrite "${PREFIX}_advanced_depth_max = ${PREFIX}_flood_depth * ${PREFIX}_damp_factor_max"

            # Verify Mask using raster
            r.mask vector=${LAND_MASK}
            # Do your calculation
            r.mapcalc --overwrite "${PREFIX}_advanced_depth_cost = if(${PREFIX}_advanced_depth_cost > 0, ${PREFIX}_advanced_depth_cost, null())"
            r.mapcalc --overwrite "${PREFIX}_advanced_depth_max = if(${PREFIX}_advanced_depth_max > 0, ${PREFIX}_advanced_depth_max, null())"
            # Remove the mask
            r.mask -r

            # Export advanced depth cost
            r.out.gdal input=${PREFIX}_advanced_depth_cost \
                output="${OUTPUT_SUBDIR}/${PREFIX}_advanced_depth_cost.tif" \
                format=GTiff \
                --overwrite

            # Export advanced depth max
            r.out.gdal input=${PREFIX}_advanced_depth_max \
                output="${OUTPUT_SUBDIR}/${PREFIX}_advanced_depth_max.tif" \
                format=GTiff \
                --overwrite

            echo ">>> Completed: ${PREFIX} (${YEAR})"

        done
    done
done

echo "=============================================="
echo "✅ MSL flood modeling completed (${TAG})"
echo "✅ Exports saved in: ${EXPORT_DIR}/projection_*/"
echo "=============================================="