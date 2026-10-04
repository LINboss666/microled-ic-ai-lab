#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Micro LED display-array driving: system-level baseline arithmetic.

Pure Python, no Cadence, no third-party modules. Runs on the guest's system Python
2.6.6 and on Python 3.x (RHEL6 has no python3), hence indexed "{0}" placeholders.

TOPOLOGY OF RECORD (corrected 2026-10-04 after reading the course specification; the
earlier version of this file wrongly assumed data=columns / scan=rows):

  - The panel is 1024 columns x 768 rows (course spec, para 8).
  - Data drivers are the ROW drivers: 左右两颗, 每颗 384 通道, 合计 768 (para 8/17/69/72).
  - Scan drivers are the COLUMN drivers: 上下两颗, 每颗 512 通道, 合计 1024 (para 8/17/75-79).
  - Scanning is column-by-column (para 32 "扫描驱动属于列驱动", Figure 3 逐列扫描).
  - Therefore one selected scan electrode carries up to 768 pixels -> I_SCAN_MAX =
    768 x 15 uA = 11.52 mA (course doc states the same number; NOT 15.36 mA).

Definition of record for current (confirmed by the student 2026-10-04):
  I_PIXEL = 15 uA is the INSTANTANEOUS current of a selected, emitting pixel. Frame
  averages are DERIVED from the select duty cycle, never the other way round.

Anything the course material does not state stays NOT DEFINED and is never silently
assumed into a number. Every derived value carries a "basis" string.

Usage:
    python microled_arch_calc.py [--outdir ROOT] [--json-only] [--quiet]
"""
from __future__ import print_function

import argparse
import json
import math
import os
import sys

# ------------------------------------------------- given / established by the course
N_COLUMNS = 1024          # 1024 列  (source: 课程规格书 V1.2 para 8)
N_ROWS = 768              # 768 行   (source: 课程规格书 V1.2 para 8)
PIXEL_SIZE_UM = 5.0       # 5 um 名义像素；pitch 是否等于它 NOT DEFINED
I_PIXEL_UA = 15.0         # 瞬时（选通发光）电流，D1
REFRESH_HZ = [60.0, 100.0]
N_DATA_DRIVERS = 2        # 左右：行驱动
N_SCAN_DRIVERS = 2        # 上下：列驱动

SPEC_SOURCE = "MicroLED_1024x768_Driver_IC_Specification_V1.2.docx (course_source/spec_v12_text.txt)"
NOT_DEFINED = "NOT DEFINED"

ROWS_PER_SCAN_LINE = N_ROWS                    # pixels on one selected column
COLS_PER_DATA_LINE = N_COLUMNS                 # a row electrode touches 1024 pixels but sinks only its own LED
# a data channel is one row's current sink -> 15 uA per pixel on that row when its column is selected

ASSUMPTIONS = [
    ("A1", "Blanking / retrace overhead", "部分给定：课程规格书给出保护留白 60Hz 3.476041667 us / 100Hz 2.085625 us",
     "时间预算直接使用课程口径，未另行假设。"),
    ("A2", "Gray scale bit depth", "8-bit 视频输入（课程规格书）；调制为 Hybrid 3+6 推荐 / 2+6 与 Pure 8-bit 对照",
     "数据速率按课程口径计算；灰阶光学有效性仍标【待实测】。"),
    ("A3", "PWM 位深 / 发光窗口", "课程假设：窗口 = 256/fPWM，60Hz 12.8 us / 100Hz 7.68 us",
     "标记为【课程设计假设】，不是实测。"),
    ("A4", "Scan multiplex factor", "1 column at a time（课程：全局最多一列有效）",
     "由课程规格书明确，不再是本脚本自加假设。"),
    ("A5", "pixel pitch == 5 um?", NOT_DEFINED,
     "5.12 x 3.84 mm 是课程名义像素面积推算值，非制造尺寸。"),
    ("A6", "LED forward voltage", "无题面数值。课程规格书只给『条件 VLED 5.0 V 与 Vf 门槛 4.4 V』且标【课程设计假设】【待实测】",
     "本脚本不引入 Vf，不做功耗结论。"),
    ("A7", "CMOS node / devices", "已固定：SMIC 0.18um Mixed-Signal RF，老师交付副本 smic18mmrf_teacher（只有 1.8 V 与 3.3 V 器件族）",
     "与课程『条件 5.0 V 高边输出域』存在器件耐压缺口，属于待决问题，见 reports/topology_channel_check.md。"),
    ("A8", "Data 接口形式", "课程口径：列优先，每个 COL_SYNC 后接收 Row0..Row767 共 768 字节；双路装载 384/50 MHz",
     "通道速率按此计算。"),
]


def compute():
    pixels = N_COLUMNS * N_ROWS
    i_pix = I_PIXEL_UA * 1e-6

    cols_per_data_driver = int(math.ceil(N_ROWS / float(N_DATA_DRIVERS)))    # 384
    rows_per_scan_driver = int(math.ceil(N_COLUMNS / float(N_SCAN_DRIVERS)))  # 512

    scan_line_pixels = ROWS_PER_SCAN_LINE                  # a column has 768 pixels
    i_scan_max = scan_line_pixels * i_pix                  # 11.52 mA
    i_data_driver_max = cols_per_data_driver * i_pix       # 5.76 mA
    duty = 1.0 / N_COLUMNS                                 # one of 1024 columns selected (A4)

    per_rate = []
    for f in REFRESH_HZ:
        ft = 1.0 / f
        col_period = ft / N_COLUMNS
        row_equivalent = ft / N_ROWS
        per_rate.append({
            "refresh_hz": f,
            "frame_time_s": ft,
            "column_scan_rate_hz": N_COLUMNS * f,
            "column_period_us": col_period * 1e6,
            "per_selected_column_available_time_s": col_period,
            "row_data_slot_us": (col_period / N_ROWS) * 1e6,
            "frame_data_bytes": pixels,
            "raw_video_throughput_Mb_s": pixels * 8 * f / 1e6,
            "min_input_clock_MHz": pixels * f / 1e6,
            "data_channels_per_driver": cols_per_data_driver,
            "data_channels_total": cols_per_data_driver * N_DATA_DRIVERS,
            "scan_channels_per_driver": rows_per_scan_driver,
            "scan_channels_total": rows_per_scan_driver * N_SCAN_DRIVERS,
            "scan_duty": duty,
            "instantaneous_scan_line_current_mA": i_scan_max * 1e3,
            "derived_panel_average_current_mA": i_scan_max * 1e3,
            "derived_pixel_average_current_nA": i_pix * duty * 1e9,
            "per_data_channel_current_uA": I_PIXEL_UA,
            "derived_data_driver_average_current_mA": i_data_driver_max * 1e3,
            "basis": {
                "column_period": "1/(N_COLUMNS*f) with N_COLUMNS=1024 (A4: 全局最多一列有效)",
                "scan_line_current": "N_ROWS x I_PIXEL = 768 x 15 uA (scan electrode = one column)",
                "panel_average": "equals the instantaneous scan-line current because exactly one "
                                 "column is always selected and no blanking current flows",
                "pixel_average": "I_PIXEL x duty, duty = 1/1024 (D1 direction: average is DERIVED)",
                "data_driver": "channels_per_driver x I_PIXEL = 384 x 15 uA = 5.76 mA",
            },
        })

    return {
        "source": "COURSE_REQUIREMENT (instructor assignment text + user-confirmed D1)",
        "legacy_reference": "GPT6_LEGACY_PROPOSAL: the MicroLED V1.2 delivery pack is a "
                            "generated proposal, not a source of record",
        "topology_of_record": {
            "panel": "1024 columns x 768 rows",
            "scan_selects": "COLUMN (列扫描, 高边开关选列)",
            "data_drives": "ROW (行驱动, 恒流吸收)",
            "data_driver_ic": {"count": N_DATA_DRIVERS, "channels_each": cols_per_data_driver,
                               "placement": "左右", "even_odd": "偶/奇行"},
            "scan_driver_ic": {"count": N_SCAN_DRIVERS, "channels_each": rows_per_scan_driver,
                               "placement": "上下", "even_odd": "偶/奇列"},
            "evidence": SPEC_SOURCE,
            "correction_note": "earlier version of this file had data=1024/scan=768; that was an "
                               "unverified assumption and is reversed here",
        },
        "definition_D1": {
            "I_pixel_uA": I_PIXEL_UA,
            "meaning": "instantaneous current of a selected, emitting pixel (student-confirmed 2026-10-04)",
            "rule": "frame averages are derived from duty; never treat 15 uA as an average",
        },
        "given_or_established": {
            "N_COLUMNS": N_COLUMNS,
            "N_ROWS": N_ROWS,
            "pixel_size_um": [PIXEL_SIZE_UM, PIXEL_SIZE_UM],
            "refresh_hz": REFRESH_HZ,
            "blocks": ["TCON x1", "Data Driver x2 (384 ch each)", "Scan Driver x2 (512 ch each)"],
        },
        "derived_totals": {
            "pixel_count": pixels,
            "array_size_mm_conditional_on_A5": [N_COLUMNS * PIXEL_SIZE_UM / 1000.0,
                                                N_ROWS * PIXEL_SIZE_UM / 1000.0],
            "scan_lines_total": N_COLUMNS,
            "data_lines_total": N_ROWS,
            "pixels_per_selected_scan_line": scan_line_pixels,
            "I_SCAN_MAX_A": i_scan_max,
            "I_SCAN_MAX_mA": i_scan_max * 1e3,
            "I_DATA_CHANNEL_A": i_pix,
            "I_DATA_DRIVER_MAX_mA": i_data_driver_max * 1e3,
            "all_pixels_on_at_once_A": pixels * i_pix,
            "select_duty_one_column": duty,
            "ron_budget_note": "课程目标：高边压降 <= 0.10 V @ 11.52 mA -> R_ON <= 8.68 ohm "
                               "(derived requirement, to be met and verified by device sizing)",
            "R_ON_MAX_OHM": 0.10 / i_scan_max,
        },
        "per_refresh_rate": per_rate,
        "assumptions": [{"id": a, "item": b, "status": c, "note": d} for (a, b, c, d) in ASSUMPTIONS],
        "open_issues": [
            "课程要求扫描输出为『条件 VLED 5.0 V 域高边开关』，而老师固定的 smic18mmrf 只交付 1.8 V / 3.3 V 器件（n50/p50 模型定义数 = 0）。",
            "Absolute Maximum 额定值在课程文档中标 TBD，且本套模型文件未附带；需向 SMIC/老师索取。",
            "LED Vf 无题面数值，不做任何功耗/裕量结论。",
        ],
        "explicitly_not_computed": ["power (needs Vf)", "PWM minimum on-time", "device sizing",
                                    "D/A resolution", "area"],
    }


def fmt(v):
    if isinstance(v, float):
        if v == 0:
            return "0"
        if abs(v) >= 1000 or abs(v) < 1e-3:
            return "{0:.4e}".format(v)
        return "{0:.6g}".format(v)
    return str(v)


def to_md(d):
    L = []
    A = L.append
    dt = d["derived_totals"]
    t = d["topology_of_record"]
    A("# Micro LED array -- system-level baseline")
    A("")
    A("SOURCE = {0} (instructor assignment text) + user-confirmed clarification D1. "
      "The V1.2 pack `MicroLED_1024x768_Driver_IC_Specification_V1.2.docx` is a "
      "GPT6_LEGACY_PROPOSAL: it is a generated proposal kept for cross-reference, NOT a "
      "source of record and NOT the instructor's paper. Generated by "
      "`scripts/microled_arch_calc.py`. Values the assignment does not give stay "
      "{1}.".format("COURSE_REQUIREMENT", NOT_DEFINED))
    A("")
    A("> **Topology correction (2026-10-04)**: the first version of this file assumed "
      "data = columns and scan = rows. The course specification says the opposite: "
      "**scan drivers are the COLUMN drivers (512 x 2), data drivers are the ROW drivers "
      "(384 x 2)**. Consequently a selected scan electrode carries 768 pixels, so "
      "I_SCAN_MAX = 768 x 15 uA = **11.52 mA**, not 15.36 mA.")
    A("")
    A("## Topology of record")
    A("")
    A("| Item | Value | Evidence |")
    A("|---|---|---|")
    A("| Panel | {0} | course spec para 8 |".format(t["panel"]))
    A("| Scan selects | {0} | course spec para 32 + Figure 3 |".format(t["scan_selects"]))
    A("| Data drives | {0} | course spec para 32 |".format(t["data_drives"]))
    A("| Data driver ICs | {0} x {1} channels, {2}, {3} | course spec para 8/17 |".format(
        t["data_driver_ic"]["count"], t["data_driver_ic"]["channels_each"],
        t["data_driver_ic"]["placement"], t["data_driver_ic"]["even_odd"]))
    A("| Scan driver ICs | {0} x {1} channels, {2}, {3} | course spec para 8/17 |".format(
        t["scan_driver_ic"]["count"], t["scan_driver_ic"]["channels_each"],
        t["scan_driver_ic"]["placement"], t["scan_driver_ic"]["even_odd"]))
    A("")
    A("## Channel and current budget")
    A("")
    A("| Quantity | Value | Basis |")
    A("|---|---|---|")
    A("| Pixels | {0} | 1024 x 768 |".format(dt["pixel_count"]))
    A("| Scan lines (columns) total | {0} | course spec |".format(dt["scan_lines_total"]))
    A("| Data lines (rows) total | {0} | course spec |".format(dt["data_lines_total"]))
    A("| Scan channels per driver | {0} | 1024 / 2 (even/odd) |".format(
        d["topology_of_record"]["scan_driver_ic"]["channels_each"]))
    A("| Data channels per driver | {0} | 768 / 2 (even/odd) |".format(
        d["topology_of_record"]["data_driver_ic"]["channels_each"]))
    A("| **Pixels on one selected scan electrode** | **{0}** | one column = {1} rows |".format(
        dt["pixels_per_selected_scan_line"], N_ROWS))
    A("| **I_SCAN_MAX** | **{0} mA** | {1} x 15 uA |".format(
        fmt(dt["I_SCAN_MAX_mA"]), dt["pixels_per_selected_scan_line"]))
    A("| Data channel current | {0} uA | per-pixel constant current sink |".format(
        fmt(dt["I_DATA_CHANNEL_A"] * 1e6)))
    A("| I_DATA_DRIVER_MAX | {0} mA | 384 x 15 uA |".format(fmt(dt["I_DATA_DRIVER_MAX_mA"])))
    A("| If every pixel emitted at once | {0} A | 786432 x 15 uA (multiplexing is why this is not the real figure) |".format(
        fmt(dt["all_pixels_on_at_once_A"])))
    A("| Select duty (one of 1024 columns) | {0} | A4 |".format(fmt(dt["select_duty_one_column"])))
    A("| High-side R_ON budget | <= {0} ohm | course target 0.10 V drop at {1} mA |".format(
        fmt(dt["R_ON_MAX_OHM"]), fmt(dt["I_SCAN_MAX_mA"])))
    A("")
    A("## Per refresh rate")
    A("")
    for r in d["per_refresh_rate"]:
        A("### {0:g} Hz".format(r["refresh_hz"]))
        A("")
        A("| Quantity | Value | Note |")
        A("|---|---|---|")
        A("| Frame time | {0} ms | 1/f |".format(fmt(r["frame_time_s"] * 1e3)))
        A("| Column scan rate | {0} columns/s | 1024 x f |".format(fmt(r["column_scan_rate_hz"])))
        A("| **Column period** | **{0} us** | 1/(1024 f) |".format(fmt(r["column_period_us"])))
        A("| Data slot per row | {0} ns | column period / 768 |".format(
            fmt(r["row_data_slot_us"] * 1e3)))
        A("| Raw video throughput | {0} Mb/s | pixels x 8 bit x f |".format(
            fmt(r["raw_video_throughput_Mb_s"])))
        A("| Minimum input clock | {0} MHz | pixels x f (8-bit parallel) |".format(
            fmt(r["min_input_clock_MHz"])))
        A("| Instantaneous scan-line current | {0} mA | 768 pixels selected together |".format(
            fmt(r["instantaneous_scan_line_current_mA"])))
        A("| Derived panel average current | {0} mA | equals line current (one column always on) |".format(
            fmt(r["derived_panel_average_current_mA"])))
        A("| Derived pixel average current | {0} nA | 15 uA x 1/1024 (D1 direction) |".format(
            fmt(r["derived_pixel_average_current_nA"])))
        A("")
    A("## Assumptions / stated inputs")
    A("")
    A("| ID | Item | Status | Note |")
    A("|---|---|---|---|")
    for a in d["assumptions"]:
        A("| {0} | {1} | {2} | {3} |".format(a["id"], a["item"], a["status"], a["note"]))
    A("")
    A("## Open issues")
    A("")
    for x in d["open_issues"]:
        A("- {0}".format(x))
    A("")
    A("## Deliberately not computed")
    A("")
    for x in d["explicitly_not_computed"]:
        A("- {0}".format(x))
    A("")
    return "\n".join(L)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    root_default = os.path.abspath(os.path.join(here, os.pardir))
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=root_default)
    ap.add_argument("--json-only", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    d = compute()
    res_dir = os.path.join(args.outdir, "results")
    rep_dir = os.path.join(args.outdir, "reports")
    for p in (res_dir, rep_dir):
        if not os.path.isdir(p):
            os.makedirs(p)
    jpath = os.path.join(res_dir, "architecture_baseline.json")
    mpath = os.path.join(rep_dir, "architecture_baseline.md")

    with open(jpath, "w") as f:
        f.write(json.dumps(d, indent=2, sort_keys=True))
        f.write("\n")
    if not args.json_only:
        with open(mpath, "w") as f:
            f.write(to_md(d))

    with open(jpath) as f:
        back = json.load(f)
    dt = back["derived_totals"]
    r100 = [x for x in back["per_refresh_rate"] if x["refresh_hz"] == 100.0][0]
    checks = [
        ("pixels", dt["pixel_count"] == N_COLUMNS * N_ROWS),
        ("scan_lines_are_columns", dt["scan_lines_total"] == 1024),
        ("data_lines_are_rows", dt["data_lines_total"] == 768),
        ("pixels_per_scan_line", dt["pixels_per_selected_scan_line"] == 768),
        ("I_scan_max_11.52mA", abs(dt["I_SCAN_MAX_mA"] - 11.52) < 1e-9),
        ("not_the_old_15.36mA", abs(dt["I_SCAN_MAX_mA"] - 15.36) > 1.0),
        ("data_driver_5.76mA", abs(dt["I_DATA_DRIVER_MAX_mA"] - 5.76) < 1e-9),
        ("column_period_100Hz_9.7656us", abs(r100["column_period_us"] - 9.765625) < 1e-4),
        ("ron_budget_8.68ohm", abs(dt["R_ON_MAX_OHM"] - 0.10 / (768 * 15e-6)) < 1e-6),
        ("md", args.json_only or (os.path.isfile(mpath) and os.path.getsize(mpath) > 1000)),
    ]
    ok = all(v for (_, v) in checks)
    if not args.quiet:
        print("wrote {0} ({1} bytes)".format(jpath, os.path.getsize(jpath)))
        if not args.json_only:
            print("wrote {0} ({1} bytes)".format(mpath, os.path.getsize(mpath)))
        print("selfcheck " + " ".join("{0}={1}".format(k, v) for (k, v) in checks))
        print("I_SCAN_MAX={0:.4f}mA  I_DATA_DRIVER={1:.4f}mA  col_period@100Hz={2:.6f}us  Ron<= {3:.3f}ohm".format(
            dt["I_SCAN_MAX_mA"], dt["I_DATA_DRIVER_MAX_mA"], r100["column_period_us"], dt["R_ON_MAX_OHM"]))
    print("MICROLED_CALC: PASS" if ok else "MICROLED_CALC: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
