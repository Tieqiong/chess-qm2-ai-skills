#!/bin/bash
#$ -N dials_stage1
#$ -q 'all.q@lnx307*,all.q@lnx311*,all.q@lnx312*,all.q@lnx313*'
#$ -l mem_free=64G
#$ -pe sge_pe 24
#$ -j y
#$ -o dials_stage1.log

set -euo pipefail
# DIALS uses process workers; avoid multiplying each worker by NSLOTS threads.
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
DIALS_ENV="${DIALS_ENV:-/nfs/chess/sw/dials_sgomezalvarado/dials_env.sh}"
SKILLS_DIR="${SKILLS_DIR:-$HOME/.gemini/config/skills/chess-dials-reduction}"

if [ "$#" -lt 3 ]; then
    echo "Usage: qsub dials-stage1-template.sh <work_dir> <raw_sweep> <poni_file> [edf_mask] [unit_cell] [space_group] [extra options...]"
    exit 1
fi
WORK_DIR="$1"
RAW_DIR="$2"
PONI_FILE="$3"
EDF_MASK="${4:-}"
UNIT_CELL="${5:-}"
SPACE_GROUP="${6:-}"
shift "$(( $# < 6 ? $# : 6 ))"
CMD=(python3 "$SKILLS_DIR/scripts/orchestrate_dials.py" stage1
    --work-dir "$WORK_DIR" --raw-dir "$RAW_DIR" --poni-file "$PONI_FILE"
    --dials-env "$DIALS_ENV" --nproc "${NSLOTS:-24}")
if [ -n "$EDF_MASK" ]; then CMD+=(--edf-mask "$EDF_MASK"); fi
if [ -n "$UNIT_CELL" ]; then CMD+=(--unit-cell "$UNIT_CELL"); fi
if [ -n "$SPACE_GROUP" ]; then CMD+=(--space-group "$SPACE_GROUP"); fi
CMD+=("$@")
printf 'Launching DIALS Stage 1 on %s\n' "$(hostname)"
"${CMD[@]}"
printf 'DIALS stage completed successfully\n'
