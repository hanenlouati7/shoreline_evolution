#!/usr/bin/env bash
# =========================================================
#  Automated Flood Modeling Workflow (v3, using r.cost )
# =========================================================

set -euo pipefail

# -------------------------------
# USER CONFIGURATION 
#the files  below will be put inside a new mapset created in grass gis interface
# in grass gis terminal we switch to our mapset using this command: g.mapset mapset=#mapset_name , 
#then we run the script 
# -------------------------------
DTM="dtm"
ROUGHNESS="roughness_papaio"
SHORELINE_RAST="shoreline_rast"
LAND_MASK="landmask"
EXPORT_DIR="/Users/hlouati/Desktop/ESL"

mkdir -p "${EXPORT_DIR}" 

MODES=(FULL )

# -------------------------------
# SET COMPUTATIONAL REGION
# -------------------------------

# Remove existing mask if any
if g.list type=raster pattern=MASK | grep -q MASK; then
    r.mask -r
fi
####################################

TARGET_YEARS=(2020 2040 2060 2080)
SCENARIOS=("SSP245" "SSP585")
VARIABLES=("rl_50yr" "rl_10yr" "rl_100yr")
BASE_DIR="/Users/hlouati/Library/CloudStorage/Dropbox-CMCC/hanen louati/shoreline_evolution/water_levels/reprojected_7792_2"

# Set region to match DTM
g.region raster=${DTM}

for SCEN in "${SCENARIOS[@]}"; do
    SCEN_LOWER=$(echo "$SCEN" | tr '[:upper:]' '[:lower:]')
    
    for VAR in "${VARIABLES[@]}"; do
        # map folder name
        case $VAR in
            "rl_10yr") FOLDER="rl10" ;;
            "rl_50yr") FOLDER="rl50" ;;
            "rl_100yr") FOLDER="rl100" ;;
        esac

        for YEAR in "${TARGET_YEARS[@]}"; do

            GPKG="${BASE_DIR}/projection${SCEN_LOWER}/${FOLDER}/${VAR}_${YEAR}.gpkg"
            NAME="esl_pts_${SCEN}_${VAR}_${YEAR}"

            echo ">>> Importing: ${GPKG}"

            # Import vector points
            v.import --overwrite input="${GPKG}" \
                output="${NAME}" \
                layer=esl_points 
            
            g.region vector="${NAME}"

                

            # Rasterize using value column — only coastal points get values, rest is null
            v.to.rast input="${NAME}" \
                output="${NAME}_rast" \
                use=attr \
                attribute_column=value \
                --overwrite

            # Propagate nearest coastal point value to every cell
            r.grow.distance input="${NAME}_rast" \
                value="ESL_${SCEN}_${VAR}_${YEAR}" \
                --overwrite

            echo ">>> ESL raster ready: ESL_${SCEN}_${VAR}_${YEAR}"

        done
    done
done

# Set region to match DTM
g.region raster=${DTM}


for SCEN in "${SCENARIOS[@]}"; do
    SCEN_LOWER=$(echo "$SCEN" | tr '[:upper:]' '[:lower:]')
    
    for VAR in "${VARIABLES[@]}"; do
        # map folder name
        case $VAR in
            "rl_10yr") FOLDER="rl10" ;;
            "rl_50yr") FOLDER="rl50" ;;
            "rl_100yr") FOLDER="rl100" ;;
        esac
        
        # Create output directory structure: projection_${scenario}/rl_period/
        OUTPUT_SUBDIR="${EXPORT_DIR}/projection_${SCEN_LOWER}/${FOLDER}"
        mkdir -p "${OUTPUT_SUBDIR}"
        
        for YEAR in "${TARGET_YEARS[@]}"; do

            ESL_RAST="ESL_${SCEN}_${VAR}_${YEAR}"
            BASE="base_${SCEN}_${VAR//_/}_${YEAR}"

            # --- replaces scalar threshold ---
            r.mapcalc --overwrite "${BASE}_grid1 = if(${DTM} < ${ESL_RAST}, 1, 0)"
            r.mapcalc --overwrite "${BASE}_grid2 = if(${BASE}_grid1 == 1, 1, null())"

            r.mask raster=${BASE}_grid2
            r.mapcalc --overwrite "${BASE}_dtm_masked = ${DTM}"
            r.mask -r

            r.mask vector=${LAND_MASK}
            r.mapcalc --overwrite "${BASE}_dtm_masked = ${BASE}_dtm_masked"
            r.mask -r

            # slope/roughness/r.cost blocks unchanged ...
            # 2. Slope, aspect, curvature on masked DTM
            r.slope.aspect --overwrite -e elevation=${BASE}_dtm_masked \
                slope=${BASE}_slope aspect=${BASE}_aspect \
                pcurvature=${BASE}_pcurv tcurvature=${BASE}_tcurv

            #  create aspect masking using land_mask
            #r.mask vector=${LAND_MASK}
            #r.mapcalc --overwrite "${BASE}_aspect_mask = ${BASE}_aspect"
            #r.mask -r

            
            # 7. Roughness factor

            rough_min=$(r.univar -g map=${ROUGHNESS} | grep min= | cut -d'=' -f2)
            rough_max=$(r.univar -g map=${ROUGHNESS}| grep max= | cut -d'=' -f2)
            r.mapcalc --overwrite "${BASE}_rough_norm = (${ROUGHNESS} - ${rough_min}) / (${rough_max} - ${rough_min})"

            # 8. compute slope factor (P95)
            p95_slope=$(r.quantile input=${BASE}_slope percentiles=95 --overwrite | awk -F':' '{print $3}')
            r.mapcalc --overwrite "${BASE}_slope_norm = min(${BASE}_slope / ${p95_slope}, 1.0)"


            # slope: 1–2
            r.mapcalc --overwrite "${BASE}_slope_factor =  ${BASE}_slope_norm"

            # roughness: 1–2
            r.mapcalc --overwrite "${BASE}_rough_factor =  ${BASE}_rough_norm"

            for MODE in "${MODES[@]}"; do
                PREFIX="${MODE}_${BASE}"
                
                # friction block unchanged ...
                r.mapcalc --overwrite "${PREFIX}_friction = ${BASE}_slope_factor * ${BASE}_rough_factor"


                r.cost --overwrite -k input=${PREFIX}_friction \
                    start_raster=${SHORELINE_RAST} \
                    output=${PREFIX}_cost
                
                # --- key change: ESL_RAST replaces scalar ESL ---
                r.mask raster=${PREFIX}_cost
                r.mapcalc --overwrite "${PREFIX}_flooded_areas = ${DTM}"
                r.mask -r

                r.mapcalc --overwrite "${PREFIX}_grid9 = ${ESL_RAST} - ${PREFIX}_flooded_areas"
                r.mapcalc --overwrite "${PREFIX}_flood_depth = if(${PREFIX}_grid9 > 0, ${PREFIX}_grid9, null())"
                # Export advanced depth max
                r.out.gdal input="${PREFIX}_flood_depth" \
                    output="${OUTPUT_SUBDIR}/${PREFIX}_flood_depth.tif" \
                    format=GTiff \
                    --overwrite
              
                ############################################
                #step 14 another approach using  weighted Depth Reduction 
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
                # verify Mask using raster 
                r.mask vector=${LAND_MASK}
                # Do your calculation
                r.mapcalc --overwrite "${PREFIX}_advanced_depth_cost= if(${PREFIX}_advanced_depth_cost > 0, ${PREFIX}_advanced_depth_cost, null())"
                r.mapcalc --overwrite "${PREFIX}_advanced_depth_max= if(${PREFIX}_advanced_depth_max > 0, ${PREFIX}_advanced_depth_max, null())"
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

            done
        done
    done
done
echo "=============================================="
echo "✅ results were produced in grass interface"
echo "✅ Exports saved in: ${EXPORT_DIR}/projection_*/rl*/"
echo "=============================================="