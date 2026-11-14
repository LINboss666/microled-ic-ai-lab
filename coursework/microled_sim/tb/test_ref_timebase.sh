#!/usr/bin/env bash
# Offline self-test for the TB reference time base (T2AR2, X31).
#
# The testbench reproduces the specification's 576/448 slot arithmetic and uses
# it as an INDEPENDENT reference axis (it never reads the DUT's slot_cycle /
# slot_len / slot_start). This script re-derives the same sequence with integer
# arithmetic only - no EDA tool, no simulation - and checks the properties the
# reference model relies on. If this script is wrong, X31 would be meaningless.
#
#   bash test_ref_timebase.sh            # prints OK/FAIL and the first 20 lengths
#
# Exit 0 = all properties hold, 1 = mismatch.
set -uo pipefail

BASE_LEN=976
LONG_LEN=977
STEP=576
MOD=1024
INIT=576

fail=0
note() { printf '%s\n' "$*"; }

# ---- one frame: 1024 slots, starting from a given frac ----------------------
frame_len=0
frac=$INIT
len=$BASE_LEN
longs=0
shorts=0
first=0
seq=""
for ((k = 0; k < 1024; k++)); do
    [ "$k" -eq 0 ] && first=$len
    [ "$k" -lt 20 ] && seq="$seq $len"
    if [ "$len" -eq "$LONG_LEN" ]; then longs=$((longs + 1)); else shorts=$((shorts + 1)); fi
    frame_len=$((frame_len + len))
    # next length decision (identical to tcon_timebase.v len_nxt / frac_nxt)
    if [ $((frac + STEP)) -ge "$MOD" ]; then
        len=$LONG_LEN
        frac=$((frac + STEP - MOD))
    else
        len=$BASE_LEN
        frac=$((frac + STEP))
    fi
done

note "FRAME first_len=$first longs=$longs shorts=$shorts cycles=$frame_len frac_end=$frac"
note "FIRST20$seq"

[ "$first" -eq "$BASE_LEN" ]      || { note "FAIL first_slot_not_976"; fail=1; }
[ "$longs" -eq 576 ]             || { note "FAIL long_slots_not_576"; fail=1; }
[ "$shorts" -eq 448 ]            || { note "FAIL short_slots_not_448"; fail=1; }
[ "$frame_len" -eq 1000000 ]     || { note "FAIL frame_cycles_not_1e6"; fail=1; }
[ "$frac" -eq "$INIT" ]          || { note "FAIL frac_not_periodic"; fail=1; }

# ---- the fractional phase must return to INIT, so every frame is identical --
frame_len2=0
frac=$INIT
len=$BASE_LEN
for ((k = 0; k < 1024; k++)); do
    frame_len2=$((frame_len2 + len))
    if [ $((frac + STEP)) -ge "$MOD" ]; then
        len=$LONG_LEN; frac=$((frac + STEP - MOD))
    else
        len=$BASE_LEN; frac=$((frac + STEP))
    fi
done
[ "$frame_len2" -eq "$frame_len" ] || { note "FAIL frame2_differs"; fail=1; }

# ---- the TB's reference compares cycle-by-cycle, so the sequence of lengths
#      must also satisfy: 0 <= frac < 1024 at every step (no stray length) ----
frac=$INIT
len=$BASE_LEN
bad=0
for ((k = 0; k < 4096; k++)); do
    [ "$frac" -ge 0 ] && [ "$frac" -lt "$MOD" ] || bad=$((bad + 1))
    [ "$len" -eq "$BASE_LEN" ] || [ "$len" -eq "$LONG_LEN" ] || bad=$((bad + 1))
    if [ $((frac + STEP)) -ge "$MOD" ]; then
        len=$LONG_LEN; frac=$((frac + STEP - MOD))
    else
        len=$BASE_LEN; frac=$((frac + STEP))
    fi
done
note "RANGE4K bad=$bad"
[ "$bad" -eq 0 ] || { note "FAIL frac_or_len_out_of_range"; fail=1; }

if [ "$fail" -eq 0 ]; then
    note "REF_TIMEBASE_SELFTEST=PASS"
    exit 0
fi
note "REF_TIMEBASE_SELFTEST=FAIL"
exit 1
