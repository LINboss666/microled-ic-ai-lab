#!/bin/bash
# pvt_probe.sh -- one small corner probe of the 3-stage chain, no cell change.
#
#   pvt_probe.sh [clock_period] [corner] [corner] ...
#
# Scope is deliberately narrow (review item A10): 1.8 V, 50 fF, three identical C^2MOS
# stages, and the question "does one clock edge ever propagate through more than one
# stage" -- because every stage builds its own local clkb with an internal inverter, so
# the shortest FF0 -> FF1 -> FF2 path has no buffer delay in the middle.
#
# Corner names are NEVER guessed here: they are read out of the model library the local
# pdk_local.env points at, by listing its `section` statements. The mapping to
# nominal / slow / fast is by the convention those names carry (tt = typical,
# ss = slow-slow, ff = fast-fast). If the expected sections are not present, or their
# role cannot be read off the name, the probe refuses to run and reports
# PVT_PROBE: NOT_RUN_AMBIGUOUS_CORNER instead of inventing a section.
#
# Out of scope by instruction: voltage sweep, temperature sweep, Monte Carlo, mismatch,
# the scan output stage, and any change to the cell itself.
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
T="${1:-2e-7}"
shift 2>/dev/null || true

ENVFILE="${PDK_ENV_FILE:-$PROJ/spectre/pdk_local.env}"
[ -r "$ENVFILE" ] || { echo "PVT_PROBE: FAIL  (missing $ENVFILE -- no local PDK path)"; exit 8; }
# shellcheck disable=SC1090
set -a; . "$ENVFILE"; set +a
[ -n "${QODER_PDK_LIB:-}" ] && [ -r "$QODER_PDK_LIB" ] || {
  echo "PVT_PROBE: FAIL  (QODER_PDK_LIB not readable)"; exit 8; }

echo "== corner discovery from the model library (names only, no content copied)"
SECTIONS=$(grep -aoE '^[[:space:]]*section[[:space:]]+[A-Za-z0-9_]+' "$QODER_PDK_LIB" |
           awk '{print $2}' | sort -u)
echo "$SECTIONS" | tr '\n' ' '; echo
have() { echo "$SECTIONS" | grep -qx "$1"; }

NOMINAL=""; SLOW=""; FAST=""
for s in $SECTIONS; do
  case "$s" in
    tt|TT|typ|typical) [ -z "$NOMINAL" ] && NOMINAL="$s" ;;
    ss|SS|slow|slow_slow|slowslw) [ -z "$SLOW" ] && SLOW="$s" ;;
    ff|FF|fast|fast_fast|fastfast) [ -z "$FAST" ] && FAST="$s" ;;
  esac
done
if [ -z "$NOMINAL" ] || [ -z "$SLOW" ] || [ -z "$FAST" ]; then
  echo "PVT_PROBE: NOT_RUN_AMBIGUOUS_CORNER"
  echo "  nominal='$NOMINAL' slow='$SLOW' fast='$FAST' -- cannot assign roles without guessing"
  exit 0
fi
echo "resolved: nominal=$NOMINAL  slow=$SLOW  fast=$FAST   (from section names only)"

CORNERS="${*:-$NOMINAL $SLOW $FAST}"
LOGD="$PROJ/logs"
summary="$LOGD/pvt_probe_summary.txt"
: > "$summary"
fail=0
for c in $CORNERS; do
  if ! have "$c"; then
    echo "PVT_PROBE: refusing unknown section '$c'" | tee -a "$summary"
    fail=1
    continue
  fi
  echo "########## corner=$c  (T=$T, VDD=1.8, Cload=50fF, 3 stages)"
  out=$(SECTION="$c" bash "$PROJ/scripts/c2mos_check.sh" shift3 "$T" "pvt_$c" 1 2>&1)
  echo "$out" | grep -aE "model section override|STATIC_OK|OP_OK|TESTBENCH_PREFLIGHT|assertions|DELAY|: PASS|: FAIL" | sed 's/^/  /'
  {
    echo "corner=$c"
    echo "$out" | grep -aE "assertions:|DELAY|C2MOS_SHIFT_3STAGE:|TESTBENCH_PREFLIGHT:"
  } >> "$summary"
  echo "$out" | grep -qa "C2MOS_SHIFT_3STAGE: PASS" || fail=1
  cp "$PROJ/spectre/run_shift3_pvt_$c.scs" "$LOGD/pvt_netlist_$c.scs" 2>/dev/null
done

echo ""
echo "== PVT probe summary"
cat "$summary"
if [ "$fail" = "0" ]; then
  echo "PVT_PROBE: PASS"
  echo "  meaning: at nominal, slow and fast MOS sections the 3-stage chain still moves"
  echo "  exactly one stage per rising edge, and the same-edge race window (q2 low while"
  echo "  q1 first takes the bit) held. Not a characterisation: one VDD, one"
  echo "  temperature, one load, three sections."
  exit 0
fi
echo "PVT_PROBE: FAIL"
exit 1
