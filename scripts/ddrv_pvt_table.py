#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ddrv_pvt_table.py -- derive results/data_driver_pvt.csv from the DC sweep file.

The three corners were run as ordinary DC sweeps through the same pipeline, so their
rows already live in results/data_driver_dc.csv under the labels `..._pvt<corner>`.
Splitting them into their own file is a view over committed evidence, not a new
measurement: no simulation runs here, and nothing is retyped.

    python scripts/ddrv_pvt_table.py [--dc results/data_driver_dc.csv]
                                     [--out results/data_driver_pvt.csv]
"""

from __future__ import print_function

import argparse
import io
import re

HEADER = "corner,vsw_V,vout_device_V,iout_uA,err_pct,vbias_V\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dc", default="results/data_driver_dc.csv")
    ap.add_argument("--out", default="results/data_driver_pvt.csv")
    a = ap.parse_args()

    # label shape: <candidate>_<model>_<corner>_l2e-6_w2e-5_dc_pvt<corner>
    # the geometry tokens contain hyphens, so [\w] alone silently matched nothing.
    rx = re.compile(r"^[\w]+_([\w]+)_(tt|ss|ff)_l[\w.-]+w[\w.-]+_dc_pvt(tt|ss|ff)$")
    rows, corners = [], set()
    with io.open(a.dc, encoding="utf-8", errors="replace") as fh:
        header = fh.readline().strip().split(",")
        for line in fh:
            parts = line.rstrip("\n").split(",")
            if len(parts) != len(header):
                continue
            m = rx.match(parts[0])
            if not m:
                continue
            corners.add(m.group(3))
            rows.append("%s,%s,%s,%s,%s,%s\n" % (m.group(3), parts[1], parts[2],
                                                 parts[3], parts[4], parts[5]))
    if not rows:
        print("DATA_DRIVER_PVT_TABLE: FAIL (no PVT-labelled rows found in %s; the sweep "
              "file does not contain the corner runs)" % a.dc)
        print("ddrv_pvt_table: wrote 0 rows")
        return 1
    # binary write with an explicit encode: io.open(..., encoding=...) on the guest's
    # Python 2.6 refuses native str, and this file has to run on both interpreters.
    blob = HEADER + "".join(rows)
    if not isinstance(blob, bytes):
        blob = blob.encode("utf-8")
    with open(a.out, "wb") as fh:
        fh.write(blob)
    print("ddrv_pvt_table: wrote %d rows for corners %s from %s"
          % (len(rows), ",".join(sorted(corners)), a.dc))
    print("DATA_DRIVER_PVT_TABLE: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
