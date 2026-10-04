#!/bin/bash
# ddrv_method_ab.sh -- is Candidate E's dynamic crosstalk physics, or trapezoidal ringing?
#
#   bash scripts/ddrv_method_ab.sh            # all legs
#   LEG="A B" bash scripts/ddrv_method_ab.sh  # a subset
#
# The same frozen Candidate E netlist (no sizing, no topology change, no Cbias), the same
# stimulus, the same initial conditions and the same maxstep are run under different
# transient integration methods. Trapezoidal integration is not L-stable, so a step-locked
# sample-to-sample alternation changes or disappears with the method, while a physical
# disturbance does not. Per run two things are recorded:
#
#   ddrv_xtalk.py  peak / Q_error / CHARGE_ERROR_PERCENT / glitch duration /
#                  VBIAS_SHARED and victim vbias_ch spread / ADJACENT_POINT_ALTERNATION
#   psf header     the method, reltol, errpreset and maxstep the run ACTUALLY used, read
#                  back out of the data file rather than assumed from the deck
#
# Legs:
#   A  frame T=9.765625 us, VOUT=1.2 V, victim CH1 held ON, aggressor CH0 toggling,
#      methods default/traponly/gear2only x slew 0.1/10/100 ns, maxstep 5 ns, plus one
#      static EN=1,1 baseline per method (that is what Q_error integrates against)
#   B  timestep convergence at frame + 10 ns: maxstep 5 ns / 1 ns / 0.5 ns
#   C  POC_STRESS_TEST only: T=200 ns, slew 10 ns, all three methods -- the 200 ns slot is
#      NOT a system time scale, it is a stress case the earlier rounds argued about
#   D  tolerance: reltol 10x tighter than the value this build reports, frame + 10 ns
#
# Already-simulated tags are reused, so re-running after a checker fix costs no simulation.
# Nothing in this script decides PASS/FAIL: it decides which numbers are trustworthy.
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
cd "$PROJ" || exit 9

FROZEN="--mpass-model n33 --mbleed-model n33 --lpass 2e-6 --lbleed 2e-6 --wpass 5e-6 --wbleed 2e-6"
VOUT=1.20
FRAME=9.765625e-6
RES="$PROJ/results/data_driver_method_ab.csv"
EVD="$PROJ/results/evidence"
LOGS="$PROJ/logs"
LEG="${LEG:-A B C D}"
[ "${FRESH:-0}" = "1" ] && : > "$RES"

mflag() { [ "$1" = "default" ] && echo "" || echo "--method $1"; }

run_deck() {   # <tag> <period> <slew> <toggle> <extra-gen-flags> -> echoes psf path
  local tag="$1" T="$2" SL="$3" TG="$4" ex="$5" cached
  cached=$(grep -aE "^/" "$LOGS/ab_${tag}.pipeline" 2>/dev/null | tail -1)
  if [ "${FRESH:-0}" != "1" ] && [ -n "$cached" ] && [ -f "$cached" ]; then
    echo "$cached"; return 0
  fi
  PROBE=iprobe TR_CSV="$LOGS/ab_${tag}.csv" TAGX="$tag" \
    EXTRA="--channels 2 --toggle $TG --en 1 --en1 1 --vout1 $VOUT $FROZEN $ex" \
    bash scripts/ddrv_run.sh tran E_local_gate n33 2e-6 2e-5 "$T" "$VOUT" tt "$SL" \
      > "$LOGS/ab_${tag}.pipeline" 2>&1
  grep -aE "^/" "$LOGS/ab_${tag}.pipeline" | tail -1
}

hdr() {   # what the run actually used, from the data file's own HEADER section
  python -c "
import sys
keep = ('method', 'reltol', 'errpreset', 'maxstep', 'step', 'temp')
out = []
for line in open(sys.argv[1]):
    s = line.strip()
    if s == 'TRACE':
        break
    p = s.split('\"')
    if len(p) > 2 and p[1] in keep:
        out.append('%s=%s' % (p[1], ' '.join(p[2:]).strip().split()[0]))
print('     HEADER ' + '  '.join(out))" "$1"
}

analyse() {   # <psf> <label> <baseline-psf> <desc>
  local p="$1" lbl="$2" base="$3" desc="$4" ref=""
  echo "  -- $lbl"
  if [ ! -f "${p:-/nonexistent}" ]; then
    echo "     NO DATA"; sed -n '1,3p' "$LOGS/ab_${lbl}.pipeline" 2>/dev/null; return 1
  fi
  hdr "$p"
  [ -f "$base" ] && ref="--ref $base"
  python scripts/ddrv_xtalk.py "$p" --ch 1 $ref --skip-frac 0.2 --label "$lbl" \
         --slew-desc "$desc" --csv "$RES" > "$EVD/ab_${lbl}.txt" 2>&1
  grep -aE "I_BASELINE|PEAK_CROSSTALK|PEAK_\||CHARGE_ERROR|GLITCH_|VBIAS_SHARED|vbias_ch1|RINGING" \
      "$EVD/ab_${lbl}.txt" | sed 's/^/  /'
  # the aggressor's own settling at the same time scale: item 10 asks for it at frame rate
  python scripts/ddrv_tran.py "$p" --label "${lbl}_ch0" > "$EVD/ab_${lbl}_ch0.txt" 2>&1
  grep -aE "TURN_ON_SETTLING|ON_SETTLED|RINGING" "$EVD/ab_${lbl}_ch0.txt" | sed 's/^/  /'
}

for leg in $LEG; do
case "$leg" in
A) echo "=========== LEG A: frame scale, integration method A/B (maxstep 5 ns)"
   for meth in default traponly gear2only; do
     mf=$(mflag $meth)
     bs=$(run_deck "A_base_${meth}" "$FRAME" 1e-8 none "$mf")
     echo "  baseline EN0=EN1=1 held, method=$meth"
     [ -f "${bs:-/nonexistent}" ] && hdr "$bs"
     for sl in 1e-10 1e-8 1e-7; do
       p=$(run_deck "A_${meth}_slew${sl}" "$FRAME" "$sl" 0 "$mf")
       analyse "$p" "A_${meth}_slew${sl}" "$bs" "T=9.765625us method=$meth maxstep=5ns slew=$sl FRAME_SCALE"
     done
   done ;;
B) echo "=========== LEG B: timestep convergence, frame scale, slew 10 ns"
   for meth in default traponly gear2only; do
     mf=$(mflag $meth)
     bs=$(run_deck "A_base_${meth}" "$FRAME" 1e-8 none "$mf")
     for ms in 5e-9 1e-9 5e-10; do
       if [ "$meth" = "default" ] && [ "$ms" = "5e-10" ]; then continue; fi
       p=$(run_deck "B_${meth}_ms${ms}" "$FRAME" 1e-8 0 "$mf --maxstep $ms")
       analyse "$p" "B_${meth}_ms${ms}" "$bs" "T=9.765625us slew=10ns method=$meth maxstep=$ms"
     done
   done ;;
C) echo "=========== LEG C: POC_STRESS_TEST only (T=200 ns, slew 10 ns)"
   for meth in default traponly gear2only; do
     mf=$(mflag $meth)
     bs=$(run_deck "C_base_${meth}" 2e-7 1e-8 none "$mf")
     p=$(run_deck "C_${meth}_T200" 2e-7 1e-8 0 "$mf")
     analyse "$p" "C_${meth}_T200" "$bs" "T=200ns POC_STRESS_TEST slew=10ns method=$meth maxstep=1ns"
   done ;;
D) echo "=========== LEG D: tolerance sensitivity, frame + slew 10 ns"
   BASE_RELTOL=$(grep -am1 '^"reltol"' spectre/generated/sim/ddrv_E_local_gate_n33_tt_l2e6w2e5_ch2_iprobe_A_default_slew1e-8_*/tran1.tran.tran 2>/dev/null | awk '{print $2}')
   echo "  default reltol read back from a LEG A run header: ${BASE_RELTOL:-NOT READ}"
   echo "  this build has no per-analysis reltol= (it is accepted and silently ignored, so"
   echo "  the knob is errpreset=conservative, which sets reltol 1e-4 but ALSO lteratio 10,"
   echo "  relref alllocal and method gear2only -- the method is therefore pinned per run and"
   echo "  every run's header is read back below to show what actually applied)"
   for meth in traponly gear2only; do
     mf=$(mflag $meth)
     bs=$(run_deck "A_base_${meth}" "$FRAME" 1e-8 none "$mf")
     p=$(run_deck "D_${meth}_epcons" "$FRAME" 1e-8 0 "$mf --errpreset conservative")
     analyse "$p" "D_${meth}_epcons" "$bs" "T=9.765625us slew=10ns method=$meth errpreset=conservative (reltol 10x tighter)"
   done ;;
esac
done

echo
echo "results: $RES"
echo "METHOD_AB_RUNS_DONE legs=$LEG"
