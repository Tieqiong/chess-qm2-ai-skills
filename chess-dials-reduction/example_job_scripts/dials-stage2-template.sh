#!/bin/bash
#$ -N dials_stage2
#$ -q 'all.q@lnx307*,all.q@lnx311*,all.q@lnx312*,all.q@lnx313*'
#$ -l mem_free=120G
#$ -pe sge_pe 24
#$ -j y
#$ -o dials_stage2.log

set -euo pipefail
# DIALS uses process workers; avoid multiplying each worker by NSLOTS threads.
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
DIALS_ENV="${DIALS_ENV:-/nfs/chess/sw/dials_sgomezalvarado/dials_env.sh}"
SKILLS_DIR="${SKILLS_DIR:-$HOME/.gemini/config/skills/chess-dials-reduction}"

if [ "$#" -lt 2 ]; then
    echo "Usage: qsub dials-stage2-template.sh <work_dir> <bravais_setting> [cb_op] [asu_composition_or_elements] [extra options...]"
    exit 1
fi
WORK_DIR="$1"
BRAVAIS_SETTING="$2"
CB_OP="${3:-a,b,c}"
COMPOSITION="${4:-KCoTeO}"
shift "$(( $# < 4 ? $# : 4 ))"
printf 'Launching DIALS Stage 2 on %s\n' "$(hostname)"
python3 "$SKILLS_DIR/scripts/orchestrate_dials.py" stage2 \
    --work-dir "$WORK_DIR" --dials-env "$DIALS_ENV" \
    --bravais-setting "$BRAVAIS_SETTING" --cb-op "$CB_OP" \
    --composition "$COMPOSITION" --nproc "${NSLOTS:-24}" \
    --scan-varying False \
    --scaling-model physical --absorption-level medium --anomalous True "$@"
printf 'DIALS stage completed successfully\n'
