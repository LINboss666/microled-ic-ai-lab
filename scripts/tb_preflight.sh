#!/bin/bash
# tb_preflight.sh -- structural + operating-point sanity gate for a Spectre testbench.
#
#   tb_preflight.sh <abs.netlist> [expected_vdd] [tag]
#
# Why this exists: the earlier shift-unit failures came from a testbench whose `vss`
# net was never tied to the Spectre reference node 0. Every NMOS then had no current
# path, nodes floated above VDD, and Spectre still reported "0 errors, 0 warnings".
# A green log is not a valid testbench, so no formal transient runs until this gate
# says the rails are real.
#
# Phase 1 (static, no simulator). Parses the testbench and the subckts it includes,
#   maps each subckt instance's POSITIONAL net list onto the subckt's port names, and
#   requires, for every instance:
#     - its `vdd` port net to be driven by an independent source referenced to node 0,
#       at exactly the expected nominal value
#     - its `vss` port net to BE node 0, or tied to node 0 by an independent source
# Phase 2 (simulation of 1.5 ns, i.e. the operating point only). Rebuilds the netlist
#   with `save` for every connected net and every subckt internal node (hierarchical
#   names), then inspects the t=0 row:
#     - vdd == expected within 1e-6, vss == 0 within 1e-9      (violation => FAIL)
#     - any node above VDD or below the reference => RAIL_OVERSHOOT_WARNING
#       (reported, not fatal: on a real clock edge, overshoot on a node is information)
#
# Negative test for this tool: spectre/preflight_negative_vss_float.scs must FAIL here.
# Exit 0 only when phase 1 and the phase 2 rail checks pass.
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
NET="${1:?usage: tb_preflight.sh <abs.netlist> [expected_vdd] [tag]}"
VEXP="${2:-1.8}"
TAG="${3:-pre}"
RS="$PROJ/scripts/run_spectre.sh"
LOGD="$PROJ/logs"

case "$NET" in "$PROJ"/*) ;; *) echo "REFUSED: netlist must be under $PROJ (got $NET)"; exit 9 ;; esac
[ -r "$NET" ] || { echo "FATAL: $NET not found"; exit 8; }
[ -r "$RS" ] || { echo "FATAL: $RS missing"; exit 8; }
mkdir -p "$LOGD"

DIR="$(cd "$(dirname "$NET")" && pwd)"
BASE="$(basename "$NET" .scs)"
OUT="$LOGD/preflight_${BASE}_${TAG}.txt"
exec > >(tee "$OUT") 2>&1

echo "== testbench preflight: $NET (expected VDD=$VEXP)"

# ---------------------------------------------------------------- phase 1 ------
# AWK note: an instance line is `X1 (d clk q qbar vdd vss) c2mos_dff`, so the net list
# spans several fields -- it is extracted from $0 between the first '(' and ')'.
P1AWK='
  function between(s,  a) {            # text inside the first ( ... )
    if (s !~ /\(/) return ""
    a = s; sub(/^[^(]*\(/, "", a); sub(/\).*$/, "", a); return a
  }
  function toks(spec, arr,  n, i, tmp, out) {
    n = split(spec, tmp, /[ \t,]+/); out = 0
    for (i = 1; i <= n; i++) if (tmp[i] != "") arr[++out] = tmp[i]
    return out
  }
  tolower($1) == "parameters" {
    for (i = 2; i <= NF; i++) { split($i, pq, "="); if (pq[2] != "") param[pq[1]] = pq[2] }
    next
  }
  { raw = $0 }
  raw ~ /^[ \t]*\/\// { next }
  raw ~ /^[ \t]*$/ { next }
  tolower($1) == "include" {
    p = $2; gsub(/"/, "", p)
    if (p !~ /^\// && p !~ /^\$/) p = dir "/" p
    if (p ~ /\$/) { next }              # expanded by run_spectre.sh at run time
    inc[++ni] = p
    next
  }
  tolower($1) == "subckt" {
    cn = $2
    ncp = toks(between(raw), parr)
    s = ""
    for (i = 1; i <= ncp; i++) s = s (i > 1 ? " " : "") parr[i]
    portlist[cn] = s; ncp_cnt[cn] = ncp
    insub = 1; subname = cn
    next
  }
  tolower($1) == "ends" { insub = 0; next }
  insub {                               # inside a subckt: collect its nodes
    nc = toks(between(raw), narr)
    for (i = 1; i <= nc; i++) seen_node[narr[i]] = 1
    next
  }
  raw ~ /vsource/ {
    nl = toks(between(raw), narr)
    if (nl < 2) next
    val = ""
    for (i = 1; i <= NF; i++) {
      if ($i ~ /^dc=/)   { split($i, q, "="); val = q[2] }
      if ($i ~ /^val1=/) { split($i, q, "="); v1 = q[2] }
    }
    if (val == "") val = v1
    nvsrc++
    vplus[nvsrc] = narr[1]; vminus[nvsrc] = narr[2]; vval[nvsrc] = val
    next
  }
  $1 ~ /^X/ && raw ~ /\(/ {
    nl = toks(between(raw), narr)
    cn = raw; sub(/^[^)]+\)[ \t]*/, "", cn); sub(/[ \t].*$/, "", cn)
    if (!(cn in portlist)) next
    ncp = toks(portlist[cn], parr)
    for (i = 1; i <= nl && i <= ncp; i++) {
      conn[$1 " " parr[i]] = narr[i]
      allnets[narr[i]] = 1
    }
    ninst++; instlist[ninst] = $1; instsub[ninst] = cn
    next
  }
  END {
    bad = 0
    for (i = 1; i <= ninst; i++) {
      inst = instlist[i]
      vd = conn[inst " vdd"]; vs = conn[inst " vss"]
      if (vd == "") { print "STATIC_FAIL instance " inst " (subckt " instsub[i] ") exposes no vdd port"; bad = 1 }
      if (vs == "") { print "STATIC_FAIL instance " inst " (subckt " instsub[i] ") exposes no vss port"; bad = 1 }
      if (vd != "") {
        found = 0
        for (j = 1; j <= nvsrc; j++)
          if ((vplus[j] == vd && vminus[j] == "0") || (vminus[j] == vd && vplus[j] == "0")) {
            found = 1
            sv = vval[j]
            if (sv != "" && sv !~ /^-?[0-9.]/) {
              if (sv in param) sv = param[sv]
              else { printf "STATIC_FAIL cannot resolve source value '%s' on net %s\n", vval[j], vd; bad = 1; sv = "" }
            }
            if (sv != "" && sv + 0 != vexp + 0) {
              printf "STATIC_FAIL vdd net %s is driven to %s V, expected %s V\n", vd, sv, vexp
              bad = 1
            }
          }
        if (!found) { printf "STATIC_FAIL vdd net %s has no independent source to reference node 0 (no DC reference)\n", vd; bad = 1 }
        else printf "STATIC_OK vdd net %s referenced to node 0 at %s V\n", vd, vexp
      }
      if (vs != "") {
        if (vs == "0") print "STATIC_OK vss net is the reference node 0 itself"
        else {
          found = 0
          for (j = 1; j <= nvsrc; j++)
            if ((vplus[j] == vs && vminus[j] == "0") || (vminus[j] == vs && vplus[j] == "0")) found = 1
          if (!found) {
            printf "STATIC_FAIL vss net %s is NOT tied to reference node 0: it is a floating substrate/source net, every NMOS carrying current through it is silently dead\n", vs
            bad = 1
          } else print "STATIC_OK vss net " vs " tied to node 0 through an independent source"
        }
      }
    }
    if (ninst == 0) { print "STATIC_FAIL no subckt instance matched a known subckt definition -- the cell file was not parsed"; bad = 1 }
    s = ""
    for (k in allnets) s = s " " k
    print (bad ? "STATIC_RESULT FAIL" : "STATIC_RESULT PASS")
    printf "NETS_TO_SAVE%s\n", s
    printf "VDD_NETS%s\n", vddlist
  }'

# The subckt definitions live in included files, and an instance only maps onto a port
# list if that definition has been read first. Resolve the local (non-vendor) includes
# transitively -- three levels is far more than this project uses -- and hand them to
# the parser before the testbench itself. Paths here never contain spaces.
CELLFILES=""
_pending="$NET"
for lvl in 1 2 3; do
  found=""
  for f in $_pending; do
    [ -r "$f" ] || continue
    for inc in $(awk '/^[ \t]*include/ {p=$2; gsub(/"/,"",p); if (p !~ /\$/) print p}' "$f"); do
      case "$inc" in
        /*) p="$inc" ;;
        *)  p="$DIR/$inc" ;;
      esac
      [ -r "$p" ] || continue
      case " $CELLFILES " in *" $p "*) continue ;; esac
      CELLFILES="$CELLFILES $p"
      found="$found $p"
    done
  done
  [ -n "$found" ] || break
  _pending="$found"
done
echo "--- local cell files parsed for port lists:${CELLFILES:- none}"

STATIC=$(awk -v vexp="$VEXP" -v dir="$DIR" "$P1AWK" $CELLFILES "$NET")
echo "$STATIC"
static_verdict=$(echo "$STATIC" | awk '/^STATIC_RESULT/ {print $2}')
SAVE_NETS=$(echo "$STATIC" | awk '/^NETS_TO_SAVE/ {$1=""; print $0}')
VDD_NETS=$(echo "$STATIC" | awk '/^NETS_TO_SAVE/ {$1=""; for (i=2;i<=NF;i++) print $i}' | tr '\n' ' ')

# ---------------------------------------------------------------- phase 2 ------
PRE="$DIR/preflight_${BASE}_${TAG}.scs"
awk -v save_list="$SAVE_NETS" '
  /^[ \t]*$/ || /^[ \t]*\/\// { print; next }
  $2 == "tran" && $1 ~ /^[A-Za-z_]/ { print $1 " tran stop=1.5e-9 maxstep=2.5e-10"; tran_done = 1; next }
  /^save/ { print; next }
  { print }
  END {
    if (!tran_done) print "pf_tran tran stop=1.5e-9 maxstep=2.5e-10"
    if (save_list != "") print "save" save_list
  }' "$NET" > "$PRE"

# hierarchical saves for the subckt internal nodes (nodes that are not subckt ports)
CELLS="$CELLFILES"
INTSAVE=""
for cell in $CELLS; do
  [ -r "$cell" ] || continue
  INTSAVE="$INTSAVE $(awk '
    function between(s,  a) { if (s !~ /\(/) return ""; a=s; sub(/^[^(]*\(/,"",a); sub(/\).*$/,"",a); return a }
    /^[ \t]*(\/\/|$)/ { next }
    tolower($1) == "subckt" { n = split(between($0), po, /[ \t,]+/);
      for (i = 1; i <= n; i++) if (po[i] != "") port[po[i]] = 1; insub = 1; next }
    tolower($1) == "ends" { insub = 0; next }
    insub { m = split(between($0), nd, /[ \t,]+/)
      for (i = 1; i <= m; i++) if (nd[i] != "" && !(nd[i] in port)) node[nd[i]] = 1 }
    END { s = ""; for (k in node) s = s " " k; print s }' "$cell")"
done
if [ -n "$INTSAVE" ]; then
  { for inst in $(awk '/^X/ && $0 ~ /\(/ {print $1}' "$NET"); do
      for nd in $INTSAVE; do echo "save ${inst}.${nd}"; done
    done; } >> "$PRE"
fi

echo "--- preflight netlist: $PRE"
LABEL="PREFLIGHT_${TAG}" bash "$RS" "$PRE" 200 > "$LOGD/preflight_run_${BASE}_${TAG}.out" 2>&1
rc=$?
DATA=$(grep -aoE "CHECK datafile='[^']+'" "$LOGD/preflight_run_${BASE}_${TAG}.out" | sed -E "s/.*'(.*)'/\1/")
echo "spectre_rc=$rc datafile=${DATA:-none}"
if [ "$rc" != "0" ] || [ -z "$DATA" ] || [ ! -r "$DATA" ]; then
  echo "TESTBENCH_PREFLIGHT: FAIL  (operating-point probe produced no data)"
  grep -aE "ERROR|REFUSED|FATAL" "$LOGD/preflight_run_${BASE}_${TAG}.out" | head -5
  exit 1
fi

OP=$(awk '
  BEGIN { n = 0; got = 0 }
  /^VALUE/ { inb = 1; next }
  /^END/   { inb = 0 }
  inb && NF >= 2 {
    k = $1; gsub(/"/, "", k); v = $2 + 0
    if (k == "time" || k == "dc" || k == "sweep") { if (got) exit; got = 1; next }
    if (got) { val[k] = v; keys[++n] = k }
  }
  END { for (i = 1; i <= n; i++) printf "%s %.9g\n", keys[i], val[keys[i]] }' "$DATA")
echo "--- operating point at the first sample"
echo "$OP" | sed 's/^/    /'

fail=""
for v in $VDD_NETS; do
  [ -n "$v" ] || continue
  got=$(echo "$OP" | awk -v k="$v" '$1==k {print $2}')
  case "$v" in
    *vdd*|*VDD*) kind=vdd ;;
    *vss*|*VSS*|*gnd*) kind=vss ;;
    *) continue ;;
  esac
  [ -n "$got" ] || { echo "OP_FAIL no operating-point value for $kind net $v"; fail=1; continue; }
  if [ "$kind" = vdd ]; then
    ok=$(awk -v a="$got" -v b="$VEXP" 'BEGIN{ d=a-b; if(d<0)d=-d; print (d<=1e-6)?"yes":"no" }')
    [ "$ok" = "yes" ] && echo "OP_OK vdd net $v = $got (expected $VEXP)" \
                     || { echo "OP_FAIL vdd net $v = $got, expected $VEXP"; fail=1; }
  else
    ok=$(awk -v a="$got" 'BEGIN{ if(a<0)a=-a; print (a<=1e-9)?"yes":"no" }')
    [ "$ok" = "yes" ] && echo "OP_OK vss net $v = $got (must equal the reference)" \
                     || { echo "OP_FAIL vss net $v = $got is not at the reference potential"; fail=1; }
  fi
done

echo "--- rail check"
echo "$OP" | awk -v vexp="$VEXP" '
  { v = $2 + 0
    if (v > vexp + 0.05) { printf "RAIL_OVERSHOOT_WARNING %s=%.6g exceeds VDD=%.3g\n", $1, v, vexp; w++ }
    else if (v < -0.05)  { printf "RAIL_OVERSHOOT_WARNING %s=%.6g is below the reference\n", $1, v; w++ } }
  END { printf "RAIL_WARNINGS=%d\n", w + 0 }'

if [ "$static_verdict" != "PASS" ] || [ -n "$fail" ]; then
  echo "TESTBENCH_PREFLIGHT: FAIL"
  exit 1
fi
echo "TESTBENCH_PREFLIGHT: PASS"
exit 0
