#!/usr/bin/env bash
# Scenario -> minimum-assertion floor, shared by the T1 and T2A runners.
#
# WHY THIS FILE EXISTS (T1R review F1)
#   run_tcon_t1.sh used to do:
#       MIN_ASSERTS="${MIN_ASSERTS:-49}"      # <-- already non-empty here
#       case "$SCEN" in RESET_FAULT) MIN_ASSERTS="${MIN_ASSERTS:-23}" ;; esac
#   The second expansion can never fire, so EVERY scenario silently required 49
#   and a correct 23/23 RESET_FAULT run would be reported as a failure. The
#   floors are therefore resolved by one explicit function that is unit-tested
#   by tb/test_scen_min_asserts.sh (pure shell, no ModelSim).

# Floors are derived by counting `chk("` occurrences inside each TB task:
#   RESET_FAULT 23 | TIMEBASE 16 | BOUNDARY 10 | ALL 49   (tcon_t1_tb.sv)
scen_floor() {
    case "$1" in
        RESET_FAULT) echo 23 ;;
        TIMEBASE)    echo 16 ;;
        BOUNDARY)    echo 10 ;;
        ALL)         echo 49 ;;
        *)           echo "" ;;
    esac
}

# resolve_min_asserts <scenario> [external_min_asserts]
#   stdout = the value to use, or an ERR_* token
#   rc     = 0 ok | 9 unknown scenario | 8 not an integer | 7 below the floor
resolve_min_asserts() {
    local scen="${1:-}"
    local ext="${2:-}"
    local floor

    floor=$(scen_floor "$scen")
    if [ -z "$floor" ]; then
        echo "ERR_UNKNOWN_SCENARIO"
        return 9
    fi
    if [ -z "$ext" ]; then
        echo "$floor"
        return 0
    fi
    case "$ext" in
        *[!0-9]*)
            echo "ERR_NOT_INTEGER"
            return 8
            ;;
    esac
    if [ "$ext" -lt "$floor" ]; then
        echo "ERR_BELOW_FLOOR_$floor"
        return 7
    fi
    echo "$ext"
    return 0
}
