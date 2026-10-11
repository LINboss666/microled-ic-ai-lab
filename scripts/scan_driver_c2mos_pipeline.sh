#!/bin/bash
# Scan Driver C2MOS -> Virtuoso schematic, using ONLY the repository's frozen flow.
#   import : scripts/sch1_asg_import.sh  (defaults: CELL=c2mos_dff_1bit from spectre/C2MOS_DFF.scs)
#   fix    : skill/sch3_fix_params.il    (SCH-3 posture, sizes from the committed
#            skill/sch2_param_table.gen.il which is generated from the golden netlist)
#   strip  : skill/qoder_del_simw.il     (residual simW the importer leaves behind)
#   verify : skill/sch3_readback.il (read-only) + scripts/sch_parameter_integrity_check.py
#            + scripts/sch2_connectivity_diff.py
# No design decisions live here: no size, no net, no topology, nothing against the PDK.
set -u
P=/root/microled_ai_project
W=$P/cadence_work
RUN=/root/qoder_ic617_sandbox/bin/sch_virtuoso.sh
O=$W/logs/c2mos
mkdir -p "$O"
R() { echo "[$(date +%H:%M:%S)] $*"; }
cd "$P" || exit 9

R "GUARD virtuoso_main=$(ps -ef | grep -c '[d]fII/bin/64bit/virtuoso')"
R "GUARD cell exists before? $(ls -d $W/microled_cells/c2mos_dff_1bit 2>/dev/null || echo NO)"
find /root/tech/teacher_pdk -printf "%p|%s\n" 2>/dev/null | sort > "$O/pdk_before.txt"
R "PDK before = $(wc -l < "$O/pdk_before.txt") entries"

R "--- STEP 1: ASG import (sch1_asg_import.sh, all defaults) ---"
PROJ=$P bash scripts/sch1_asg_import.sh > "$O/step1_import.log" 2>&1
R "step1 exit=$?  SPICEIN_ok=$(grep -acE 'SPICEIN-54|SPICEIN-33' "$O/step1_import.log")"
grep -aE "REFUSE|FATAL|CELL=|MOS|SPICEIN-[0-9]+|ASG rc|GOLDEN" "$O/step1_import.log" | tail -14
R "cells now: $(ls -1 $W/microled_cells | tr '\n' ' ')"

R "--- STEP 2: pre-fix readback (read-only) ---"
PROJ=$P MODE=nograph HOME=$W/home SCH3_LIB=microled_cells SCH3_CELLS=c2mos_dff_1bit \
  bash "$RUN" $P/skill/sch3_readback.il 600 RD3_DONE > "$O/step2_rd_pre.log" 2>&1
PRE=$(ls -t "$W"/logs/sch_nograph_*.log | head -1)
R "PRE_LOG=$PRE"
python scripts/sch_parameter_integrity_check.py --golden results/c2mos_golden_device_parameters.csv \
  --readback "$PRE" --out "$O/gate_pre.csv" --pdk-default-l 180n --pdk-default-w 220n \
  > "$O/step2_gate_pre.log" 2>&1
R "gate PRE rc=$?"; grep -aE "MOS_COUNT|MASTER_MATCH|L_MATCH|W_MATCH|_COUNT:|OA_DEVICE" "$O/step2_gate_pre.log"
R "PRE simW tally: $(grep -ao 'simW=[^ ]*' "$PRE" | sort | uniq -c | tr '\n' ' ')"

R "--- STEP 3: apply golden sizes (sch3_fix_params.il + committed table) ---"
PROJ=$P MODE=nograph HOME=$W/home SCH3_LIB=microled_cells SCH3_CELL=c2mos_dff_1bit \
  SCH3_TABLE=$P/skill/sch2_param_table.gen.il \
  bash "$RUN" $P/skill/sch3_fix_params.il 600 FX3_DONE > "$O/step3_fix.log" 2>&1
R "step3 exit=$? token=$(grep -ac FX3_DONE "$O/step3_fix.log")"
grep -aE "FX3-OPENED|FX3-ROWCOUNT|refusing|FX3-SAVE" "$O/step3_fix.log" | tail -6

R "--- STEP 4: strip residual simW ---"
PROJ=$P MODE=nograph HOME=$W/home SCH3_LIB=microled_cells SCH3_CELLS=c2mos_dff_1bit \
  bash "$RUN" $P/skill/qoder_del_simw.il 600 DS_DONE > "$O/step4_delsimw.log" 2>&1
R "step4 exit=$? token=$(grep -ac DS_DONE "$O/step4_delsimw.log")"
DS=$(grep -al "DS-BEGIN" "$W"/logs/sch_nograph_*.log | tail -1)
R "del count=$(grep -ac 'DS-DEL ' "$DS")  deletes: $(grep -ao 'DS-DEL "[a-z_0-9]*"' "$DS" | tr '\n' ' ')"
grep -aE "BEFORE-SUMMARY|AFTER-SUMMARY" "$DS" | sed 's/^..//'

R "--- STEP 5: post readback + gate ---"
PROJ=$P MODE=nograph HOME=$W/home SCH3_LIB=microled_cells SCH3_CELLS=c2mos_dff_1bit \
  bash "$RUN" $P/skill/sch3_readback.il 600 RD3_DONE > "$O/step5_rd_post.log" 2>&1
POST=$(ls -t "$W"/logs/sch_nograph_*.log | head -1)
R "POST_LOG=$POST"
python scripts/sch_parameter_integrity_check.py --golden results/c2mos_golden_device_parameters.csv \
  --readback "$POST" --out "$O/gate_post.csv" --pdk-default-l 180n --pdk-default-w 220n \
  > "$O/step5_gate_post.log" 2>&1
RC5=$?
R "gate POST rc=$RC5"; grep -aE "MOS_COUNT|MASTER_MATCH|L_MATCH|W_MATCH|_COUNT:|PORT_PINS|OA_DEVICE|MISMATCH" "$O/step5_gate_post.log"
R "POST simW tally: $(grep -ao 'simW=[^ ]*' "$POST" | sort | uniq -c | tr '\n' ' ')"
R "POST raw_w tally: $(grep -ao 'raw_w=[^ ]*' "$POST" | cut -d= -f2 | sort | uniq -c | tr '\n' ' ')"
R "POST cdf_w tally: $(grep -ao 'cdf_w=[^ ]*' "$POST" | cut -d= -f2 | sort | uniq -c | tr '\n' ' ')"

R "--- STEP 6: prove the fix moved no structure ---"
python scripts/sch2_connectivity_diff.py --before "$PRE" --after "$POST" > "$O/step6_conn.log" 2>&1
R "conn rc=$?"; tail -14 "$O/step6_conn.log"

find /root/tech/teacher_pdk -printf "%p|%s\n" 2>/dev/null | sort > "$O/pdk_after.txt"
R "PDK after = $(wc -l < "$O/pdk_after.txt") entries  diff_lines = $(diff "$O/pdk_before.txt" "$O/pdk_after.txt" | wc -l)"
R "PDK locks/logs = $(find /root/tech/teacher_pdk \( -name '*.cdslck*' -o -name 'CDS.log*' -o -name 'journal*' \) 2>/dev/null | wc -l)"
ps -ef | awk '/cdsMsgServer.*mpssession virtuoso/ && $3==1 {print $2}' | while read q; do kill "$q" 2>/dev/null; done
R "C2MOS_PIPELINE_DONE gate_post_rc=$RC5 conn_rc=$?"
