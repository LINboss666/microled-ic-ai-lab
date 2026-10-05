#!/usr/bin/env bash
# ddrv_survey.sh -- read-only survey of the two NMOS families a 15 uA data-driver sink
# could use, plus the DC-analysis syntax of this Spectre build.
#
# Prints family comments, geometry legality and voltage-validity parameter NAMES. Values
# of model coefficients are never printed: the PDK card stays out of the repository, and a
# design decision must not rest on copying vendor numbers -- the behaviour is measured.
set -uo pipefail

# same indirection the simulator runner uses: the PDK path lives in an untracked file and
# is never written into a netlist or the repository
PROJ="${PROJ:-/root/microled_ai_project}"
if [ -z "${QODER_PDK_LIB:-}" ] && [ -r "$PROJ/spectre/pdk_local.env" ]; then
  set -a; . "$PROJ/spectre/pdk_local.env"; set +a
fi
LIB="${QODER_PDK_LIB:?QODER_PDK_LIB must come from spectre/pdk_local.env}"
echo "== library: $LIB"
[ -r "$LIB" ] || { echo "SURVEY: FAIL (card unreadable)"; exit 1; }

echo "== MOS corner sections present:"
grep -oE '^section +(tt|ff|ss|snfp|fnsp|mos_mc)' "$LIB" | awk '{print $2}' | sort -u | tr '\n' ' '
echo

for want in "1.8v core nmos" "3.3v mvt nmos" "3.3v native"; do
  echo "-- family comment: $want"
  grep -n "^// \*${want}" "$LIB" | head -3
done

echo
echo "== model names defined inside section tt (name + type token only):"
awk '
  /^section +tt/    {t=1; next}
  /^section +[a-z]/ {t=0}
  t && /^[[:space:]]*\.?model[[:space:]]/ {print "  " $2 "   type=" $3}
' "$LIB" | sort -u

echo
echo "== geometry legality for the candidates (limits only, no coefficients):"
for m in n18 n33; do
  echo "-- $m"
  awk -v want="$m" '
    tolower($2)==tolower(want) && /^[[:space:]]*\.?model[[:space:]]/ {grab=1; next}
    grab && /^[[:space:]]*\.?model[[:space:]]/ {grab=0}
    grab {
      for (k in a) {}
      line=toupper($0)
      while (match(line, /(LMIN|LMAX|WMIN|WMAX|NRD|NRS)[= ][^ ,+;]+/)) {
        tok=substr(line, RSTART, RLENGTH); sub(/[= ]/, "=", tok)
        print "   " tok
        line=substr(line, RSTART+RLENGTH)
      }
    }
  ' "$LIB" | sort -u | head -8
done

echo
echo "== parameter NAMES that bound the drain/source voltage (names only, value withheld):"
for m in n18 n33; do
  hits=$(awk -v want="$m" '
    tolower($2)==tolower(want) && /^[[:space:]]*\.?model[[:space:]]/ {grab=1; next}
    grab && /^[[:space:]]*\.?model[[:space:]]/ {grab=0}
    grab { if (match($0, /[Bb][Vv][Dd][Mm][Xx]|[Vv][Dd][Ss][Mm][Aa][Xx]|[Dd][Mm][Aa][Xx]/)) {print 1} }
  ' "$LIB" | wc -l)
  echo "   $m: lines carrying a drain-voltage-validity keyword = $hits"
done

echo
echo "== this build's dc analysis syntax (first lines of its help):"
spectre -h dc 2>&1 | head -24 || true
