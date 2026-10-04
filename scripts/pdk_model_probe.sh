#!/bin/bash
# Aggregate PDK model probe: runs each netlist/expectation pair through
# run_spectre.sh and reports one verdict per check plus an overall token.
# Read-only with respect to the PDK: the netlists only `include` vendor cards.
set -u

PROJ=/root/microled_ai_project
RS="$PROJ/scripts/run_spectre.sh"
NM="$PROJ/model_probe/model_probe_tsmc18_nm.scs"
PM="$PROJ/model_probe/model_probe_tsmc18_pm.scs"
SE="$PROJ/model_probe/model_probe_smic18ee_nm.scs"
S5="$PROJ/model_probe/model_probe_smic18ee_5v.scs"
MT1="$PROJ/model_probe/model_probe_mmrf_teacher_1v8.scs"
MT2="$PROJ/model_probe/model_probe_mmrf_teacher_3v3.scs"
TMP="$PROJ/logs/pdk_probe_tmp.out"
mkdir -p "$PROJ/logs"

# label | netlist | signal | sweep value | mode(eq/gt/lt) | expected
# double quotes so $NM/$PM/... expand at definition time (a single-quoted value would
# stay literal, because bash does not re-expand substitution results)
CHECKS="
TSMC18_NM_cutoff_at_rail|$NM|d|0|eq|1.8
TSMC18_NM_on_pulls_node_down|$NM|d|1.8|lt|1.75
TSMC18_PM_on_pulls_node_up|$PM|p|0|gt|0.05
TSMC18_PM_cutoff_at_ground|$PM|p|1.8|eq|0.0
SMIC18EE_NM18_cutoff_at_rail|$SE|d|0|eq|1.8
SMIC18EE_NM18_on_pulls_node_down|$SE|d|1.8|lt|1.75
SMIC18EE_NM50_cutoff_at_rail|$S5|d|0|eq|5.0
SMIC18EE_NM50_on_pulls_node_down|$S5|d|5.0|lt|4.9
MMRF18_N_cutoff_at_rail|$MT1|dn|0|eq|1.8
MMRF18_N_on_pulls_node_down|$MT1|dn|1.8|lt|1.75
MMRF18_P_on_pulls_node_up|$MT1|dp|0|gt|0.05
MMRF18_P_cutoff_at_ground|$MT1|dp|1.8|eq|0.0
MMRF33_N_cutoff_at_rail|$MT2|dn|0|eq|3.3
MMRF33_N_on_pulls_node_down|$MT2|dn|3.3|lt|3.2
MMRF33_P_on_pulls_node_up|$MT2|dp|0|gt|0.05
MMRF33_P_cutoff_at_ground|$MT2|dp|3.3|eq|0.0
"

pass=0; fail=0; failed=""
t_pass=0; t_fail=0; s_pass=0; s_fail=0; m_pass=0; m_fail=0
while IFS='|' read -r label net sig sw mode val; do
  [ -n "${label:-}" ] || continue
  case "$mode" in
    eq) env LABEL="$label" PROJ="$PROJ" EXPECT_SIG="$sig" EXPECT_SWEEP="$sw" EXPECT_VAL="$val" EXPECT_TOL=1e-3 bash "$RS" "$net" 150 > "$TMP" 2>&1 ;;
    gt) env LABEL="$label" PROJ="$PROJ" EXPECT_SIG="$sig" EXPECT_SWEEP="$sw" EXPECT_GT="$val"            bash "$RS" "$net" 150 > "$TMP" 2>&1 ;;
    lt) env LABEL="$label" PROJ="$PROJ" EXPECT_SIG="$sig" EXPECT_SWEEP="$sw" EXPECT_LT="$val"            bash "$RS" "$net" 150 > "$TMP" 2>&1 ;;
    *)  echo "bad mode '$mode' in table"; exit 9 ;;
  esac
  rc=$?
  chk=$(grep -aE "^CHECK (numeric|threshold)" "$TMP" | tail -1)
  case "$label" in
    TSMC18_*)     grp=t ;;
    SMIC18EE_*)   grp=s ;;
    MMRF*)        grp=m ;;
    *)            grp=? ;;
  esac
  if [ "$rc" = "0" ]; then
    pass=$((pass+1))
    [ "$grp" = t ] && t_pass=$((t_pass+1))
    [ "$grp" = s ] && s_pass=$((s_pass+1))
    [ "$grp" = m ] && m_pass=$((m_pass+1))
    printf '%-40s PASS  %s\n' "$label" "$chk"
  else
    fail=$((fail+1))
    [ "$grp" = t ] && t_fail=$((t_fail+1))
    [ "$grp" = s ] && s_fail=$((s_fail+1))
    [ "$grp" = m ] && m_fail=$((m_fail+1))
    failed="$failed $label"
    printf '%-40s FAIL  rc=%s\n' "$label" "$rc"
    grep -aE "REASON|ERROR \(" "$TMP" | head -3 | sed 's/^/      /'
  fi
done <<EOF
$CHECKS
EOF

echo "-----------------------------------------"
echo "TSMC18       checks passed=$t_pass failed=$t_fail"
echo "SMIC18EE     checks passed=$s_pass failed=$s_fail"
echo "SMIC18MMRF   checks passed=$m_pass failed=$m_fail   (teacher copy)"
[ "$t_fail" = "0" ] && [ "$t_pass" -ge 4 ] && echo "MODEL_PROBE_TSMC18: PASS"     || echo "MODEL_PROBE_TSMC18: FAIL"
[ "$s_fail" = "0" ] && [ "$s_pass" -ge 4 ] && echo "MODEL_PROBE_SMIC18EE: PASS"   || echo "MODEL_PROBE_SMIC18EE: FAIL"
[ "$m_fail" = "0" ] && [ "$m_pass" -ge 8 ] && echo "MODEL_PROBE_SMIC18MMRF: PASS" || echo "MODEL_PROBE_SMIC18MMRF: FAIL"
echo "total checks passed=$pass failed=$fail"
if [ "$fail" = "0" ] && [ "$pass" -ge 16 ]; then
  echo "PDK_MODEL_PROBE: PASS"
  exit 0
fi
echo "PDK_MODEL_PROBE: FAIL (failed:${failed})"
exit 1
