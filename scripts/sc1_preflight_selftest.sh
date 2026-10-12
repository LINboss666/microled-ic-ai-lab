#!/bin/bash
# SCAN-1 R2A / R1-C: regression matrix for the preflight supply gate.
#
#   bash scripts/sc1_preflight_selftest.sh [static|full]
#
#   static -- no simulator is involved. Refusal cases must be refused in the static layer, and
#            acceptance cases are checked with the preflight static probe, which exits 7 and
#            prints no circuit verdict.
#   full   -- the same matrix plus the real operating-point phase on the teacher PDK; an
#             acceptance case only counts as PASS when Spectre produced the data.
#
# Why the shape changed: the previous revision mapped rc=0 to PASS and ANY other rc to FAIL, so a
# missing file (rc 8), an awk crash, or a dead licence could make a "negative" case look correct.
# Every case here declares its expected exit code, the stage that must refuse it, the reason token
# that must appear, whether the simulator may be reached, and the physical connection that was
# actually altered. Fault injection uses LOCAL COPIES of the checker -- the committed checker is
# never broken to prove the gate closes.
set -u
PROJ=${PROJ:-/root/microled_ai_project}
cd "$PROJ" || { echo "HARNESS_ERROR: cannot cd $PROJ"; exit 8; }
MODE=${1:-static}
PF="$PROJ/scripts/tb_preflight.sh"
REAL_AWK="$PROJ/scripts/sc1_supply_check.awk"
D="$PROJ/cadence_work/sc1_sim/selftest_r2a"
rm -rf "$D"; mkdir -p "$D/decks" "$D/logs" "$D/fault"
CSV="$D/sc1_r2a_preflight.csv"
FAILS=0; BLOCKED=0; NOTRUN=0; NCASE=0

# ------------------------------------------------------------------ case records
rows=""
add_row() { rows="$rows$1"$'\n'; }
csvq() { local s=$1; s=${s//\"/\"\"}; printf '"%s"' "$s"; }
row() { # 16 columns, every one quoted. ${10}..${16} must keep their braces: "$10" is $1 followed
  # by a zero, which is exactly how the first draft of this file wrote case ids into column 10.
  printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
    "$(csvq "$1")" "$(csvq "$2")" "$(csvq "$3")" "$(csvq "$4")" "$(csvq "$5")" "$(csvq "$6")" \
    "$(csvq "$7")" "$(csvq "${8}")" "$(csvq "${9}")" "$(csvq "${10}")" "$(csvq "${11}")" \
    "$(csvq "${12}")" "$(csvq "${13}")" "$(csvq "${14}")" "$(csvq "${15}")" "$(csvq "${16}")"
}

# ------------------------------------------------------------------- synthetic cells
CELL='subckt dut (in out vdd18 vdd33 vss)
  mp (out in vdd33 vdd33) p33 l=3.5e-7 w=5e-6
  mn (out in vss vss) n33 l=3.5e-7 w=5e-6
ends dut
subckt dut18 (in out vdd vss)
  mp (out in vdd vdd) p18 l=2e-7 w=4e-6
  mn (out in vss vss) n18 l=2e-7 w=2e-6
ends dut18
subckt buf33 (in out vdd33 vss)
  mpb (out in vdd33 vdd33) p33 l=3.5e-7 w=8e-6
  mnb (out in vss vss) n33 l=3.5e-7 w=4e-6
ends buf33
subckt mid (in out vdd18 vdd33 vss)
  Xm1 (in nb vdd18 vss) dut18
  Xm2 (nb out vdd33 vss) buf33
ends mid'

mkdeck() { # name  body
  printf '%s\n' "$2" > "$D/decks/$1.scs"
  echo "$D/decks/$1.scs"
}
HDR='simulator lang=spectre insensitive=yes
include "$QODER_PDK_LIB" section=tt'

# pf_run CID CLASS REQUIRES_SIM DECK CLI_MODE VEXP MAP EXPECT_RC EXPECT_STAGE EXPECT_TOKEN CONNECTION
pf_run() {
  local cid="$1" class="$2" sim="$3" deck="$4" clim="$5" vexp="$6" map="$7"
  local exp_rc="$8" exp_stage="$9" exp_tok="${10}" conn="${11}" awk_override="${12:-}"
  local tag="$cid" log="$D/logs/$cid.log" rc=0 out=""
  NCASE=$((NCASE+1))
  if [ "$MODE" = static ] && [ "$class" = "circuit_positive" ]; then
    exp_rc=7; exp_stage=static_gate; exp_tok="STATIC_PROBE: accepted"
  fi
  # the wrapper is always executed, even for a deck path that does not exist: the harness error
  # has to come from the tool itself, not from this selftest deciding not to call it.
  if [ -n "$awk_override" ]; then
    if [ "$clim" = contract ]; then
      SUPPLY_CHECK_AWK="$awk_override" PREFLIGHT_STATIC_PROBE=$([ "$MODE" = static ] && [ "$class" = circuit_positive ] && echo 1 || echo 0) \
        bash "$PF" "$deck" "$vexp" "$tag" "$map" > "$log" 2>&1; rc=$?
    else
      SUPPLY_CHECK_AWK="$awk_override" bash "$PF" "$deck" "$vexp" "$tag" > "$log" 2>&1; rc=$?
    fi
  elif [ "$clim" = contract ]; then
    PREFLIGHT_STATIC_PROBE=$([ "$MODE" = static ] && [ "$class" = circuit_positive ] && echo 1 || echo 0) \
      bash "$PF" "$deck" "$vexp" "$tag" "$map" > "$log" 2>&1; rc=$?
  else
    PREFLIGHT_STATIC_PROBE=$([ "$MODE" = static ] && [ "$class" = circuit_positive ] && echo 1 || echo 0) \
      bash "$PF" "$deck" "$vexp" "$tag" > "$log" 2>&1; rc=$?
  fi
  out=$(cat "$log" 2>/dev/null)
  # judge only a complete log: an unfinished write is a harness fault, never a circuit verdict
  log_complete=yes
  printf '%s\n' "$out" | grep -q '^TESTBENCH_PREFLIGHT:' || log_complete=no
  local act_stage act_reject sim_called verdict why_note=""
  act_stage=$(printf '%s\n' "$out" | awk '/^PREFLIGHT_STAGE=/{sub(/^PREFLIGHT_STAGE=/,"");print;exit}')  act_reject=$(printf '%s\n' "$out" | grep -m1 '^PREFLIGHT_REJECT:' | sed 's/^PREFLIGHT_REJECT: //')
  [ -n "$act_reject" ] || act_reject=$(printf '%s\n' "$out" | grep -m1 '^PREFLIGHT_HARNESS_ERROR:' | sed 's/.*: //')
  [ -n "$act_reject" ] || act_reject=$(printf '%s\n' "$out" | grep -m1 '^CIRCUIT_VERDICT:' | sed 's/^CIRCUIT_VERDICT: //')
  [ -n "$act_reject" ] || act_reject=$(printf '%s\n' "$out" | grep -m1 '^TESTBENCH_PREFLIGHT:' | sed 's/^TESTBENCH_PREFLIGHT: //')
  case "$out" in *spectre_rc=*) sim_called=yes ;; *) sim_called=no ;; esac
  verdict=PASS
  # expected_rc may name an explicit set ("1,2"): a crashed awk exits 2 under newer gawk and 1
  # under the guest's gawk 3.1.7, and both are the same tool fault rather than a circuit verdict.
  rc_ok=no
  oldifs=$IFS; IFS=,
  for want_rc in $exp_rc; do [ "$rc" = "$want_rc" ] && rc_ok=yes; done
  IFS=$oldifs
  [ "$rc_ok" = yes ] || { verdict=FAIL; why_note="rc=$rc not in allowed set $exp_rc"; }
  if [ "$verdict" = PASS ] && [ -n "$exp_stage" ]; then
    [ "$act_stage" = "$exp_stage" ] || { verdict=FAIL; why_note="stage=${act_stage:-none} want=$exp_stage"; }
  fi
  if [ "$verdict" = PASS ] && [ -n "$exp_tok" ]; then
    # '+' separates tokens that must ALL appear: the refusal reason plus the injected fault text, so
    # a case cannot be satisfied by a generic message that happens to mention the same stage.
    missing=""
    oldifs=$IFS; IFS='+'
    for tk in $exp_tok; do case "$out" in *"$tk"*) ;; *) missing="$missing+$tk" ;; esac; done
    IFS=$oldifs
    if [ -n "$missing" ]; then verdict=FAIL; why_note="token absent:${missing#+}"; fi
  fi
  # a refusal must never have reached the simulator, and a tool fault must never look like a
  # circuit judgement: both are structural assertions, not expectations about one deck.
  if [ "$verdict" = PASS ] && [ "$class" != circuit_positive ] && [ "$sim_called" = yes ] && [ "$exp_rc" != 0 ]; then
    verdict=FAIL; why_note="simulator was reached for a static-layer refusal"
  fi
  if [ "$verdict" = PASS ] && [ "$class" = tool_fault ] && [ "$act_stage" != supply_contract ]; then
    verdict=FAIL; why_note="tool fault refused at the wrong stage: ${act_stage:-none}"
  fi
  if [ "$verdict" = PASS ] && [ "$log_complete" = no ]; then
    verdict=FAIL; why_note="HARNESS_ERROR log_incomplete_no_final_verdict_line"
  fi
  # an acceptance case whose simulator phase produced nothing is BLOCKED, not FAIL and not PASS
  if [ "$verdict" != PASS ] && [ "$class" = circuit_positive ] && [ "$MODE" = full ]; then
    case "$out" in
      *PREFLIGHT_STAGE=operating_point_sim*) verdict=BLOCKED; why_note="simulator environment produced no operating point" ;;
    esac
  fi
  case "$verdict" in
    PASS) ;;
    BLOCKED) BLOCKED=$((BLOCKED+1));;
    *) FAILS=$((FAILS+1));;
  esac
  printf '%-4s %-28s exp_rc=%-2s act=%-2s stage=%-15s sim=%-3s %s %s\n' "$cid" "$class" "$exp_rc" "$rc" \
    "${act_stage:-none}" "$sim_called" "$verdict" "$why_note"
  add_row "$(row "$cid" "$class" "$MODE" "$clim" "$map" "$conn" "$exp_rc" "$exp_stage" "$exp_tok" \
             "$rc" "$act_stage" "$act_reject" "$sim_called" "$verdict" "$why_note" "$log")"
}

# ---------------------------------------------------------------- deck generators
BASE_CONTRACT='vdd18=1.8 vdd33=3.3 vss=0'
DUAL=$(mkdeck dual_ok "$HDR
$CELL
V18 (vdd18 0) vsource dc=1.8
V33 (vdd33 0) vsource dc=3.3
Vss (vss 0) vsource dc=0
Vi (in 0) vsource dc=0
X1 (in out vdd18 vdd33 vss) dut
sw1 tran stop=1.5n maxstep=0.5n
save in out vdd18 vdd33 vss")
SINGLE=$(mkdeck single_ok "$HDR
$CELL
Vdd (vdd 0) vsource dc=1.8
Vss (vss 0) vsource dc=0
Vi (in 0) vsource dc=0
X1 (in out vdd vss) dut18
sw1 tran stop=1.5n maxstep=0.5n
save in out vdd vss")

# ================================================================= circuit positives
pf_run p01 circuit_positive yes "$SINGLE" legacy 1.8 "-" 0 "" "TESTBENCH_PREFLIGHT: PASS" "none: legacy single-rail bench"
pf_run p02 circuit_positive yes "$DUAL" contract 1.8 "$BASE_CONTRACT" 0 "" "TESTBENCH_PREFLIGHT: PASS" "none: correctly supplied dual-rail bench"
NEST=$(mkdeck nest_ok "$HDR
$CELL
V18 (vdd18 0) vsource dc=1.8
V33 (vdd33 0) vsource dc=3.3
Vss (vss 0) vsource dc=0
Vi (in 0) vsource dc=0
Xm (in out vdd18 vdd33 vss) mid
sw1 tran stop=1.5n maxstep=0.5n
save in out vdd18 vdd33 vss")
pf_run p03 circuit_positive yes "$NEST" contract 1.8 "$BASE_CONTRACT dut18.vdd=1.8" 0 "" "descendants=2" "none: hierarchical mid -> dut18 + buf33"
N0=$(mkdeck node0_ok "$HDR
$CELL
V18 (vdd18 0) vsource dc=1.8
V33 (vdd33 0) vsource dc=3.3
Vi (in 0) vsource dc=0
X1 (in out vdd18 vdd33 0) dut
sw1 tran stop=1.5n maxstep=0.5n
save in out vdd18 vdd33")
pf_run p04 circuit_positive yes "$N0" contract 1.8 "$BASE_CONTRACT" 0 "" "reference node 0" "vss port tied straight to node 0"
ZERO18=$(sed 's/V18 (vdd18 0) vsource dc=1.8/V18 (vdd18 0) vsource dc=0/' "$DUAL" > "$D/decks/p05.scs"; echo "$D/decks/p05.scs")
pf_run p05 circuit_positive yes "$ZERO18" contract 1.8 "vdd18=0 vdd33=3.3 vss=0" 0 "" "SUPPLY_GATE: PASS" "vdd18 source clamped to 0 V: declared power-down"
ZERO33=$(sed 's/V33 (vdd33 0) vsource dc=3.3/V33 (vdd33 0) vsource dc=0/' "$DUAL" > "$D/decks/p06.scs"; echo "$D/decks/p06.scs")
pf_run p06 circuit_positive yes "$ZERO33" contract 1.8 "vdd18=1.8 vdd33=0 vss=0" 0 "" "SUPPLY_GATE: PASS" "vdd33 source clamped to 0 V: declared power-down"
MIX=$(mkdeck mix_ok "$HDR
$CELL
V18 (vdd 0) vsource dc=1.8
V18b (vdd18 0) vsource dc=1.8
V33 (vdd33 0) vsource dc=3.3
Vss (vss 0) vsource dc=0
Vi (in 0) vsource dc=0
X0 (in nb vdd vss) dut18
X1 (nb out vdd18 vdd33 vss) dut
sw1 tran stop=1.5n maxstep=0.5n
save in nb out vdd vdd18 vdd33 vss")
pf_run p07 circuit_positive yes "$MIX" contract 1.8 "vdd=1.8 vdd18=1.8 vdd33=3.3 vss=0" 0 "" "SUPPLY_GATE: PASS" "core-domain and high-domain instances side by side"

# ================================================================= circuit negatives
pf_run n01 circuit_negative no "$(sed 's/^V33 (vdd33 0) vsource dc=3.3/V33 (unusednet 0) vsource dc=3.3/' "$DUAL" > "$D/decks/n01.scs"; echo "$D/decks/n01.scs")" \
  contract 1.8 "$BASE_CONTRACT" 1 supply_contract "has no independent source" "V33 moved off net vdd33 onto unusednet"
pf_run n02 circuit_negative no "$(sed 's/V33 (vdd33 0) vsource dc=3.3/V33 (vdd33 0) vsource dc=2.5/' "$DUAL" > "$D/decks/n02.scs"; echo "$D/decks/n02.scs")" \
  contract 1.8 "$BASE_CONTRACT" 1 supply_contract "driven 2.5 V" "vdd33 source value changed 3.3 -> 2.5"
pf_run n03 circuit_negative no "$(sed 's/X1 (in out vdd18 vdd33 vss) dut/X1 (in out vdd33 vdd18 vss) dut/' "$DUAL" > "$D/decks/n03.scs"; echo "$D/decks/n03.scs")" \
  contract 1.8 "$BASE_CONTRACT" 1 supply_contract "contract vdd18=1.8" "vdd18/vdd33 pins swapped on the instance"
pf_run n04 circuit_negative no "$(sed 's/Vss (vss 0) vsource dc=0/Vss (vss 0) vsource dc=0.1/' "$DUAL" > "$D/decks/n04.scs"; echo "$D/decks/n04.scs")" \
  contract 1.8 "$BASE_CONTRACT" 1 supply_contract "driven 0.1 V" "vss lifted off the reference by 0.1 V"
pf_run n05 circuit_negative no "$(printf '%s\n' "$HDR
Vdd (vdd 0) vsource dc=1.8
Vss (vss 0) vsource dc=0
Vi (in 0) vsource dc=0
mp (out in vdd vdd) p18 l=2e-7 w=4e-6
mn (out in vss vss) n18 l=2e-7 w=2e-6
sw1 tran stop=1.5n maxstep=0.5n" > "$D/decks/n05.scs"; echo "$D/decks/n05.scs")" \
  contract 1.8 "vdd=1.8 vss=0" 1 supply_contract "no top-level instance" "deck holds only top-level devices, no instance to certify"
pf_run n06 circuit_negative no "$(printf '%s\n' "$HDR
$CELL
V18 (vdd18 0) vsource dc=1.8
V33 (vdd33 0) vsource dc=3.3
Vss (vss 0) vsource dc=0
X1 (in out vdd18 vdd33 vss) dut
Xbad (a b c d e) master_never_included
sw1 tran stop=1.5n maxstep=0.5n" > "$D/decks/n06.scs"; echo "$D/decks/n06.scs")" \
  contract 1.8 "$BASE_CONTRACT" 1 supply_contract "port list unresolved" "an extra instance of a master the checker never read"
pf_run n07 circuit_negative no "$DUAL" contract 1.8 "vdd18=1.8 vdd33=3.3 vss=garbage" \
  1 supply_contract "not a finite number" "contract value written as garbage, deck untouched"
pf_run n08 circuit_negative no "$(sed 's/V18 (vdd18 0) vsource dc=1.8/V18 (vdd18 0) vsource dc=1.8\nVtie (vdd18 vdd33) vsource dc=0/' "$DUAL" > "$D/decks/n08.scs"; echo "$D/decks/n08.scs")" \
  contract 1.8 "$BASE_CONTRACT" 1 supply_contract "forces 0 V" "an added 0 V source ties the 1.8 and 3.3 rails together"
pf_run n09 circuit_negative no "$DUAL" contract 1.8 "vdd18=1.8 vss=0" \
  1 supply_contract "not covered by the contract" "contract entry for vdd33 removed while the cell still exposes it"
pf_run n10 circuit_negative no "$DUAL" contract 1.8 "$BASE_CONTRACT vdd9=9" \
  1 supply_contract "matches no instance port" "an extra contract entry no port uses"
COLLIDE=$(mkdeck collide "$HDR
$CELL
subckt midc (in out vdd18 vss)
  mp2 (nb in vdd33 vdd33) p33 l=3.5e-7 w=8e-6
  Xm2 (nb out vdd33 vss) buf33
ends midc
V18 (vdd18 0) vsource dc=1.8
V33 (vdd33 0) vsource dc=3.3
Vss (vss 0) vsource dc=0
Xm (in out vdd18 vss) midc
sw1 tran stop=1.5n maxstep=0.5n")
pf_run n11 circuit_negative no "$COLLIDE" contract 1.8 "$BASE_CONTRACT" \
  1 supply_contract "refusing to guess" "a midc-local net named vdd33 while a global vdd33 rail also exists"
# R2B: the reviewer's uncertified child substrate, driven through the wrapper rather than the awk
FLOATKIDS='subckt leafc (in out vdd33 vss)
  mpleaf (out in vdd33 vdd33) p33 l=3.5e-7 w=5e-6
  mnleaf (out in vss vss) n33 l=3.5e-7 w=5e-6
ends leafc
subckt topc (in out vdd18 vdd33 vss)
  Xchild (in out vdd33 floating_ground) leafc
ends topc'
F13=$(mkdeck float_child "$HDR
$CELL
$FLOATKIDS
V18 (vdd18 0) vsource dc=1.8
V33 (vdd33 0) vsource dc=3.3
Vss (vss 0) vsource dc=0
Vi (in 0) vsource dc=0
X1 (in out vdd18 vdd33 vss) topc
sw1 tran stop=1.5n maxstep=0.5n
save in out vdd18 vdd33 vss")
pf_run n13 circuit_negative no "$F13" contract 1.8 "$BASE_CONTRACT" 1 supply_contract "is not certified" "child vss tied to a mid-level internal node (floating_ground) instead of the parent vss port"
MAPPEDKIDS=$(printf '%s' "$FLOATKIDS" | sed 's/floating_ground/vss/')
F14=$(mkdeck mapped_child "$HDR
$CELL
$MAPPEDKIDS
V18 (vdd18 0) vsource dc=1.8
V33 (vdd33 0) vsource dc=3.3
Vss (vss 0) vsource dc=0
Vi (in 0) vsource dc=0
X1 (in out vdd18 vdd33 vss) topc
sw1 tran stop=1.5n maxstep=0.5n
save in out vdd18 vdd33 vss")
pf_run p08 circuit_positive yes "$F14" contract 1.8 "$BASE_CONTRACT" 0 "" "SUPPLY_GATE: PASS" "the same deck with the child wired through the parent vss port"
# the project's own legacy negative bench must still be refused, at the static parse stage
LEGNEG="$PROJ/spectre/preflight_negative_vss_float.scs"
pf_run n12 circuit_negative no "$LEGNEG" legacy 1.8 "-" 1 static_parse "NOT tied to reference node 0" "committed negative bench: vss left floating"

# ============================================================ tool fault injection
mkfault() { # name  body
  printf '%s\n' "$2" > "$D/fault/$1"
  echo "$D/fault/$1"
}
F_SYNTAX=$(mkfault syntax_error.awk "$(cat "$REAL_AWK")
if (")                                   # copy of the real checker, broken on purpose
F_EMPTY=$(mkfault empty.awk 'BEGIN { exit 0 }')
F_PASSFAIL=$(mkfault pass_then_nonzero.awk 'BEGIN { print "SUPPLY_OK stub"; print "SUPPLY_NET vdd33=3.3"; print "SUPPLY_INSTANCES top=1 descendants=0 checked=1 internal=0 masters=0"; print "SUPPLY_RESULT PASS"; exit 3 }')
F_NOTOK=$(mkfault no_result_token.awk 'BEGIN { print "SUPPLY_OK stub"; print "SUPPLY_NET vdd33=3.3"; print "SUPPLY_INSTANCES top=1 descendants=0 checked=1 internal=0 masters=0"; print "SUPPLY_RESULT UNKNOWN"; exit 0 }')
F_DOUBLE=$(mkfault double_pass.awk 'BEGIN { print "SUPPLY_OK stub"; print "SUPPLY_NET vdd33=3.3"; print "SUPPLY_INSTANCES top=1 descendants=0 checked=1 internal=0 masters=0"; print "SUPPLY_RESULT PASS"; print "SUPPLY_RESULT PASS"; exit 0 }')
F_ZERO=$(mkfault zero_checked.awk 'BEGIN { print "SUPPLY_NET vdd33=3.3"; print "SUPPLY_INSTANCES top=3 descendants=0 checked=0 internal=0 masters=0"; print "SUPPLY_RESULT PASS"; exit 0 }')
F_MISMATCH=$(mkfault count_mismatch.awk 'BEGIN { print "SUPPLY_OK a"; print "SUPPLY_NET vdd33=3.3"; print "SUPPLY_INSTANCES top=1 descendants=0 checked=9 internal=0 masters=0"; print "SUPPLY_RESULT PASS"; exit 0 }')
F_INTOKN=$(mkfault internal_mismatch.awk 'BEGIN { print "SUPPLY_OK a"; print "SUPPLY_NET vdd33=3.3"; print "SUPPLY_INSTANCES top=1 descendants=0 checked=1 internal=4 masters=0"; print "SUPPLY_RESULT PASS"; exit 0 }')
F_DIRTY=$(mkfault pass_with_fail.awk 'BEGIN { print "SUPPLY_OK a"; print "SUPPLY_FAIL something inconsistent"; print "SUPPLY_NET vdd33=3.3"; print "SUPPLY_INSTANCES top=1 descendants=0 checked=1 internal=0 masters=0"; print "SUPPLY_RESULT PASS"; exit 0 }')
F_GARBAGE=$(mkfault garbled.awk 'BEGIN { print "this is not a checker report at all"; exit 0 }')

pf_run t01 tool_fault no "$DUAL" contract 1.8 "$BASE_CONTRACT" 1,2 supply_contract "checker_exit=+syntax error" "no deck change: awk copy of the checker given a syntax error" "$F_SYNTAX"
pf_run t02 tool_fault no "$DUAL" contract 1.8 "$BASE_CONTRACT" 1 supply_contract "checker_empty_stdout" "no deck change: checker stub prints nothing and exits 0" "$F_EMPTY"
pf_run t03 tool_fault no "$DUAL" contract 1.8 "$BASE_CONTRACT" 1 supply_contract "checker_exit=3" "no deck change: stub prints PASS then exits 3" "$F_PASSFAIL"
pf_run t04 tool_fault no "$DUAL" contract 1.8 "$BASE_CONTRACT" 1 supply_contract "no_unique_PASS_token" "no deck change: stub prints no result token" "$F_NOTOK"
pf_run t05 tool_fault no "$DUAL" contract 1.8 "$BASE_CONTRACT" 1 supply_contract "result_token_count=2" "no deck change: stub prints two PASS lines" "$F_DOUBLE"
pf_run t06 tool_fault no "$DUAL" contract 1.8 "$BASE_CONTRACT" 1 supply_contract "zero_supply_checks_performed" "no deck change: stub reports checked=0" "$F_ZERO"
pf_run t07 tool_fault no "$DUAL" contract 1.8 "$BASE_CONTRACT" 1 supply_contract "count_mismatch_checked=9_vs_supply_ok=1" "no deck change: stub count disagrees with its own lines" "$F_MISMATCH"
pf_run t08 tool_fault no "$DUAL" contract 1.8 "$BASE_CONTRACT" 1 supply_contract "count_mismatch_internal=4_vs_supply_internal=0" "no deck change: internal count disagrees" "$F_INTOKN"
pf_run t09 tool_fault no "$DUAL" contract 1.8 "$BASE_CONTRACT" 1 supply_contract "pass_with_fail_detail" "no deck change: stub prints PASS alongside a FAIL detail" "$F_DIRTY"
pf_run t10 tool_fault no "$DUAL" contract 1.8 "$BASE_CONTRACT" 1 supply_contract "result_token_count=0" "no deck change: stub prints an unrecognisable report" "$F_GARBAGE"
pf_run h01 harness_error no "$DUAL" contract 1.8 "$BASE_CONTRACT" 8 inputs "checker_missing" "no deck change: SUPPLY_CHECK_AWK points at a file that does not exist" "$D/fault/not_installed.awk"
pf_run h02 harness_error no "$PROJ/spectre/no_such_deck.scs" contract 1.8 "$BASE_CONTRACT" 8 inputs "netlist_not_found" "no deck: the netlist path does not exist"

# ==================================================================== read-back
printf '%s\n' "$(row caseid class mode cli supply_map connection_changed expected_rc expected_stage \
  expected_token actual_rc actual_stage actual_reason simulator_called verdict evidence_note log_path)" > "$CSV"
printf '%s' "$rows" >> "$CSV"
echo "MATRIX_CSV=$CSV  cases=$NCASE"
python "$PROJ/scripts/sc1_csv_audit.py" "$CSV" || { echo "PREFLIGHT_VALIDATION: FAIL (CSV read-back)"; exit 6; }
echo "PREFLIGHT_MODE=$MODE cases=$NCASE fails=$FAILS blocked=$BLOCKED"
if [ "$FAILS" != 0 ]; then echo "PREFLIGHT_VALIDATION: FAIL ($FAILS of $NCASE)"; exit 6; fi
if [ "$BLOCKED" != 0 ]; then echo "PREFLIGHT_VALIDATION: BLOCKED ($BLOCKED simulator-side)"; exit 5; fi
echo "PREFLIGHT_VALIDATION: PASS ($NCASE/$NCASE in $MODE mode)"
exit 0
