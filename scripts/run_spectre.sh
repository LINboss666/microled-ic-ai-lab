#!/bin/bash
# Run a Spectre netlist that lives inside the Micro LED project area, then verify
# it structurally and (optionally) numerically.
#
#   run_spectre.sh <abs.path.netlist> [timeoutSec]
#
# Environment (all optional):
#   EXPECT_SIG / EXPECT_SWEEP / EXPECT_VAL / EXPECT_TOL
#       numeric assertion against the PSF-ASCII data, e.g.
#       EXPECT_SIG=vm EXPECT_SWEEP=1.8 EXPECT_VAL=0.6 EXPECT_TOL=1e-3
#   EXPECT_EPS
#       sweep-point match window, default 1e-6 (widen it for time sweeps, where
#       samples do not land on the exact requested instant)
#   EXPECT_SIG / EXPECT_T0 / EXPECT_T1 / EXPECT_MIN_GT / EXPECT_MAX_LT
#       waveform assertion over a time window: EVERY sample inside [T0,T1] must be
#       above MIN_GT and/or below MAX_LT. This is how transient functional checks are
#       expressed (a shift register is proven by windows of levels, not one instant).
#   EXPECT_GT / EXPECT_LT / EXPECT_ABS
#       instead of an equality check, assert the value at EXPECT_SWEEP is greater
#       than EXPECT_GT / lower than EXPECT_LT (magnitude, when EXPECT_ABS=1).
#       Used for behavioural checks such as "the device turns on", where the exact
#       current is not known in advance.
#   LABEL          token prefix for the verdict line (default SPECTRE_SMOKE_TEST)
#   SPECTRE_EXTRA  extra spectre options, e.g. "-mps 2"
#
# Guards / behaviour:
#   - refuses any netlist outside $PROJ, so an automated caller cannot point Spectre
#     at a PDK or at somebody else's project
#   - loads the Cadence environment by harvesting /etc/env/virtuoso's exports
#     (that wrapper must never be executed: it ends with a background GUI launch)
#   - HOME redirected into the project so Spectre scratch cannot land in the real home
#   - hard timeout; log + raw kept under <netlist dir>/sim/
#   - exit code 0 only when every enabled check passes
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
NET="${1:?usage: run_spectre.sh <netlist> [timeoutSec]}"
TMO="${2:-180}"
LABEL="${LABEL:-SPECTRE_SMOKE_TEST}"

case "$NET" in
  "$PROJ"/*) ;;
  *) echo "REFUSED: netlist must be under $PROJ (got: $NET)"; exit 9 ;;
esac
[ -f "$NET" ] || { echo "REFUSED: $NET not found"; exit 9; }

# ---- PDK path indirection (no vendor path may live in a committed file) --------
# Committed netlists reference the model library as ${QODER_PDK_LIB}: Spectre expands
# environment variables inside an include path (verified on this host by the same
# device test that gave 0.758 V with a literal path). The real path lives in
# spectre/pdk_local.env, which is git-ignored, so the instructor's PDK is never copied
# into the repository and never appears in tracked content.
PDK_ENV="${PDK_ENV:-$PROJ/spectre/pdk_local.env}"
if [ -r "$PDK_ENV" ]; then
  set -a; . "$PDK_ENV"; set +a
fi
missing=""
for v in $(grep -oE '\$\{QODER_[A-Z0-9_]+' "$NET" | sed -e 's/[${]//g' | sort -u); do
  [ -n "$(printenv "$v" 2>/dev/null)" ] || missing="$missing $v"
done
if [ -n "$missing" ]; then
  echo "REFUSED: $NET needs environment variable(s)$missing to resolve its includes"
  echo "  copy spectre/pdk_local.env.example to spectre/pdk_local.env and set your local"
  echo "  PDK paths there (that file is git-ignored; the PDK itself is never committed)"
  exit 9
fi

CAD_ENV="${CAD_ENV:-/root/qoder_ic617_sandbox/bin/cad_env.sh}"
[ -r "$CAD_ENV" ] || { echo "FATAL: env loader missing: $CAD_ENV"; exit 8; }
. "$CAD_ENV" || { echo "FATAL: env load failed"; exit 8; }

DIR="$(cd "$(dirname "$NET")" && pwd)"
BASE="$(basename "$NET")"; STEM="${BASE%.*}"
SIM="$DIR/sim"
mkdir -p "$SIM" "$PROJ/logs"
export HOME="$PROJ/home"; mkdir -p "$HOME"

cd "$DIR" || exit 9
rm -rf "$SIM/$STEM.log" "$SIM/$STEM.raw"
start=$(date +%s)
# shellcheck disable=SC2086
timeout "$TMO" spectre "$NET" -64 -format psfascii ${SPECTRE_EXTRA:-} > "$SIM/$STEM.stdout" 2>&1
rc=$?
el=$(( $(date +%s) - start ))

# spectre writes "<stem>.log" and "<stem>.raw/" next to the cwd; archive them
[ -f "$DIR/$STEM.log" ] && mv -f "$DIR/$STEM.log" "$SIM/$STEM.log"
[ -d "$DIR/$STEM.raw" ] && { rm -rf "$SIM/$STEM.raw"; mv -f "$DIR/$STEM.raw" "$SIM/$STEM.raw"; }
LOG="$SIM/$STEM.log"
RAWDIR="$SIM/$STEM.raw"

echo "SPECTRE name=$BASE rc=$rc elapsed=${el}s timeout=${TMO}s"
echo "LOGFILE $LOG"
echo "RAWDIR  $RAWDIR"

reason=""
[ "$rc" = "0" ] || reason="spectre exit=$rc (124=timeout)"
[ -s "$LOG" ] || reason="${reason} no-log"

done_line=$(grep -aoE "spectre completes with [0-9]+ error" "$LOG" 2>/dev/null | tail -1)
echo "CHECK done_line='$done_line'"
case "$done_line" in *"with 0 error"*) ;; *) reason="${reason} not-zero-errors" ;; esac
fatals=$(grep -aciE "^ERROR|FATAL|spectre terminated prematurely" "$LOG" 2>/dev/null || true)
echo "CHECK error_hits=$fatals"
[ "$fatals" = "0" ] || { reason="${reason} log-has-errors"; grep -aoE "ERROR \([A-Z0-9-]+\)[^ ]*" "$LOG" | head -3 | sed 's/^/  /'; }

# real PSF-ASCII data files carry both a TRACE and a VALUE section; spectre also
# drops a "logFile" in the same dir whose VALUE block is empty, so skip it by name
# and take the largest remaining candidate
datafile=""
for f in $(ls -S "$RAWDIR"/* 2>/dev/null); do
  [ -f "$f" ] || continue
  [ "$(basename "$f")" = "logFile" ] && continue
  grep -qs "^TRACE" "$f" && grep -qs "^VALUE" "$f" && { datafile="$f"; break; }
done
echo "CHECK datafile='$datafile'"
[ -n "$datafile" ] || reason="${reason} no-psf-data"

# --- assertions --------------------------------------------------------------
if [ -n "${EXPECT_SIG:-}" ] && [ -n "$datafile" ]; then
  # the swept variable's key name is declared in the SWEEP section; for a dc analysis
  # it is the swept parameter ("dc"), for a transient it is "time". Take the first key
  # rather than matching the literal word "sweep".
  if [ -n "${EXPECT_T0:-}" ] || [ -n "${EXPECT_T1:-}" ]; then MODE=window; else MODE=point; fi
  res=$(awk -v sig="$EXPECT_SIG" -v mode="$MODE" -v want="${EXPECT_SWEEP:-0}" \
              -v eps="${EXPECT_EPS:-1e-6}" -v t0="${EXPECT_T0:-0}" -v t1="${EXPECT_T1:-1e30}" \
              -v mingt="${EXPECT_MIN_GT:-}" -v maxlt="${EXPECT_MAX_LT:-}" '
    /^SWEEP/ {insw=1; next}
    /^TRACE/ {insw=0; next}
    insw && NF>=2 && swkey=="" { k=$1; gsub(/"/,"",k); swkey=k; next }
    /^VALUE/ {inb=1; next}
    /^END/   {inb=0}
    inb && NF>=2 {
      k=$1; gsub(/"/,"",k); v=$2+0
      if (k==swkey) { sw=v; next }
      if (k!=sig) next
      if (mode=="window") {
        if (sw>=t0 && sw<=t1) {
          n++
          if (mingt!="" && v<=mingt+0) { bad++; if (firstbad=="") firstbad=sw }
          if (maxlt!="" && v>=maxlt-0) { bad++; if (firstbad=="") firstbad=sw }
          if (first=="") first=v
          last=v
        }
      } else {
        d=sw-want; if (d<0) d=-d
        if (d<=eps) { print "POINT " v; foundp=1; exit }
      }
    }
    END {
      if (mode=="window") printf "WINDOW n=%d bad=%d min_ok=%s max_ok=%s firstbad=%.9g first=%.6g last=%.6g\n", \
             n, bad, (mingt==""?"n/a":"yes"), (maxlt==""?"n/a":"yes"), \
             (firstbad==""?-1:firstbad), first, last
      else if (!foundp) print "NOMATCH"
    }' "$datafile")
  echo "CHECK mode=$MODE sig=$EXPECT_SIG window=[${EXPECT_T0:-},${EXPECT_T1:-}] sweep=${EXPECT_SWEEP:-n/a} -> $res"
  case "$res" in
    NOMATCH|"") reason="${reason} signal-or-sweep-not-found" ;;
    WINDOW*)
      if [ "$MODE" = window ]; then
        n=$(echo "$res" | sed -E 's/.*n=([0-9]+).*/\1/')
        bad=$(echo "$res" | sed -E 's/.*bad=([0-9]+).*/\1/')
        if [ "${n:-0}" -lt 3 ]; then reason="${reason} window-too-few-samples"
        elif [ "${bad:-1}" != "0" ]; then reason="${reason} window-assertion-violated"; fi
      fi ;;
    POINT*)
      got=$(echo "$res" | awk '{print $2}')
      if [ -n "${EXPECT_GT:-}" ]; then
        v=$(awk -v a="$got" -v m="${EXPECT_ABS:-0}" 'BEGIN{print (m=="1"&&a<0)?-a:a}')
        ok=$(awk -v a="$v" -v g="${EXPECT_GT}" 'BEGIN{print (a>g)?"OK":"BAD"}')
        echo "CHECK threshold=$ok value=$got want>${EXPECT_GT}"
        [ "$ok" = "OK" ] || reason="${reason} threshold-not-met"
      elif [ -n "${EXPECT_LT:-}" ]; then
        v=$(awk -v a="$got" -v m="${EXPECT_ABS:-0}" 'BEGIN{print (m=="1"&&a<0)?-a:a}')
        ok=$(awk -v a="$v" -v l="${EXPECT_LT}" 'BEGIN{print (a<l)?"OK":"BAD"}')
        echo "CHECK threshold=$ok value=$got want<${EXPECT_LT}"
        [ "$ok" = "OK" ] || reason="${reason} threshold-not-met"
      else
        diff=$(awk -v a="$got" -v b="${EXPECT_VAL}" -v t="${EXPECT_TOL:-1e-3}" 'BEGIN{d=a-b; if(d<0)d=-d; print (d<=t)?"OK":"BAD"}')
        rel=$(awk -v a="$got" -v b="${EXPECT_VAL}" 'BEGIN{ if (b==0) { printf "delta=%.3e", (a>b?a-b:b-a) } else printf "got=%.6e expected=%.6e relerr=%.2e", a, b, ((a>b?a-b:b-a)/(b<0?-b:b)) }')
        echo "CHECK numeric=$diff  ($rel)"
        [ "$diff" = "OK" ] || reason="${reason} numeric-mismatch"
      fi ;;
    *) reason="${reason} unexpected-check-output" ;;
  esac
elif [ -n "${EXPECT_SIG:-}" ]; then
  reason="${reason} expect-set-but-no-data"
fi

ls -la "$SIM" | sed -n '1,12p'
echo "----- log tail -----"
tail -8 "$LOG" 2>/dev/null

if [ -z "$reason" ]; then
  echo "$LABEL: PASS"
  exit 0
fi
echo "$LABEL: FAIL"
echo "REASON:$reason"
exit 1
