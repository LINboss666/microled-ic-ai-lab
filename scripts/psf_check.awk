# PSF-ASCII waveform checker. Read one PSF-ASCII data file plus a directive file.
#
# Directives (whitespace separated):
#   ASSERT <sig> <t0> <t1> gt <v>   every sample of sig in [t0,t1] must be >  v
#   ASSERT <sig> <t0> <t1> lt <v>   every sample of sig in [t0,t1] must be <  v
#   CROSS  <sig> <v> [t0]           first RISING threshold crossing at or after t0
#   FALL   <sig> <v> [t0]           first FALLING threshold crossing at or after t0
#
# CROSS/FALL are real edge detectors, not "first sample above/below the threshold".
# A rising crossing needs an adjacent sample pair with
#       v_prev <= VTH  and  v_now > VTH
# and is then located by linear interpolation between the two samples:
#       t_cross = t_prev + (VTH - v_prev) / (v_now - v_prev) * (t_now - t_prev)
# t0 only restricts WHERE a crossing may be reported: a signal that is already high at
# t0 (and was never seen below the threshold inside the search) reports no crossing.
# If nothing crosses, the directive FAILs with an explicit "not-found" -- it never
# silently returns the last sample.
#
# Output: one line per directive prefixed OK/FAIL/BAD, then a summary line.
# Exit code 0 only when every ASSERT held and every CROSS/FALL was found.
# Used for transient checks: proving a shift register means proving windows of logic
# levels AND edge-anchored delays, not matching one exact sample time.
BEGIN { ndir = 0; nfail = 0 }

# linear interpolation of the crossing instant between two samples
function tcross(tp, vp, tn, vn, thr) {
  if (vn == vp) return tn
  return tp + (thr - vp) * (tn - tp) / (vn - vp)
}

# ---- pass 1: directives (spec file is the first argument) -------------------
NR == FNR {
  if ($1 == "" || $1 ~ /^#/) next
  ndir++
  kind[ndir] = $1
  if ($1 == "ASSERT") { sig[ndir]=$2; t0[ndir]=$3+0; t1[ndir]=$4+0; op[ndir]=$5; lim[ndir]=$6+0 }
  else                { sig[ndir]=$2; lim[ndir]=$3+0; tstart[ndir]=(NF>=4 ? $4+0 : -1) }
  nseen[ndir] = 0; nbad[ndir] = 0; firstv[ndir] = ""; lastv[ndir] = ""
  minv[ndir] = 1e30; maxv[ndir] = -1e30
  done[ndir] = 0; have[ndir] = 0; nedge[ndir] = 0
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
    if (kind[i] == "CROSS" || kind[i] == "FALL") {
      if (have[i] && !done[i]) {
        tc = -1
        if (kind[i] == "CROSS" && pvv[i] <= lim[i] && val > lim[i])
          tc = tcross(pvt[i], pvv[i], t, val, lim[i])
        else if (kind[i] == "FALL" && pvv[i] >= lim[i] && val < lim[i])
          tc = tcross(pvt[i], pvv[i], t, val, lim[i])
        if (tc >= tstart[i]) { done[i] = 1; tcut[i] = tc }
      }
      # remember every edge encountered, so a "first crossing after t0" test can also
      # prove that an earlier edge was really found (and where it was)
      if (have[i]) {
        if ((kind[i] == "CROSS"  && pvv[i] <= lim[i] && val > lim[i]) ||
            (kind[i] == "FALL"   && pvv[i] >= lim[i] && val < lim[i])) {
          nedge[i]++
          if (firstedge[i] == "") firstedge[i] = tcross(pvt[i], pvv[i], t, val, lim[i])
          ledge[i] = tcross(pvt[i], pvv[i], t, val, lim[i])
        }
      }
      pvt[i] = t; pvv[i] = val; have[i] = 1
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
      if (done[i])
        printf "OK   %-6s %s thr=%g t=%.12g%s edges=%d\n", kind[i], sig[i], lim[i], tcut[i], \
               (tstart[i] < 0 ? "" : sprintf(" t0=%.9g", tstart[i])), nedge[i]
      else {
        printf "FAIL %-6s %s thr=%g not-found%s edges=%d\n", kind[i], sig[i], lim[i], \
               (tstart[i] < 0 ? "" : sprintf(" after_t0=%.9g", tstart[i])), nedge[i]
        nfail++
      }
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
