# PSF-ASCII waveform checker. Read one PSF-ASCII data file plus a directive file.
# Directives (whitespace separated):
#   ASSERT <sig> <t0> <t1> gt <v>    every sample of sig in [t0,t1] must be >  v
#   ASSERT <sig> <t0> <t1> lt <v>    every sample of sig in [t0,t1] must be <  v
#   CROSS  <sig> <v> [t0]            the FIRST time AFTER t0 that sig rises above v
#   FALL   <sig> <v> [t0]            the FIRST time AFTER t0 that sig falls below v
#           (t0 defaults to -inf; it is what makes per-clock-edge clk->Q delays
#            measurable instead of just "the first transition in the whole run")
# Prints one line per directive prefixed OK/FAIL/BAD, then a summary line.
# Exit code 0 only when every ASSERT held and every CROSS/FALL was found.
# Used for transient checks, where proving a shift register means proving windows
# of logic levels, not matching one exact sample time.
BEGIN { ndir = 0; nfail = 0 }

# ---- pass 1: directives (spec file is the first argument) -------------------
NR == FNR {
  if ($1 == "" || $1 ~ /^#/) next
  ndir++
  kind[ndir] = $1
  if ($1 == "ASSERT") { sig[ndir]=$2; t0[ndir]=$3+0; t1[ndir]=$4+0; op[ndir]=$5; lim[ndir]=$6+0 }
  else                { sig[ndir]=$2; lim[ndir]=$3+0; tstart[ndir]=(NF>=4 ? $4+0 : -1) }
  nseen[ndir] = 0; nbad[ndir] = 0; firstv[ndir] = ""; lastv[ndir] = ""; minv[ndir] = 1e30; maxv[ndir] = -1e30
  done[ndir] = 0
  next
}

# ---- pass 2: the data file --------------------------------------------------
/^SWEEP/ { insw = 1; next }
/^TRACE/ { insw = 0; next }
insw && NF >= 2 && swkey == "" { k = $1; gsub(/"/, "", k); swkey = k; next }
/^VALUE/ { inb = 1; next }
/^END/   { inb = 0; next }

inb && NF >= 2 {
  key = $1; gsub(/"/, "", key); val = $2 + 0
  if (key == swkey) { t = val; next }
  for (i = 1; i <= ndir; i++) {
    if (sig[i] != key) continue
    if (kind[i] == "CROSS") {
      if (!done[i] && t >= tstart[i] && val > lim[i]) { done[i] = 1; tcut[i] = t }
      continue
    }
    if (kind[i] == "FALL") {
      if (!done[i] && t >= tstart[i] && val < lim[i]) { done[i] = 1; tcut[i] = t }
      continue
    }
    if (t >= t0[i] && t <= t1[i]) {
      nseen[i]++
      if (firstv[i] == "") firstv[i] = val
      lastv[i] = val
      if (val < minv[i]) minv[i] = val
      if (val > maxv[i]) maxv[i] = val
      if (op[i] == "gt" && val <= lim[i]) nbad[i]++
      if (op[i] == "lt" && val >= lim[i]) nbad[i]++
    }
  }
}

END {
  printf "sweep_key=%s\n", (swkey == "" ? "NONE" : swkey)
  for (i = 1; i <= ndir; i++) {
    if (kind[i] == "CROSS" || kind[i] == "FALL") {
      if (done[i]) printf "OK   %-6s %s thr=%g t=%.9g%s\n", kind[i], sig[i], lim[i], tcut[i], \
                         (tstart[i] < 0 ? "" : sprintf(" t0=%.9g", tstart[i]))
      else       { printf "FAIL %-6s %s thr=%g never-crossed\n", kind[i], sig[i], lim[i]; nfail++ }
      continue
    }
    if (nseen[i] < 3) {
      printf "FAIL ASSERT %s [%.9g,%.9g] %s %g  too-few-samples(n=%d)\n", sig[i], t0[i], t1[i], op[i], lim[i], nseen[i]; nfail++; continue
    }
    if (nbad[i] == 0)
      printf "OK   ASSERT %s [%.9g,%.9g] %s %g  n=%d min=%.6g max=%.6g\n", sig[i], t0[i], t1[i], op[i], lim[i], nseen[i], minv[i], maxv[i]
    else {
      printf "FAIL ASSERT %s [%.9g,%.9g] %s %g  n=%d min=%.6g max=%.6g viol=%d\n", sig[i], t0[i], t1[i], op[i], lim[i], nseen[i], minv[i], maxv[i], nbad[i]; nfail++
    }
  }
  printf "SUMMARY directives=%d failed=%d\n", ndir, nfail
  exit (nfail == 0 ? 0 : 1)
}
