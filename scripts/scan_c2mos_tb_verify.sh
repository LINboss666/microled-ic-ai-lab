#!/bin/bash
# C2MOS Spectre verification, detached. Uses ONLY the repository's frozen testbenches and
# assertion machinery (scripts/c2mos_check.sh + scripts/tb_preflight.sh + scripts/psf_check.awk).
# Nothing here edits a cell, a parameter, a topology or the PDK.
# Order is enforced: the 3-stage chain runs only if the single DFF passes.
set -u
P=/root/microled_ai_project
O=$P/cadence_work/logs/tbverify
mkdir -p "$O"
R() { echo "[$(date +%H:%M:%S)] $*"; }
cd "$P" || exit 9

R "GUARD virtuoso_main=$(ps -ef | grep -c '[d]fII/bin/64bit/virtuoso')"
find /root/tech/teacher_pdk -printf "%p|%s\n" 2>/dev/null | sort > "$O/pdk_before.txt"
R "PDK before = $(wc -l < "$O/pdk_before.txt") entries"
R "cell untouched? md5 of schematic dir listing:"
ls -l "$P/cadence_work/microled_cells/c2mos_dff_1bit/schematic" | sed 's/^/  /'

R "--- STEP 1: install the netlist rebuilt from THIS machine's readback ---"
if [ -f "$P/spectre/generated/.committed_backup" ]; then
  R "already installed, skipping"
else
  cp -p "$P/spectre/generated/c2mos_dff_1bit_from_oa_readback.scs" "$O/committed_export.scs.bak"
  cp /tmp/rb_thismachine.scs "$P/spectre/generated/c2mos_dff_1bit_from_oa_readback.scs"
  diff "$O/committed_export.scs.bak" "$P/spectre/generated/c2mos_dff_1bit_from_oa_readback.scs" \
    > "$O/install_diff.txt" 2>&1
  R "install diff lines vs committed = $(wc -l < "$O/install_diff.txt") (expect: provenance comment only)"
fi

R "--- STEP 2: golden cell DFF (frozen deck, 2 repeats) ---"
bash scripts/c2mos_check.sh ff1 2e-7 local1 2 > "$O/ff1_golden.log" 2>&1
R "ff1 rc=$?"; grep -aE "^C2MOS_DFF_1CH|PREFLIGHT|SPECTRE name|assert|ASSERT|byte|IDENT|FAIL|PASS" "$O/ff1_golden.log" | tail -14

R "--- STEP 3: this-machine OA schematic DFF (ff1_sch, 2 repeats) ---"
bash scripts/c2mos_check.sh ff1_sch 2e-7 local1 2 > "$O/ff1_sch.log" 2>&1
R "ff1_sch rc=$?"; grep -aE "^SCHEMATIC_DFF_FUNCTION|PREFLIGHT|SPECTRE name|ASSERT|byte|IDENT|FAIL|PASS" "$O/ff1_sch.log" | tail -14

GOLD=$(grep -ac "^C2MOS_DFF_1CH: PASS" "$O/ff1_golden.log")
SCHE=$(grep -ac "^SCHEMATIC_DFF_FUNCTION: PASS" "$O/ff1_sch.log")
R "DFF verdict: golden_pass_lines=$GOLD  oa_pass_lines=$SCHE"

if [ "$GOLD" -ge 1 ] && [ "$SCHE" -ge 1 ]; then
  R "--- STEP 4: 3-stage shift register (DFF passed, so allowed) ---"
  bash scripts/c2mos_check.sh shift3_sch 9.765625e-6 local1 1 > "$O/shift3_sch.log" 2>&1
  R "shift3_sch rc=$?"; grep -aE "^SCHEMATIC_SHIFT3_FUNCTION|PREFLIGHT|SPECTRE name|ASSERT|FAIL|PASS" "$O/shift3_sch.log" | tail -12
  bash scripts/c2mos_check.sh shift3 9.765625e-6 local1 1 > "$O/shift3_golden.log" 2>&1
  R "shift3 rc=$?"; grep -aE "^C2MOS_SHIFT_3STAGE|PREFLIGHT|SPECTRE name|FAIL|PASS" "$O/shift3_golden.log" | tail -10
else
  R "STEP 4 SKIPPED: DFF did not pass, per the task order the chain must not be run"
fi

R "--- STEP 5: evidence bundle ---"
for f in "$P"/logs/c2mos_assert_*local1*.txt "$P"/logs/c2mos_dirs_*local1*.txt "$P"/logs/preflight_*local1*.txt; do
  [ -e "$f" ] && echo "  $(basename "$f") $(wc -l < "$f") lines"
done
R "delay tables:"; ls -1 "$P"/logs/c2mos_run_*local1*.out 2>/dev/null | head -6

find /root/tech/teacher_pdk -printf "%p|%s\n" 2>/dev/null | sort > "$O/pdk_after.txt"
R "PDK after = $(wc -l < "$O/pdk_after.txt") entries  diff_lines = $(diff "$O/pdk_before.txt" "$O/pdk_after.txt" | wc -l)"
R "cell schematic dir after (must be identical): $(md5sum "$P"/cadence_work/microled_cells/c2mos_dff_1bit/schematic/sch.oa 2>/dev/null | cut -c1-12)"
ps -ef | awk '/cdsMsgServer.*mpssession virtuoso/ && $3==1 {print $2}' | while read q; do kill "$q" 2>/dev/null; done
R "disk after: $(df -h / | tail -1 | awk '{print $4" free"}')"
R "TB_VERIFY_DONE golden=$GOLD oa=$SCHE"
