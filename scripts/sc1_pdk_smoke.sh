#!/bin/bash
# SCAN-1 S0.3: which 3.3 V PMOS masters does THIS Spectre actually accept, and with how many
# terminals? Nothing here is assumed from a device name -- DATA-5 already proved that
# n33_dnw_ckt rejects a 4-node instance (SFE-45 "needs at least 6 terminals") while
# n33_dnw_4t_ckt accepts 4, so the same measurement is done for the p33 family before any
# high-side switch is designed around it.
#
# Read-only w.r.t. the PDK. Writes only under cadence_work/sc1_sim/ and /tmp.
set -u
PROJ=/root/microled_ai_project
cd "$PROJ" || exit 8
. ./skill/cad_env.sh >/dev/null 2>&1 || { echo "FATAL: cad_env load failed"; exit 8; }
[ -f spectre/pdk_local.env ] && . spectre/pdk_local.env
LIB="${QODER_PDK_LIB:-$PROJ/pdk/smic18mmrf_teacher/models/spectre/ms018_enhanced_v1p2_rev0_spe.lib}"
[ -f "$LIB" ] || { echo "FATAL: model lib not readable at $LIB"; exit 8; }
echo "PDK_LIB=$LIB"
echo "SPECTRE=$(command -v spectre)"
SECTION="${1:-tt}"
echo "SECTION_REQUESTED=$SECTION"
OUT=$PROJ/cadence_work/sc1_sim
mkdir -p "$OUT"

# 1.8 V reference devices, to prove the include+section path itself works in this session
# 3.3 V candidates for the high-side switch, and the deep-n-well variants
MASTERLIST="p33 p33_ckt p33_dnw_4t_ckt p33_dnw_ckt p33_dnw n18 n33_ckt n33_dnw_4t_ckt"
: > "$OUT/pdk_smoke.csv"
echo "master,nodes,rc,verdict,first_error" >> "$OUT/pdk_smoke.csv"

for m in $MASTERLIST; do
  for nodes in 4 6; do
    D="$OUT/smoke_${m}_${nodes}n.scs"
    # Analysis syntax is copied from a deck that is known to run on THIS build
    # (spectre/nmos_probe.scs): a named DC analysis `sw1 dc dev=<vsrc> param=dc ...`.
    # An earlier draft used `dc ana=dc`, which Spectre read as an instance with no master
    # (SFE-709) and failed every case, including n18 -- a bad deck, not missing devices.
    {
      echo "simulator lang=spectre insensitive=yes"
      echo "include \"$LIB\" section=$SECTION"
      echo "Vdd (vdd 0) vsource dc=1.8"
      echo "Vss (vss 0) vsource dc=0"
      echo "Vg  (g 0) vsource dc=0"
      echo "Vd  (d 0) vsource dc=0"
      if [ "$nodes" = "4" ]; then
        echo "Mx (d g vss vss) $m l=350n w=10u m=1"
      else
        # 6-terminal form: d g s b nwell substrate
        echo "Mx (d g vss vss vdd 0) $m l=350n w=10u m=1"
      fi
      echo "sw1 dc dev=Vd param=dc start=0 stop=0.9 step=0.9"
      echo "save d"
    } > "$D"
    R=$(cd "$OUT" && timeout 120 spectre "$D" -64 -format psfascii 2>&1)
    rc=$?
    # take the specific ERROR/SFE line, never the generic "Error found by spectre" summary
    ERRLINE=$(printf '%s' "$R" | grep -aiE "ERROR \(|SFE-[0-9]+|unknown|not found" | head -1 | cut -c1-90)
    if [ "$rc" = "0" ]; then
      verdict=ACCEPTED
      err=""
    elif printf '%s' "$R" | grep -qiE "needs at least|wrong number of terminals|SFE-45"; then
      verdict=TERMINAL_COUNT
      err="$ERRLINE"
    elif printf '%s' "$R" | grep -qiE "unknown (model|subckt)|no master|not found|does not exist"; then
      verdict=NO_SUCH_MASTER
      err="$ERRLINE"
    else
      verdict=OTHER_FAIL
      err="$ERRLINE"
    fi
    echo "$m,$nodes,$rc,$verdict,\"$err\"" >> "$OUT/pdk_smoke.csv"
    printf '%-16s %sn rc=%-3s %-16s %s\n' "$m" "$nodes" "$rc" "$verdict" "$err"
  done
done
echo "SMOKE_CSV=$OUT/pdk_smoke.csv"
echo "PDK_SMOKE: DONE"
