# psf_dump.awk -- print a sampled table of every trace in a PSF-ASCII file.
#
#   awk -v every=5000 -f psf_dump.awk <psf-file>
#       one row every `every` sweep points (default 5000)
#   awk -v from=4.8e-7 -v to=6.0e-7 -f psf_dump.awk <psf-file>
#       every row inside the time window, capped at 400 rows
#   awk -v want="clk d12 q12" -f psf_dump.awk <psf-file>
#       keep only these traces (a multi-instance sweep saves 27 traces, which is wider
#       than a terminal, so filtering is what makes the numbers readable)
#
# PSF-ASCII writes one "key value" pair per line inside the VALUE section, so a row is
# accumulated until the next sweep point. This exists because debugging a digital cell
# means having to SEE the internal nodes, not only assert windows on the outputs.
BEGIN {
  inb = 0; row = ""; cnt = 0; shown = 0
  if (every == "") every = 5000
  if (cap == "") cap = 400
  ranged = (from != "" || to != "")
  if (want != "") { nw = split(want, w, " "); for (j = 1; j <= nw; j++) keep[w[j]] = 1 }
}
/^VALUE/ { inb = 1; next }
/^END/   { inb = 0; next }
inb && NF >= 2 {
  key = $1; gsub(/"/, "", key); val = $2
  if (key == "logFile" || key == "PSFversion") next
  if (key == "time" || key == "dc" || key == "sweep") {
    cnt++
    tv = val + 0
    if (ranged) {
      lo = (from == "" ? -1e30 : from + 0); hi = (to == "" ? 1e30 : to + 0)
      if (tv >= lo && tv <= hi) {
        in_cnt++
        if (in_cnt % every == 0 && shown < cap) { shown++; printf "t=%-14s %s\n", val, row }
      }
    } else if (cnt % every == 0) {
      printf "t=%-14s %s\n", val, row
    }
    row = ""
    next
  }
  # the trace filter must not hide the sweep column, so it comes after it
  if (nw && !(key in keep)) next
  row = row sprintf("%s=%.6f ", key, val + 0)
}
END { printf "rows_seen=%d mode=%s printed=%d\n", cnt, (ranged ? "range" : "every=" every), shown }
