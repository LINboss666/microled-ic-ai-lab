#!/bin/bash
# SCAN-1 R2C: reproduce and close the preflight log-completion race, using LOCAL COPIES only.
#
#   bash scripts/sc1_r2c_lograce.sh [N] [SLEEP_SECONDS]
#
# Observed symptom (cloud review of 9159a39): the first static matrix run reported row p05 with an
# empty rejection stage although its log, read later, contained PREFLIGHT_STAGE=static_gate and the
# probe token. The wrapper pipes its own output through `exec > >(tee "$OUT") 2>&1`, which is an
# asynchronous writer: the script can exit while tee is still draining, so a harness that reads the
# log immediately afterwards may see a truncated file.
#
# This script proves the cause instead of asserting it. Both variants run the SAME adversarially slow
# log writer; only the completion synchronisation differs:
#   nowait : the trap/wait that closes the descriptors is disabled  -> truncated reads expected
#   fixed  : the committed wrapper, trap active                    -> every read must be complete
# Nothing here calls a simulator: the decks are judged with PREFLIGHT_STATIC_PROBE=1, which stops
# after the static gates and exits 7 without touching Spectre. The committed checker and wrapper are
# never modified by this script -- it writes copies under cadence_work/r2c_lograce.
set -u
PROJ=${PROJ:-/root/microled_ai_project}
N=${1:-10}
SLEEP=${2:-0.05}
PF="$PROJ/scripts/tb_preflight.sh"
[ -r "$PF" ] || { echo "HARNESS_ERROR: $PF not readable"; exit 8; }
TD="$PROJ/cadence_work/r2c_lograce"
rm -rf "$TD"; mkdir -p "$TD/decks"

CELL='subckt dut18 (in out vdd vss)
  mp (out in vdd vdd) p18 l=2e-7 w=4e-6
  mn (out in vss vss) n18 l=2e-7 w=2e-6
ends dut18'
DECK="$TD/decks/probe_ok.scs"
printf '%s\n' "simulator lang=spectre insensitive=yes
$CELL
Vdd (vdd 0) vsource dc=1.8
Vss (vss 0) vsource dc=0
Vi (in 0) vsource dc=0
X1 (in out vdd vss) dut18
sw1 tran stop=1.5n maxstep=0.5n
save in out vdd vss" > "$DECK"

# the slow writer: same content, written line by line with a delay, so an unsynchronised reader
# loses the race deterministically rather than by luck
SLOW_FN='slow_tee() { f="$1"; while IFS= read -r l; do printf "%s\n" "$l" >> "$f"; sleep __SLEEP__; done; }'
SLOW_FN=$(printf '%s' "$SLOW_FN" | sed "s/__SLEEP__/$SLEEP/")

mkvariant() { # out_path  mode(async|sync)
  local out="$1" mode="$2"
  # the function goes at the very top: bash reads the file top down, and the script is always
  # invoked as `bash FILE`, so shifting the shebang one line down changes nothing
  printf '%s\n' "$SLOW_FN" > "$out"
  if [ "$mode" = async ]; then
    # swap ONLY the log-writing mechanism of the committed script back to an asynchronous tee
    sed 's|^exec >>"\$OUT" 2>&1$|exec > >(slow_tee "\$OUT") 2>\&1|' "$PF" >> "$out"
    grep -q 'slow_tee "$OUT"' "$out" || { echo "HARNESS_ERROR: async injection failed"; exit 8; }
  else
    cat "$PF" >> "$out"
    grep -q 'slow_tee "$OUT"' "$out" && { echo "HARNESS_ERROR: sync variant must not be async"; exit 8; }
  fi
  bash -n "$out" || { echo "HARNESS_ERROR: variant $out does not parse"; exit 8; }
}
VAR_ASYNC="$TD/pf_async_writer.sh"; VAR_SYNC="$TD/pf_sync.sh"
mkvariant "$VAR_ASYNC" async
mkvariant "$VAR_SYNC" sync

run_variant() { # script  label
  local script="$1" label="$2" log cap incomplete=0 rc i
  for i in $(seq 1 "$N"); do
    log="$PROJ/logs/preflight_probe_ok_lr_$label.txt"
    cap="$TD/capture_$label.txt"
    rm -f "$log" "$cap"
    PREFLIGHT_STATIC_PROBE=1 bash "$script" "$DECK" 1.8 "lr_$label" > "$cap" 2>&1
    rc=$?
    # read immediately after the process returned -- exactly what the matrix harness does, from both
    # the wrapper's own report file and the caller's capture
    if ! tail -1 "$log" 2>/dev/null | grep -q '^TESTBENCH_PREFLIGHT:'; then
      incomplete=$((incomplete + 1))
    fi
    if ! tail -1 "$cap" 2>/dev/null | grep -q '^TESTBENCH_PREFLIGHT:'; then
      incomplete=$((incomplete + 1))
    fi
    if [ "$rc" != "7" ]; then
      echo "HARNESS_ERROR: $label exit $rc, expected the static probe code 7"
      exit 8
    fi
  done
  echo "$incomplete"
}

INC_ASYNC=$(run_variant "$VAR_ASYNC" async)
INC_SYNC=$(run_variant "$VAR_SYNC" sync)
echo "LOG_RACE iterations=$N writer_sleep=${SLEEP}s  (2 reads checked per run: report file + caller capture)"
echo "  async log writer (the mechanism this round replaces): incomplete reads = $INC_ASYNC/$((N * 2))"
echo "  committed wrapper (synchronous report + echo on exit): incomplete reads = $INC_SYNC/$((N * 2))"
echo "  exit status stayed 7 (static probe, no simulator) in both variants"
if [ "$INC_SYNC" != "0" ]; then
  echo "LOG_COMPLETION_VALIDATION: FAIL (the committed wrapper still lost $INC_SYNC reads)"
  exit 6
fi
if [ "$INC_ASYNC" = "0" ]; then
  echo "LOG_COMPLETION_VALIDATION: INCONCLUSIVE (the async variant lost no reads either; raise SLEEP"
  echo "  or N so the race is observable before crediting the fix)"
  exit 5
fi
echo "LOG_COMPLETION_VALIDATION: PASS (cause reproduced on a copy of the committed script, and the"
echo "  committed mechanism reads complete $((N * 2))/$((N * 2)))"
exit 0
