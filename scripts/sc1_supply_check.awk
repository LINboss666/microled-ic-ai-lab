# SCAN-1 R2A: supply contract checker. Standalone awk on purpose -- an earlier revision nested
# this program inside the shell script's single-quoted string, where an escaping slip produced an
# unterminated string and silently broke even the legacy path.
#
#   awk -v smap="<entries>" -f scripts/sc1_supply_check.awk <cell files...> <top deck>
#
# Contract entry syntax, space separated:
#   port=volts        applies to any instance (at any depth) exposing that port     e.g. vdd33=3.3
#   master.port=volts applies only to instances of that subckt                      e.g. inv18.vdd=1.8
# Volts must be a finite plain number, or a deck parameter name the deck itself resolves.
# No silent +0 coercion: `vss=garbage` is refused, because awk turning a bad string into 0 would
# otherwise bless the very rail being checked.
#
# Netlist semantics actually implemented here:
#  * a net used inside a subckt body is that subckt's OWN net unless it is one of its port names;
#    a same-name coincidence with a top-level net is never treated as a connection.
#  * a supply port that resolves, through the port bindings, to a top-level net is checked against
#    the source holding that net; a supply port that resolves only to an internal node is reported as
#    SUPPLY_NOT_CERTIFIED and REFUSES the contract (R2B) -- counting it was never the same as
#    checking it, and a floating child substrate is exactly the failure this gate exists to catch.
#  * V(n) is signed: (0 n) vsource dc=-1.8 puts n at +1.8 V, and (n 0) dc=1.8 also does.
#  * a source wired between two declared supply nets forces a fixed difference between them; a
#    contract that contradicts it is refused instead of left for the simulator to discover.
#
# Emitted tokens (the wrapper requires the positive ones, it does not merely look for failure text):
#   SUPPLY_OK / SUPPLY_FAIL / SUPPLY_NOT_CERTIFIED / SUPPLY_TIE_OK / SUPPLY_NET <net>=<volts>
#   SUPPLY_INSTANCES top=<n> descendants=<d> checked=<m> internal=<i> masters=<k>
#   SUPPLY_RESULT PASS | SUPPLY_RESULT FAIL                exit 0 iff PASS

function between(s,   a) { if (s !~ /\(/) return ""; a = s; sub(/^[^(]*\(/, "", a); sub(/\).*$/, "", a); return a }
function toks(spec, arr,   n, i, tmp, out) {
  n = split(spec, tmp, /[ \t,]+/); out = 0
  for (i = 1; i <= n; i++) if (tmp[i] != "") arr[++out] = tmp[i]
  return out
}
function is_supplyish(n) {
  n = tolower(n)
  return (n ~ /^vdd/ || n ~ /^vss/ || n ~ /^vcc/ || n ~ /^gnd/ || n == "0" ||
          n ~ /substr/ || n ~ /bulk/ || n ~ /well/)
}
# strict numeric parse: finite, no trailing junk, not empty. Returns 1/0 and leaves the value in the
# NUM global -- awk parameters are always local, so a value cannot be returned through one.
function parsevol(txt) {
  txt = txt ""
  gsub(/^[ \t]+|[ \t]+$/, "", txt)
  if (txt == "") return 0
  if (txt !~ /^[+-]?([0-9]+\.?[0-9]*|\.[0-9]+)([eE][+-]?[0-9]+)?$/) return 0
  NUM = txt + 0
  if (NUM != NUM) return 0                      # NaN, without relying on isfinite
  if (NUM > 1e30 || NUM < -1e30) return 0
  return 1
}
# index of `net` in subckt `def`'s port list; 0 means it is one of def's own internal nets
function portidx(def, net,   n, i, p) {
  n = split(portlist[def], p, /[ \t,]+/)
  for (i = 1; i <= n; i++) if (p[i] == net) return i
  return 0
}
# map a net used inside `def` (caller-side names in g[1..]) up one level. Internal nodes get an
# "@def.net" marker so nothing downstream can mistake them for a global rail. Node 0 is the
# simulator reference and is global by definition: a subckt cannot shadow it.
function rname(def, g, net,   pi) {
  if (net == "0") return "0"
  pi = portidx(def, net); if (pi > 0) return g[pi]; return "@" def "." net
}
function isinternal(n) { return (substr(n, 1, 1) == "@") }
# difference of two declared rail potentials cannot be compared bit-exactly: 3.3-1.8 is
# 1.4999999999999998 in IEEE double. Only a stated tolerance can tell a real conflict from rounding.
function aeq(x, y,   d) { d = x - y; if (d < 0) d = -d; return d <= 1e-9 }
# potential an independent source holds global net `n` at, referenced to node 0.
# "" = nothing drives it; "UNRESOLVABLE" = driven by a value the deck's parameters cannot resolve.
function srcval(n,   j, sv, sign) {
  for (j = 1; j <= nvsrc; j++) {
    if (vplus[j] == n && vminus[j] == "0") sign = 1
    else if (vminus[j] == n && vplus[j] == "0") sign = -1
    else continue
    sv = vval[j]
    if (parsevol(sv)) return sign * NUM
    if ((sv in param) && parsevol(param[sv])) return sign * NUM
    return "UNRESOLVABLE"
  }
  return ""
}
BEGIN { ninst = 0; nvsrc = 0; insub = 0; nsubdef = 0; ntie = 0; desc = 0; checked = 0; intern = 0; bad = 0 }
tolower($1) == "parameters" {
  for (i = 2; i <= NF; i++) { split($i, pq, "="); if (pq[2] != "") param[pq[1]] = pq[2] }
  next
}
{ raw = $0 }
raw ~ /^[ \t]*(\/\/|$)/ { next }
tolower($1) == "subckt" {
  cn = $2; portlist[cn] = between(raw); nsubdef++
  curdef = (insub > 0 ? curdef "/" cn : cn)
  insub++
  next
}
tolower($1) == "ends" { insub--; if (insub < 0) insub = 0; next }
# top-level independent sources define the rails; a source inside a subckt body is legal netlist
# content but is never the bench's supply reference, so it is not collected as one.
insub == 0 && $1 ~ /^[Vv]/ && raw ~ /vsource/ {
  nl = toks(between(raw), srcn); nvsrc++
  vplus[nvsrc] = srcn[1]; vminus[nvsrc] = (nl > 1 ? srcn[2] : "0")
  gnet[srcn[1]] = 1; if (nl > 1) gnet[srcn[2]] = 1
  if (match(raw, /dc=[^ ]+/)) vval[nvsrc] = substr(raw, RSTART + 3, RLENGTH - 3); else vval[nvsrc] = ""
  if (vplus[nvsrc] != "0" && vminus[nvsrc] != "0") {
    ntie++; tiea[ntie] = vplus[nvsrc]; tieb[ntie] = vminus[nvsrc]; tiev[ntie] = vval[nvsrc]
  }
  next
}
insub == 0 && $1 ~ /^X/ && raw ~ /\(/ {
  nl = toks(between(raw), narr)
  cn = raw; sub(/^[^)]+\)[ \t]*/, "", cn); sub(/[ \t].*$/, "", cn)
  for (q = 1; q <= nl; q++) gnet[narr[q]] = 1
  ninst++; instlist[ninst] = $1; instsub[ninst] = cn; instnets[ninst] = between(raw)
  next
}
# a child instance inside a subckt DEFINITION: recorded per definition and resolved later by walking
# the port bindings -- never handed to the checker as if its local nets were global.
insub > 0 && $1 ~ /^X/ && raw ~ /\(/ {
  cn = raw; sub(/^[^)]+\)[ \t]*/, "", cn); sub(/[ \t].*$/, "", cn)
  nkids[curdef]++; j = nkids[curdef]
  kidmaster[curdef, j] = cn; kidname[curdef, j] = $1; kidnets[curdef, j] = between(raw)
  next
}
END {
  # ---- parse the contract ----
  ns = split(smap, se, " ")
  if (ns <= 1 && smap !~ /=/) { print "SUPPLY_FAIL empty or malformed contract"; print "SUPPLY_RESULT FAIL"; exit 1 }
  for (e = 1; e <= ns; e++) {
    ent = se[e]; if (ent == "") continue
    if (index(ent, "=") == 0) { printf "SUPPLY_FAIL malformed contract entry %s (expected port=volts)\n", ent; bad = 1; continue }
    split(ent, kv, "=")
    pname = kv[1]; vtxt = kv[2]
    split(vtxt, junk, /[ \t]/)
    if (junk[2] != "") { printf "SUPPLY_FAIL contract value for %s is not a single token: %s\n", pname, vtxt; bad = 1; continue }
    if (!parsevol(vtxt)) { printf "SUPPLY_FAIL contract value for %s is not a finite number: %s\n", pname, vtxt; bad = 1; continue }
    pv = NUM
    if (pname in contract_val) {
      if (contract_val[pname] + 0 != pv + 0)
        printf "SUPPLY_FAIL duplicate contract entry %s conflicts (%s vs %s)\n", pname, contract_val[pname], pv
      else printf "SUPPLY_FAIL duplicate contract entry %s\n", pname
      bad = 1; continue
    }
    contract_val[pname] = pv; ndecl++
  }
  if (ndecl == 0) { print "SUPPLY_FAIL no valid contract entry"; print "SUPPLY_RESULT FAIL"; exit 1 }
  if (ninst == 0) { print "SUPPLY_FAIL no top-level instance found: a contract over nothing must not pass"; print "SUPPLY_RESULT FAIL"; exit 1 }

  # ---- two sources driving the same rail to node 0 must agree ----
  for (j = 1; j <= nvsrc; j++) {
    if (vplus[j] != "0" && vminus[j] != "0") continue
    rn = (vplus[j] == "0" ? vminus[j] : vplus[j]); sgn = (vplus[j] == "0" ? -1 : 1)
    if (parsevol(vval[j])) vv = sgn * NUM
    else if ((vval[j] in param) && parsevol(param[vval[j]])) vv = sgn * NUM
    else continue
    if (rn in drive1) {
      if (!aeq(drive1[rn] + 0, vv + 0)) { printf "SUPPLY_FAIL net %s is driven to both %s V and %s V by separate sources\n", rn, drive1[rn], vv; bad = 1 }
    } else drive1[rn] = vv
  }

  # ---- unresolved masters: cannot certify what was never parsed ----
  for (i = 1; i <= ninst; i++)
    if (!(instsub[i] in portlist)) {
      printf "SUPPLY_FAIL instance %s master %s port list unresolved (include not parsed): cannot certify its supplies\n", instlist[i], instsub[i]
      bad = 1
    }

  # ---- audit every top-level instance, then its descendants through the port bindings ----
  for (i = 1; i <= ninst; i++) {
    inst = instlist[i]; cn = instsub[i]
    if (!(cn in portlist)) continue
    ng = toks(instnets[i], gn)
    np = split(portlist[cn], ep, /[ \t,]+/)
    if (ng < np) { printf "SUPPLY_FAIL instance %s (%s) connects %d nets to %d ports\n", inst, cn, ng, np; bad = 1 }
    split("", a)
    for (k = 1; k <= np; k++) a[k] = (k <= ng ? gn[k] : "")
    top_check(cn, a, inst, np)
    down(cn, a, inst, 1)
  }

  # ---- a source tying two declared rails together must match the contract ----
  for (j = 1; j <= ntie; j++) {
    if (!(tiea[j] in declared_net) || !(tieb[j] in declared_net)) continue
    if (parsevol(tiev[j])) off = NUM
    else if ((tiev[j] in param) && parsevol(param[tiev[j]])) off = NUM
    else continue
    want = declared_net[tiea[j]] - declared_net[tieb[j]]
    if (!aeq(off + 0, want + 0)) {
      printf "SUPPLY_FAIL source between rails %s and %s forces %s V, contract says %s V\n", tiea[j], tieb[j], off, want
      bad = 1
    } else printf "SUPPLY_TIE_OK %s-%s = %s V consistent\n", tiea[j], tieb[j], off
  }

  # ---- a declared entry that matched nothing anywhere is a contract bug, not a pass ----
  for (k in contract_val) if (!(k in hit)) { printf "SUPPLY_FAIL contract entry %s matches no instance port\n", k; bad = 1 }
  printf "SUPPLY_INSTANCES top=%d descendants=%d checked=%d internal=%d masters=%d\n", ninst, desc, checked, intern, nsubdef
  print (bad ? "SUPPLY_RESULT FAIL" : "SUPPLY_RESULT PASS")
  exit (bad ? 1 : 0)
}
# check one instance's supply ports; a[1..np] hold caller-side (global or @internal) names
function top_check(cn, a, path, np,   k, pn, key, n, want, sv, ports) {
  split(portlist[cn], ports, /[ \t,]+/)
  for (k = 1; k <= np; k++) {
    pn = ports[k]; if (pn == "") continue
    if (!is_supplyish(pn) && !((cn "." pn) in contract_val) && !(pn in contract_val)) continue
    if ((cn "." pn) in contract_val) key = cn "." pn
    else if (pn in contract_val) key = pn
    else { printf "SUPPLY_FAIL %s (%s) supply-like port %s is not covered by the contract\n", path, cn, pn; bad = 1; continue }
    hit[key] = 1
    n = a[k]
    if (n == "") { printf "SUPPLY_FAIL %s port %s has no net\n", path, pn; bad = 1; continue }
    want = contract_val[key]
    declared_net[n] = want
    if (isinternal(n)) {
      # An internal node can share its name with a top-level rail while sitting at a different
      # potential. Certification must not silently pick one reading, so a colliding name refuses.
      lname = n; sub(/^@/, "", lname); sub(/.*\./, "", lname)
      if (lname in gnet) {
        printf "SUPPLY_FAIL %s port %s resolves to internal node %s, but the deck also has a top-level net named %s: refusing to guess which rail drives it\n", path, pn, n, lname
        bad = 1
      } else {
        # R2B: counting an uncertifiable supply was not enough. Under a formal supply contract a
        # supply or reference port that never resolves to a certified rail FAILS the gate -- the
        # project has already been bitten by a floating vss that left every NMOS dead while the
        # simulator still finished cleanly. NOT_CERTIFIED is reported for diagnosis only.
        printf "SUPPLY_NOT_CERTIFIED %s port %s is internal node %s: potential is set inside the parent, preflight cannot certify it\n", path, pn, n
        intern++
        printf "SUPPLY_FAIL %s port %s is not certified: it maps to internal node %s instead of a rail the contract covers; every supply/reference port must reach a declared rail through subckt ports\n", path, pn, n
        bad = 1
      }
      continue
    }
    if (n == "0") {
      if (aeq(want + 0, 0)) { printf "SUPPLY_OK %s port %s is reference node 0\n", path, pn; checked++ }
      else { printf "SUPPLY_FAIL %s port %s tied to node 0 but contract declares %s V\n", path, pn, want; bad = 1 }
      printf "SUPPLY_NET 0=0\n"
      continue
    }
    sv = srcval(n)
    if (sv == "") { printf "SUPPLY_FAIL net %s (%s port %s) has no independent source from reference node 0\n", n, path, pn; bad = 1 }
    else if (sv == "UNRESOLVABLE") { printf "SUPPLY_FAIL cannot resolve the source value driving %s (%s port %s)\n", n, path, pn; bad = 1 }
    else if (!aeq(sv + 0, want + 0)) { printf "SUPPLY_FAIL net %s (%s port %s) driven %s V, contract %s=%s V\n", n, path, pn, sv, key, want; bad = 1 }
    else { printf "SUPPLY_OK %s.%s = %s V via net %s\n", path, pn, want, n; checked++ }
    printf "SUPPLY_NET %s=%s\n", n, want
  }
}
# recurse into the children of subckt cn, mapping their nets up through cn's own caller names
function down(cn, a, path, depth,   j, m, kid, nl, np, i, cg, kn, mp) {
  if (depth > 8) { printf "SUPPLY_FAIL hierarchy deeper than 8 levels below %s: refusing to guess\n", path; bad = 1; return }
  for (j = 1; j <= nkids[cn] + 0; j++) {
    m = kidmaster[cn, j]; kid = path "." kidname[cn, j]
    if (!(m in portlist)) { printf "SUPPLY_FAIL %s master %s port list unresolved: cannot certify its supplies\n", kid, m; bad = 1; continue }
    nl = toks(kidnets[cn, j], kn)
    np = split(portlist[m], mp, /[ \t,]+/)
    if (nl < np) { printf "SUPPLY_FAIL %s (%s) connects %d nets to %d ports\n", kid, m, nl, np; bad = 1 }
    split("", cg)
    for (i = 1; i <= np; i++) cg[i] = (i <= nl ? rname(cn, a, kn[i]) : "")
    desc++
    top_check(m, cg, kid, np)
    down(m, cg, kid, depth + 1)
  }
}
