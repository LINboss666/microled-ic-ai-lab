#!/usr/bin/env bash
# Reference runner for the course Spectre jobs. It does NOT start a simulation
# unless explicitly invoked with a case name, and it never auto-adds budget.
#
#   COURSE_NATIVE_DIR=<guest sandbox> bash run_course_spectre.sh <dc|tran|mc>
#
# Requires the native guest environment with:
#   * an untracked local env file exporting QODER_PDK_LIB (see pdk_local.env.example)
#   * skill/cad_env.sh on the guest to put spectre on PATH
# This script is documentation of the exact commands used in the real runs;
# all three jobs have ALREADY been executed and their budgets are exhausted.
set -uo pipefail

D="${COURSE_NATIVE_DIR:-/root/qoder_ic617_sandbox/course_sim_20261112}"
CASE="${1:-}"
case "$CASE" in
  dc)   NET=course_dc_tt.scs ;;
  tran) NET=course_tran_en.scs ;;
  mc)   NET=course_mc.scs ;;
  *) echo "usage: run_course_spectre.sh <dc|tran|mc>   (NO job started)"; exit 9 ;;
esac

echo "NOTE: this round's native budget is already spent (Spectre 3/3, MC 1x30)."
echo "NOTE: only run this after a NEW explicit authorisation."
echo "cd $D"
echo "set -a; . <untracked pdk_local.env>; set +a"
echo ". <sandbox>/bin/cad_env.sh"
echo "spectre $NET -64 -format psfascii"
echo "(command NOT executed by this reference script)"
exit 0
