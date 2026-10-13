#!/bin/bash
# sc1_s1_r2d_regression.sh -- independent S1 regression entry, prepared for the authorised session.
#
#   bash scripts/sc1_s1_r2d_regression.sh                                # dry run (default)
#   RUN=1 bash scripts/sc1_s1_r2d_regression.sh                          # refused: exit 5, nothing runs
#   RUN=1 QODER_SIM_AUTHORISED=1 bash scripts/sc1_s1_r2d_regression.sh    # future session only
#
# This replaces the first draft, which the cloud reviewer showed to be broken on its own future path.
# Fixed here, item by item (each item was reproduced against the draft before it was changed):
#  1. required inputs are checked with -f: they are files, and `[ -d netlist ]` always failed;
#  2. the reader's exit status no longer travels through a variable assigned inside $(...) -- command
#     substitution runs in a child shell, so the parent never saw READ_RC and, under set -u, died on
#     an unbound variable (measured: rc 127 with a mock reader exiting 3). The read now happens in
#     this shell, returns its status directly, and the status is judged BEFORE any numeric conversion;
#  3. a non-zero preflight stops that deck and the runner is never reached; the three failure kinds
#     are recorded apart as PRECHECK_FAIL / SIM_FAIL / READ_FAIL, and a runner success needs exit 0
#     plus exactly one complete '$LABEL: PASS' line plus 'CHECK error_hits=0' plus a readable data
#     file -- a bare ': PASS' substring is not accepted;
#  4. truth rows compare the measurement with that row's own expected state, and the row's stimulus
#     (blank, qbar) is read back against its label; any wrong polarity exits non-zero, so a detected
#     fault can no longer hide a failing normal row;
#  5. the stimulus is the historical one from scripts/sc1_s1r.sh, copied verbatim (clock delay=50n
#     rise=1n fall=1n period=100n width=50n, the data and blank PWLs, stop=900n maxstep=1n
#     method=traponly), the DC truth decks drive the gate only (no DFF instance with floating d/clk
#     behind an ideal source), and the negative is the same real BLANK-to-vss rewire;
#  6. no literal backslash inside the window list and no hand-quoted CSV rows -- rows are accumulated
#     as TAB-separated text and written by scripts/sc1_csv_writer.py, which refuses a ragged row;
#  7. the model library is bound through the project's own convention (skill/cad_env.sh then the
#     git-ignored spectre/pdk_local.env). If neither resolves, the authorised path stops with BLOCKED
#     before generating or running anything, instead of emitting a deck with an undefined variable.
#
# The future execution path is exercised only through the injectable command hooks below, with mocks
# and synthetic data (scripts/sc1_r2d1_entry_selftest.py). That evidence is labelled SYNTHETIC/MOCK
# and is not an S1 circuit regression.
set -u
PROJ=${PROJ:-/root/microled_ai_project}
cd "$PROJ" || { echo "HARNESS_ERROR: cannot cd $PROJ"; exit 8; }
RUN=${RUN:-0}
AUTH=${QODER_SIM_AUTHORISED:-0}
SECTION=${SECTION:-tt}
VDDC=${VDDC:-1.8}
VOL=${VOL:-0.9}                 # historical decision level, kept identical on purpose
D=${S1REG_DIR:-"$PROJ/cadence_work/sc1_sim/s1_reg"}
GOLD="$PROJ/spectre/C2MOS_DFF.scs"
CELL="$PROJ/spectre/sc1_scan_gate.scs"
PF=${PF_CMD:-"bash $PROJ/scripts/tb_preflight.sh"}
RS=${RUN_CMD:-"bash $PROJ/scripts/run_spectre.sh"}
RD=${READ_CMD:-"python $PROJ/scripts/sc1_read_psf.py"}
CSVW="$PROJ/scripts/sc1_csv_writer.py"
CONTRACT="$PROJ/scripts/sc1_s1_window_contract.py"
TSV=""                          # accumulated rows, written once at the end
OUT_CSV=${OUT_CSV:-"$PROJ/results/evidence/sc1_r2d_s1_regression.csv"}
PREFLIGHT_RC=NOT_RUN
RUNNER_RC=NOT_RUN
DATA=''

# the six transient assertions exactly as scripts/sc1_s1r.sh defined them: id signal t0 t1 mode kind
WINDOWS='T1 en 400n 455n max lt
T2 en 520n 620n min gt
T3 q 410n 520n min gt
T4 en 700n 860n max lt
T5 q 700n 860n max lt'

echo "S1_R2D_REGRESSION section=$SECTION vdd_core=$VDDC decision_level_V=$VOL"

# ------------------------------------------------------------------ model binding
# Sourced in THIS shell, not inside $(...): a command substitution would throw the loaded value away
# and the runner would then be handed a deck whose include variable is undefined.
[ -f "$PROJ/skill/cad_env.sh" ] && . "$PROJ/skill/cad_env.sh" >/dev/null 2>&1
[ -f "$PROJ/spectre/pdk_local.env" ] && . "$PROJ/spectre/pdk_local.env"
if [ -n "${QODER_PDK_LIB:-}" ] && [ -f "$QODER_PDK_LIB" ]; then
  export QODER_PDK_LIB; PDKSTATE=ok
else
  PDKSTATE=missing
fi
[ "$PDKSTATE" = ok ] || echo "PDK_BINDING: NOT_RESOLVED (set QODER_PDK_LIB or spectre/pdk_local.env)"

if [ "$RUN" != "1" ] || [ "$AUTH" != "1" ]; then
  cat <<EOF
S1_R2D_REGRESSION: DRY_RUN (nothing executed). The authorised path would, in order:
  1. bind the model library (cad_env + spectre/pdk_local.env -> \${QODER_PDK_LIB}); unresolved = BLOCKED
     before any deck is written, so no deck can carry an undefined include;
  2. write two DC truth decks (gate only, qbar swept 0/${VDDC} V at blank=0 and blank=${VDDC} V), the
     transient deck with the historical stimulus verbatim, and the BLANK-rewired-to-vss negative;
  3. preflight each deck (tb_preflight.sh DECK $VDDC tag "vdd=${VDDC} vss=0"); non-zero = PRECHECK_FAIL
     and the runner is not called for that deck;
  4. run the deck only after a clean preflight; SIM_FAIL unless run_spectre exits 0 AND prints exactly
     one '\$LABEL: PASS' AND 'CHECK error_hits=0' AND a readable 'CHECK datafile=';
  5. read every row with sc1_read_psf.py, judging its exit code before any numeric conversion
     (READ_FAIL otherwise);
  6. assert truth rows against their own expected state (with blank/qbar read back against the label),
     assert the five windows against $VOL V, assert the stimulus sanity (clk high in 60n..90n) and
     require the untouched T1 assertion to reject the rewired negative;
  7. write $OUT_CSV through sc1_csv_writer.py and exit non-zero on any single failing row.
EOF
  if [ "$RUN" = "1" ] && [ "$AUTH" != "1" ]; then
    echo "  RUN=1 without QODER_SIM_AUTHORISED=1: real-circuit simulation stays paused by the user."
    [ "$PDKSTATE" = ok ] || echo "  Also BLOCKED: the model library is not resolved."
    exit 5
  fi
  exit 0
fi

[ "$PDKSTATE" = ok ] || { echo "S1_R2D_REGRESSION: BLOCKED (no model library resolved)"; exit 7; }
for f in "$GOLD" "$CELL" "$CSVW" "$CONTRACT"; do
  [ -f "$f" ] || { echo "HARNESS_ERROR: required file missing: $f"; exit 8; }
done
mkdir -p "$D" || { echo "HARNESS_ERROR: cannot create $D"; exit 8; }

fail=0
HDR='case_id	kind	raw_file	deck_file	signal	window	mode	value_V	samples_required	reader_rc	runner_rc	preflight_rc	row_verdict	note'
TSV="$HDR
"

# --------------------------------------------------------------------- deck writers
dc_deck() { # file  blank_volts   -- gate only: the truth table sweeps qbar directly, exactly as the
            # historical deck did. No DFF instance whose d/clk float behind an ideal source.
  local f="$1" bv="$2"
  { echo 'simulator lang=spectre insensitive=yes'
    echo 'include "${QODER_PDK_LIB}" section='"$SECTION"
    echo "include \"$CELL\""
    echo "Vdd (vdd 0) vsource dc=$VDDC"
    echo "Vss (vss 0) vsource dc=0"
    echo "Vb  (blank 0) vsource dc=$bv"
    echo "Vq  (qbar 0) vsource dc=0"
    echo "X2 (qbar blank en vdd vss) sc1_scan_gate"
    echo "sw dc dev=Vq param=dc start=0 stop=$VDDC step=$VDDC"
    echo 'save en blank qbar vdd vss'; } > "$f"
}

tran_deck() { # file  gate_blank_net   -- stimulus copied verbatim from scripts/sc1_s1r.sh; the only
              # difference between the positive and the negative is which net the gate's BLANK pin uses.
  local f="$1" bnet="$2"
  { echo 'simulator lang=spectre insensitive=yes'
    echo 'include "${QODER_PDK_LIB}" section='"$SECTION"
    echo "include \"$GOLD\""
    echo "include \"$CELL\""
    echo '// stimulus syntax decided by measurement on this build (spectre -h vsource):'
    echo '// type=pulse val0/val1 and type=pwl wave=[t v t v ...]; anything else would make'
    echo '// the T1..T5 windows refer to a different circuit than the one they were defined on.'
    echo "Vdd (vdd 0) vsource dc=$VDDC"
    echo "Vss (vss 0) vsource dc=0"
    echo "Vclk (clk 0) vsource type=pulse val0=0 val1=$VDDC delay=50n rise=1n fall=1n period=100n width=50n"
    echo "Vd (d 0) vsource type=pwl wave=[0 0 260n 0 270n $VDDC 620n $VDDC 630n 0 900n 0]"
    echo "Vbl (blank 0) vsource type=pwl wave=[0 $VDDC 450n $VDDC 460n 0 900n 0]"
    echo "X1 (d clk q qbar vdd vss) c2mos_dff"
    if [ "$bnet" = vss ]; then
      echo '// FAULT (the historical one, unchanged in kind): the gate BLANK pin is rewired to vss, so'
      echo '// BLANK never reaches the gate. No expected value or threshold is moved; the untouched T1'
      echo '// assertion has to reject the result.'
      echo "X2 (qbar vss en vdd vss) sc1_scan_gate"
    else
      echo "X2 (qbar blank en vdd vss) sc1_scan_gate"
    fi
    echo "sw1 tran stop=900n maxstep=1n method=traponly"
    echo 'save clk d q qbar blank en vdd vss'; } > "$f"
}

# ------------------------------------------------------------------- helper: reader
READ_VAL=''
READ_ERR=''
READ_RC=NOT_RUN
run_read() {                      # run_read FILE ARGS...  -> READ_VAL, returns the reader's status
  local file="$1"; shift
  local tmp rc
  tmp=$(mktemp) || return 9
  # $RD is expanded unquoted on purpose: it is a command plus its arguments ("python reader.py"),
  # exactly like the $PF and $RS hooks above.
  $RD --data "$file" "$@" > "$tmp" 2>&1; rc=$?
  if [ "$rc" = "0" ]; then READ_VAL=$(tail -1 "$tmp"); else READ_ERR=$(tail -1 "$tmp"); fi
  # the reader's own code travels here, in this shell: a row that says "the reader refused" must show
  # WHICH refusal was seen (3 no-signal, 4 too-few-samples, 5 bad number), never a flattened 1
  READ_RC=$rc
  rm -f "$tmp"
  return "$rc"
}

# ------------------------------------------------------------------- helper: closeness
close() {  # close VALUE EXPECTED TOL -> status 0 when both parse and |value-expected| <= tol
  python - "$1" "$2" "$3" <<'PY'
import sys
try:
    a, b, t = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
except Exception:
    sys.exit(1)
sys.exit(0 if (a == a and abs(a - b) <= t) else 1)
PY
}

# ------------------------------------------------------------------- helper: numeric
num_cmp() { # value kind -> prints PASS/FAIL, prints NOT_FINITE and exits 2 when the value is not finite
  python - "$1" "$2" "$VOL" <<'PY'
import sys
raw, kind, lvl = sys.argv[1], sys.argv[2], float(sys.argv[3])
try:
    x = float(raw)
except Exception:
    print('NOT_FINITE'); sys.exit(2)
if x != x or x in (float('inf'), float('-inf')):
    print('NOT_FINITE'); sys.exit(2)
ok = (x < lvl) if kind == 'lt' else (x > lvl)
print('PASS' if ok else 'FAIL')
PY
}

data_for() { # log_file -> the data path run_spectre itself reported, empty when absent
  sed -n "s/^CHECK datafile='\(.*\)'/\1/p" "$1" | head -1
}

run_deck() {   # run_deck DECK TAG  -> sets DATA (empty on failure) and STAGE (ok|PRECHECK_FAIL|SIM_FAIL)
  local deck="$1" tag="$2" log pfrc drc tok label
  label="S1REG_$tag"          # not assigned inside the same local: $tag is still unset while its
                              # words expand, so "local ... label=S1REG_$tag" dies under set -u
  log="$D/$tag.pf.log"
  $PF "$deck" "$VDDC" "$tag" "vdd=$VDDC vss=0" > "$log" 2>&1; pfrc=$?
  PREFLIGHT_RC=$pfrc
  if [ "$pfrc" != "0" ]; then
    STAGE=PRECHECK_FAIL; DATA=''; tail -3 "$log"
    echo "  preflight exit=$pfrc -> the runner is not called for $tag"
    return 1
  fi
  log="$D/$tag.sim.log"
  LABEL="$label" $RS "$deck" 300 > "$log" 2>&1; drc=$?
  RUNNER_RC=$drc
  # the runner's own completion token, exactly one line, not a substring of anything else
  tok=$(grep -cxF "$label: PASS" "$log" 2>/dev/null || true)
  if [ "$drc" != "0" ] || [ "$tok" != "1" ]; then
    STAGE=SIM_FAIL; DATA=''
    echo "  runner exit=$drc success_token_lines=$tok -> SIM_FAIL"
    return 1
  fi
  if ! grep -qxF 'CHECK error_hits=0' "$log"; then STAGE=SIM_FAIL; DATA=''; return 1; fi
  DATA=$(data_for "$log")
  if [ -z "$DATA" ] || [ ! -s "$DATA" ]; then
    STAGE=SIM_FAIL; DATA=''
    echo "  SIM_FAIL: no readable data file in the runner log -- an older raw is never used"
    return 1
  fi
  STAGE=ok; return 0
}

row() { # 14 positional fields, TAB separated -- ${10}..${14} must stay braced: "$10" is $1 followed by 0
  TSV="$TSV$1	$2	$3	$4	$5	$6	$7	$8	$9	${10}	${11}	${12}	${13}	${14}
"
}

# --------------------------------------------------------------------- truth table
for pair in "dc_blank0 0" "dc_blank1.8 $VDDC"; do
  run=$(echo "$pair" | cut -d' ' -f1); bv=$(echo "$pair" | cut -d' ' -f2)
  deck="$D/s1reg_$run.scs"; dc_deck "$deck" "$bv"
  if ! run_deck "$deck" "$run"; then
    echo "  $run: $STAGE (preflight=$PREFLIGHT_RC) -- no row is fabricated from an old run"
    row "$run" truth "$STAGE" "$deck" - - - NOT_MEASURED 1 NOT_RUN "$RUNNER_RC" "$PREFLIGHT_RC" FAIL \
        "deck never produced data, so the truth table is incomplete"
    fail=1; continue
  fi
  if [ "$bv" = "0" ]; then BSTATE=0; else BSTATE=1; fi
  for qmv in 0 $VDDC; do
    if [ "$qmv" = "0" ]; then Q=1; else Q=0; fi
    if [ "$Q" = 1 ] && [ "$BSTATE" = 0 ]; then want=ON; else want=OFF; fi
    if ! run_read "$DATA" --sig en --sweep "$qmv" --mode last --require-n 1; then
      echo "  Q=$Q BLANK=$BSTATE: READ_FAIL $READ_ERR"
      row "truth_Q${Q}_BLANK$BSTATE" truth "$DATA" "$deck" en "sweep=$qmv" last NOT_MEASURED 1 \
          "$READ_RC" "$RUNNER_RC" "$PREFLIGHT_RC" FAIL "the reader refused this row ($READ_ERR)"
      fail=1; continue
    fi
    v=$READ_VAL
    verdict=$(num_cmp "$v" "$([ "$want" = ON ] && echo gt || echo lt)") || true
    [ "$verdict" = PASS ] || fail=1
    note="expected $want at decision level $VOL V"
    # the row's own stimulus must be what its label claims, or the row is not evidence of anything
    for sb in "blank:$bv" "qbar:$qmv"; do
      sig2=${sb%%:*}; want2=${sb##*:}
      if run_read "$DATA" --sig "$sig2" --sweep "$qmv" --mode last --require-n 1; then
        if close "$READ_VAL" "$want2" 1e-6; then
          echo "    $sig2=$READ_VAL matches label $want2"
        else
          echo "    $sig2=$READ_VAL but the label says $want2 -> the row cannot be trusted"
          verdict=FAIL; fail=1; note="$note; $sig2 read $READ_VAL != label $want2"
        fi
      else
        echo "    $sig2 READ_FAIL $READ_ERR -> the row cannot be trusted"
        verdict=FAIL; fail=1; note="$note; $sig2 unreadable"
      fi
    done
    echo "  Q=$Q BLANK=$BSTATE -> en=${v} V expect=$want  $verdict"
    row "truth_Q${Q}_BLANK$BSTATE" truth "$DATA" "$deck" en "sweep=$qmv V" last "$v" 1 0 "$RUNNER_RC" \
        "$PREFLIGHT_RC" "$verdict" "$note"
  done
done

# ---------------------------------------------------------------- transient windows
# R2D2: the window judgement is no longer made here. scripts/sc1_s1_window_contract.py holds the
# S1 state contract once (output assertion + whole-window states + the frozen blank PWL + the clock's
# real edges) and the historical re-analysis reads the same table, so the two entries cannot drift
# apart again. The draft used to read blank/qbar/q/d/clk with --mode max and record PASS as long as
# the read worked; the reviewer set T2's blank to 1.8 V -- T2 is defined as BLANK=0 -- and the run
# still reported PASS at rc 0. Reading a state is not agreeing with it.
deck="$D/s1reg_tran.scs"; tran_deck "$deck" blank
if run_deck "$deck" tran; then
  # stimulus sanity first: without a clock that actually rises, an en verdict means nothing
  if run_read "$DATA" --sig clk --t0 60n --t1 90n --mode max --require-n 3 \
     && [ "$(num_cmp "$READ_VAL" gt)" = PASS ]; then
    sv=$READ_VAL; sverdict=PASS
    echo "  S1_STIMULUS_SANITY: PASS (clk reached $sv V)"
  else
    sv=${READ_VAL:-NOT_MEASURED}; sverdict=FAIL; fail=1
    echo "  S1_STIMULUS_SANITY: FAIL (clk only reached $sv V) -- the window verdicts are meaningless"
  fi
  row stimulus_sanity evidence "$DATA" "$deck" clk "60n..90n" max "$sv" 3 0 "$RUNNER_RC" "$PREFLIGHT_RC" \
      "$sverdict" "the historical clock must actually edge inside this window"
  for wid in T1 T2 T3 T4 T5; do
    ranges=$(echo "$WINDOWS" | awk -v w="$wid" '$1==w{print $3".."$4}')
    creport="$D/$wid.contract.tsv"
    # the contract's status is its own; carriage returns are stripped afterwards so a Windows host
    # cannot inject a line break into a CSV field (and stripping must not hide a non-zero exit code)
    python "$CONTRACT" --data "$DATA" --window "$wid" --reader "$RD" > "$creport.raw" 2>&1
    crc=$?
    tr -d '\r' < "$creport.raw" > "$creport"
    rm -f "$creport.raw"
    if [ "$crc" = "2" ]; then
      echo "  $wid: CONTRACT_HARNESS_ERROR (rc 2) -- the window could not be evaluated at all"
      row "${wid}_contract" contract_harness "$DATA" "$deck" - "$ranges" - NOT_MEASURED 3 "$crc" \
          "$RUNNER_RC" "$PREFLIGHT_RC" FAIL "harness problem, not a circuit result"
      fail=1; continue
    fi
    [ "$crc" = 0 ] || fail=1
    while IFS='	' read -r cw kind sig rule detail rc cv; do
      [ -z "$kind" ] && continue
      [ "$kind" = window ] && continue          # the label row, not a check
      val=$(echo "$detail" | sed -n 's/.*=\(-\?[0-9.][0-9.eE+-]*\).*/\1/p')
      req=3; [ "$rc" = awk ] && req=per_sample
      echo "    $wid $kind $sig -> $cv  ${detail:0:96}"
      row "${wid}_${kind}_${sig}" "$kind" "$DATA" "$deck" "$sig" "$ranges" "$kind" \
          "${val:-NOT_AGGREGATED}" "$req" "$rc" "$RUNNER_RC" "$PREFLIGHT_RC" "$cv" \
          "$rule | $detail"
    done < "$creport"
    echo "  $wid contract: $([ "$crc" = 0 ] && echo PASS || echo FAIL)"
  done
else
  echo "  transient: $STAGE (preflight=$PREFLIGHT_RC)"; fail=1
  row T1 window "$STAGE" "$deck" - - - NOT_MEASURED 3 NOT_RUN "$RUNNER_RC" "$PREFLIGHT_RC" FAIL \
      "no data: the transient deck was refused, so the five windows are NOT_AVAILABLE"
fi

# ---------------------------------------------------------------- the real negative
# The negative is the historical one: the gate's BLANK PIN is tied to vss while the blank SOURCE keeps
# its PWL. R2D2 adds what the draft got wrong twice -- first it demanded blank==0 V (which is a
# different fault and wrongly failed the real historical run), now it re-reads the whole T1 contract on
# the faulted data: Q must still hold 1 throughout 400n..455n and the blank stimulus must still follow
# the frozen PWL, and only then does a rejected T1 output assertion mean the checker caught the fault.
fdeck="$D/s1reg_fault.scs"; tran_deck "$fdeck" vss
if run_deck "$fdeck" fault; then
  # the rewire itself is a wiring fact: read it out of the deck the runner was given
  if grep -qE 'X2[[:space:]]*\(qbar[[:space:]]+vss[[:space:]]+en' "$fdeck"; then rewire=YES; else rewire=NO; fi
  if grep -qE 'Vbl \(blank 0\) vsource type=pwl' "$fdeck"; then bsrc=PWL_KEPT; else bsrc=PWL_CHANGED; fi
  freport="$D/F1.contract.tsv"
  python "$CONTRACT" --data "$DATA" --window T1 --reader "$RD" > "$freport.raw" 2>&1; fcrc=$?
  tr -d '\r' < "$freport.raw" > "$freport"; rm -f "$freport.raw"
  f_out=$(awk -F'\t' '$2=="output_assertion"{print $7}' "$freport")
  # NF==7 matters: the report's trailing 'WINDOW_CONTRACT ...' summary line has one field, and counting
  # it as a check made every negative look like a broken setup
  f_others=$(awk -F'\t' 'NF==7 && $2!="output_assertion" && $2!="window" && $7!="PASS"{n++} END{print n+0}' "$freport")
  fval=$(awk -F'\t' '$2=="output_assertion"{print $5}' "$freport" | sed -n 's/.* -> \(-\?[0-9.][0-9.eE+-]*\).*/\1/p')
  if [ "$fcrc" = "2" ] || [ -z "$f_out" ]; then
    dverdict=CONTRACT_HARNESS; fail=1
  elif [ "$rewire" != YES ] || [ "$bsrc" != PWL_KEPT ]; then
    dverdict=FAULT_SETUP_INVALID; fail=1
  elif [ "$f_others" != "0" ]; then
    # some state or stimulus check disagrees with the T1 label, so this is not the experiment T1 judges
    dverdict=FAULT_SETUP_INVALID; fail=1
  elif [ "$f_out" = FAIL ]; then dverdict=DETECTED
  elif [ "$f_out" = PASS ]; then dverdict=CHECKER_TOOTHLESS; fail=1
  else dverdict=READ_BAD; fail=1; fi
  echo "  F1 BLANK pin -> vss (deck says $rewire, blank source $bsrc): T1 assertion $f_out, other T1 checks failing=$f_others -> $dverdict"
  row F1_blank_clamped negative "$DATA" "$fdeck" en "400n..455n" output_assertion "${fval:-NOT_MEASURED}" \
      3 0 "$RUNNER_RC" "$PREFLIGHT_RC" "$dverdict" \
      "T1's own assertion on the faulted data: $f_out; Q-throughout and the blank PWL were re-checked on this deck (failing others=$f_others, rewire=$rewire, blank source=$bsrc)"
  # a compact, single-line, tab-free summary of the T1 contract on the faulted data: the raw report
  # would drop its own separators into a CSV field and the writer would rightly refuse the row
  fsum=$(awk -F'\t' 'NF==7 && $2!="window"{printf "%s/%s=%s; ", $2, $3, $7}' "$freport")
  row F1_blank_clamped_setup negative "$DATA" "$fdeck" "blank,q,qbar,clk" "400n..455n" stimulus_setup \
      "$f_others" per_sample "$fcrc" "$RUNNER_RC" "$PREFLIGHT_RC" \
      "$([ "$f_others" = 0 ] && echo PASS || echo FAIL)" \
      "the faulted bench must still be the T1 experiment; $fsum"
else
  echo "  negative deck: $STAGE -- a missing negative fails the run, it is never skipped"
  row F1_blank_clamped negative "$STAGE" "$fdeck" en "400n..455n" max NOT_MEASURED 3 NOT_RUN \
      "$RUNNER_RC" "$PREFLIGHT_RC" FAIL "no data: without the negative the checker is uncertified"
  fail=1
fi

printf '%s' "$TSV" | python "$CSVW" --out "$OUT_CSV" || { echo "HARNESS_ERROR: CSV write failed"; exit 8; }
echo "S1_R2D_REGRESSION: $([ "$fail" = 0 ] && echo PASS || echo FAIL) -- csv $OUT_CSV"
[ "$fail" = 0 ] || exit 6
exit 0
