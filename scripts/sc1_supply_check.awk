
# SCAN-1 R1: dual-rail supply contract checker.
#   awk -v smap="vdd18=1.8 vdd33=3.3 vss=0" -v dir=. -f sc1_supply_check.awk <cells...> <deck>
# Emits SUPPLY_OK / SUPPLY_FAIL lines and "SUPPLY_NET <net>=<declared volts>" for phase 2.
# Port names are matched from the declared mapping, never by a vdd/vss name substring, and a
# supply-looking port that the contract does not mention is a failure rather than a silent pass.
function between(s,   a) { if (s !~ /\(/) return ""; a = s; sub(/^[^(]*\(/, "", a); sub(/\).*$/, "", a); return a }
function toks(spec, arr,   n, i, tmp, out) {
  n = split(spec, tmp, /[ \t,]+/); out = 0
  for (i = 1; i <= n; i++) if (tmp[i] != "") arr[++out] = tmp[i]
  return out
}
function srcval(n,   j, sv) {
  for (j = 1; j <= nvsrc; j++) {
    if (!((vplus[j] == "0" && vminus[j] == n) || (vminus[j] == "0" && vplus[j] == n))) continue
    sv = vval[j]
    if (sv ~ /^[+-]?[0-9.]/) return sv
    if (sv in param) return param[sv]
    return "UNRESOLVABLE"
  }
  return ""
}
tolower($1) == "parameters" { for (i = 2; i <= NF; i++) { split($i, pq, "="); if (pq[2] != "") param[pq[1]] = pq[2] } ; next }
{ raw = $0 }
raw ~ /^[ \t]*(\/\/|$)/ { next }
tolower($1) == "subckt" { cn = $2; portlist[cn] = between(raw); next }
tolower($1) == "ends" { next }
$1 ~ /^[Vv]/ && raw ~ /vsource/ {
  nl = toks(between(raw), a2); nvsrc++
  vplus[nvsrc] = a2[1]; vminus[nvsrc] = (nl > 1 ? a2[2] : "0")
  if (match(raw, /dc=[^ ]+/)) { sv = substr(raw, RSTART + 3, RLENGTH - 3); vval[nvsrc] = sv } else vval[nvsrc] = ""
  next
}
$1 ~ /^X/ && raw ~ /\(/ {
  nl = toks(between(raw), narr)
  cn = raw; sub(/^[^)]+\)[ \t]*/, "", cn); sub(/[ \t].*$/, "", cn)
  if (!(cn in portlist)) { print "SUPPLY_WARN instance " $1 " master " cn " port list not read (include unresolved?)"; next }
  split(portlist[cn], pp, /[ \t,]+/)
  for (i = 1; i <= nl && i <= length(pp) + 0; i++) if (pp[i] != "") conn[$1 " " pp[i]] = narr[i]
  ninst++; instlist[ninst] = $1; instsub[ninst] = cn
  next
}
END {
  bad = 0
  ns = split(smap, se, " ")
  for (e = 1; e <= ns; e++) {
    if (se[e] == "") continue
    if (index(se[e], "=") == 0) { printf "SUPPLY_FAIL malformed contract entry %s\n", se[e]; bad = 1; continue }
    split(se[e], kv, "="); sport[kv[1]] = kv[2]
  }
  if (ns == 0) { print "SUPPLY_FAIL empty contract"; exit 1 }
  if (ninst == 0) { print "SUPPLY_FAIL no subckt instance found: a contract over nothing must not pass"; print "SUPPLY_RESULT FAIL"; exit 1 }
  for (i = 1; i <= ninst; i++) {
    inst = instlist[i]
    npp = split(portlist[instsub[i]], pnarr, /[ \t,]+/)
    for (q = 1; q <= npp; q++) {
      pp2 = pnarr[q]; if (pp2 == "") continue
      low = tolower(pp2)
      if (low !~ /vdd|vss|vcc|gnd|substr|bulk|well/) continue
      if (pp2 in sport) continue
      printf "SUPPLY_FAIL instance %s (%s) exposes supply-like port %s that the contract does not map\n", inst, instsub[i], pp2
      bad = 1
    }
    for (e = 1; e <= ns; e++) {
      if (se[e] == "") continue
      split(se[e], kv, "=")
      n = conn[inst " " kv[1]]
      if (n == "") { printf "SUPPLY_FAIL instance %s (%s) does not connect declared supply port %s\n", inst, instsub[i], kv[1]; bad = 1; continue }
      sv = srcval(n)
      if (sv == "") { printf "SUPPLY_FAIL supply net %s (port %s of %s) has no independent source to reference node 0\n", n, kv[1], inst; bad = 1 }
      else if (sv == "UNRESOLVABLE") { printf "SUPPLY_FAIL cannot resolve the source value driving %s\n", n; bad = 1 }
      else if (sv + 0 != kv[2] + 0) { printf "SUPPLY_FAIL supply net %s (port %s) is driven to %s V but the contract declares %s V\n", n, kv[1], sv, kv[2]; bad = 1 }
      else printf "SUPPLY_OK %s=%s V on net %s for %s\n", kv[1], kv[2], n, inst
      printf "SUPPLY_NET %s=%s\n", n, kv[2]
    }
  }
  print (bad ? "SUPPLY_RESULT FAIL" : "SUPPLY_RESULT PASS")
}
