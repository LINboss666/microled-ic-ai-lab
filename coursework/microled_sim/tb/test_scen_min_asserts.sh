#!/usr/bin/env bash
# Pure-shell self test for the MIN_ASSERTS resolution (T1R review F1).
# No ModelSim, no simulator, no repository writes. Exit 0 = 8/8 pass.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=tb/scen_min_asserts.sh
. "$HERE/scen_min_asserts.sh"

pass=0
fail=0

chk() { # chk <name> <expected-token> <expected-rc> <scen> [ext]
    local name="$1" want="$2" wantrc="$3" scen="$4" ext="${5:-}"
    local got rc
    got=$(resolve_min_asserts "$scen" "$ext")
    rc=$?
    if [ "$got" = "$want" ] && [ "$rc" = "$wantrc" ]; then
        echo "PASS $name  (scen='$scen' ext='$ext' -> '$got' rc=$rc)"
        pass=$((pass + 1))
    else
        echo "FAIL $name  (scen='$scen' ext='$ext' -> '$got' rc=$rc, want '$want' rc=$wantrc)"
        fail=$((fail + 1))
    fi
}

echo "=== scenario floor resolution ==="
chk "S1_RESET_FAULT_default_23"  "23"                  0 RESET_FAULT
chk "S2_TIMEBASE_default_16"     "16"                  0 TIMEBASE
chk "S3_BOUNDARY_default_10"     "10"                  0 BOUNDARY
chk "S4_ALL_default_49"          "49"                  0 ALL

echo "=== external MIN_ASSERTS handling ==="
chk "S5_ALL_external_above_ok"     "60"                 0 ALL        60
chk "S6_RESET_external_equal_ok"   "23"                 0 RESET_FAULT 23
chk "S7_RESET_external_below_bad"  "ERR_BELOW_FLOOR_23" 7 RESET_FAULT 10
chk "S8_BOUNDARY_external_below_bad" "ERR_BELOW_FLOOR_10" 7 BOUNDARY 1

echo "=== input validation ==="
chk "S9_unknown_scenario"        "ERR_UNKNOWN_SCENARIO" 9 NOPE
chk "S10_non_integer"            "ERR_NOT_INTEGER"      8 ALL        abc

echo
echo "SUMMARY pass=$pass fail=$fail"
if [ "$fail" -ne 0 ]; then
    echo "SCEN_MIN_ASSERTS_SELFTEST=FAIL"
    exit 6
fi
echo "SCEN_MIN_ASSERTS_SELFTEST=PASS"
exit 0
