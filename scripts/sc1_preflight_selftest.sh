#!/bin/bash
# SCAN-1 R1: regression matrix for the dual-rail preflight contract.
#
#   bash scripts/sc1_preflight_selftest.sh
#
# Each case is a generated deck plus the expected verdict. The point is not "the new mode is
# happy": it is that the new mode still REFUSES broken rails, that the old single-rail call path
# behaves exactly as before, and that a DECLARED 0 V supply (a power-down test condition) is
# accepted while an undeclared or wrong one is not. Case 09 changes a real connection in an
# otherwise correct dual-rail deck, so it cannot be satisfied by editing an expected number.
set -u
PROJ=/root/microled_ai_project
cd "$PROJ" || exit 8
. ./skill/cad_env.sh >/dev/null 2>&1 || { echo "FATAL cad_env"; exit 8; }
PF="$PROJ/scripts/tb_preflight.sh"
RS="$PROJ/scripts/run_spectre.sh"
D="$PROJ/cadence_work/sc1_sim/selftest"; mkdir -p "$D"
CSV="$D/preflight_matrix.csv"
echo "case,description,mode,expected,actual,rc,verdict" > "$CSV"
FAILS=0

CELL='subckt dut (in out vdd18 vdd33 vss)
  parameters l=3.5e-7 w=5e-6
  mp (out in vdd33 vdd33) p33 l=l w=w
  mn (out in vss vss) n33 l=l w=w
ends dut
subckt dut18 (in out vdd vss)
  mp (out in vdd vdd) p18 l=2e-7 w=4e-6
  mn (out in vss vss) n18 l=2e-7 w=2e-6
ends dut18'

mk() {  # file  body
  printf '%s\n' "$2" > "$1"
}
run() {  # file expected description mode vdd tag supply_map caseid
  local f="$1" exp="$2" desc="$3" mode="$4" vexp="$5" tag="$6" map="$7" cid="$8" out rc act
  if [ "$map" = "-" ]; then
    out=$(bash "$PF" "$f" "$vexp" "$tag" 2>&1)          # legacy 3-argument interface
  else
    out=$(bash "$PF" "$f" "$vexp" "$tag" "$map" 2>&1)   # dual-rail contract
  fi
  rc=$?
  if [ "$rc" = "0" ]; then act=PASS; else act=FAIL; fi
  local v=PASS
  [ "$act" = "$exp" ] || { v=FAIL; FAILS=$((FAILS+1)); }
  printf '%-3s %-52s exp=%-4s act=%-4s rc=%-3s %s\n' "$7" "$desc" "$exp" "$act" "$rc" "$v"
  echo "\"$7\",$desc,$mode,$exp,$act,$rc,$v" >> "$CSV"
}

# 01 old single-rail interface still passes (1.8 V core inverter only)
F="$D/c01_single_rail_ok.scs"
mk "$F" "simulator lang=spectre insensitive=yes
include \"\$QODER_PDK_LIB\" section=tt
$CELL
Vdd (vdd 0) vsource dc=1.8
Vss (vss 0) vsource dc=0
Vi (in 0) vsource dc=0
X1 (in out vdd vss) dut18
sw1 tran stop=1.5n maxstep=0.5n
save in out vdd vss"
run "$F" PASS "legacy single-rail bench, old CLI form" legacy 1.8 c01 - 01

# 02 legacy negative: the project's own floating-vss bench must still be refused
F="$PROJ/spectre/preflight_negative_vss_float.scs"
[ -r "$F" ] || { echo "MISSING NEGATIVE BENCH $F -> cannot validate the legacy refusal path"; exit 8; }
run "$F" FAIL "legacy negative: project floating-vss bench" legacy 1.8 c02 - 02

# 03 dual-rail correct contract passes
F="$D/c03_dual_ok.scs"
mk "$F" "simulator lang=spectre insensitive=yes
include \"\$QODER_PDK_LIB\" section=tt
$CELL
V18 (vdd18 0) vsource dc=1.8
V33 (vdd33 0) vsource dc=3.3
Vss (vss 0) vsource dc=0
Vi (in 0) vsource dc=0
X1 (in out vdd18 vdd33 vss) dut
sw1 tran stop=1.5n maxstep=0.5n
save in out vdd18 vdd33 vss"
run "$F" PASS "dual-rail 1.8/3.3 declared correctly" contract 1.8 c03 "vdd18=1.8 vdd33=3.3 vss=0" c03

# 04 one supply has no source at all
F="$D/c04_missing_rail.scs"
sed 's/^V33 (vdd33 0) vsource dc=3.3$/V33 (unusednet 0) vsource dc=3.3/' "$D/c03_dual_ok.scs" > "$F"
run "$F" FAIL "vdd33 left unconnected to any source" contract 1.8 c04 "vdd18=1.8 vdd33=3.3 vss=0" c04

# 05 wrong value on one rail
F="$D/c05_wrong_value.scs"
sed 's/V33 (vdd33 0) vsource dc=3.3/V33 (vdd33 0) vsource dc=2.5/' "$D/c03_dual_ok.scs" > "$F"
run "$F" FAIL "vdd33 driven to 2.5 V against a 3.3 V contract" contract 1.8 c05 "vdd18=1.8 vdd33=3.3 vss=0" c05

# 06 supply ports swapped between instances is caught (vdd18 net driven to 3.3)
F="$D/c06_ports_swapped.scs"
sed 's/X1 (in out vdd18 vdd33 vss) dut/X1 (in out vdd33 vdd18 vss) dut/' "$D/c03_dual_ok.scs" > "$F"
run "$F" FAIL "vdd18/vdd33 pins swapped on the instance" contract 1.8 c06 "vdd18=1.8 vdd33=3.3 vss=0" c06

# 07 reference node missing: vss tied to a nonzero source
F="$D/c07_no_reference.scs"
sed 's/Vss (vss 0) vsource dc=0/Vss (vss 0) vsource dc=0.1/' "$D/c03_dual_ok.scs" > "$F"
run "$F" FAIL "vss lifted off the reference by 0.1 V" contract 1.8 c07 "vdd18=1.8 vdd33=3.3 vss=0" c07

# 08 declared power-down is a legal condition, not an automatic failure
F="$D/c08_declared_zero_core.scs"
sed 's/V18 (vdd18 0) vsource dc=1.8/V18 (vdd18 0) vsource dc=0/' "$D/c03_dual_ok.scs" > "$F"
run "$F" PASS "declared vdd18=0 with vdd33=3.3 (power-down scenario)" contract 1.8 c08 "vdd18=0 vdd33=3.3 vss=0" c08
F="$D/c09_declared_zero_io.scs"
sed 's/V33 (vdd33 0) vsource dc=3.3/V33 (vdd33 0) vsource dc=0/' "$D/c03_dual_ok.scs" > "$F"
run "$F" PASS "declared vdd33=0 with vdd18=1.8 (power-down scenario)" contract 1.8 c09 "vdd18=1.8 vdd33=0 vss=0" c09

# 10 real connection change in a correct deck: core rail tied to the 3.3 net (NOT an expected edit)
F="$D/c10_real_break.scs"
sed 's/V18 (vdd18 0) vsource dc=1.8/V18 (vdd18 0) vsource dc=1.8\nVx (vdd18 vdd33) vsource dc=0/' "$D/c03_dual_ok.scs" > "$F"
run "$F" FAIL "core rail shorted to the 3.3 V net by an extra source" contract 1.8 c10 "vdd18=1.8 vdd33=3.3 vss=0" c10

# 11 unmapped supply-looking port must not pass silently
F="$D/c11_unmapped_port.scs"
cp "$D/c03_dual_ok.scs" "$F"
run "$F" FAIL "contract omits vdd33 while the cell exposes it" contract 1.8 c11a "vdd18=1.8 vss=0" c11a

echo "PREFLIGHT_VALIDATION: $([ "$FAILS" = 0 ] && echo PASS || echo "FAIL cases=$FAILS")"
echo "MATRIX_CSV=$CSV"
column -s, -t "$CSV" 2>/dev/null | head -14
[ "$FAILS" = 0 ] || exit 6
exit 0
