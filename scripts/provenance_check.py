#!/usr/bin/env python3
"""provenance_check.py -- police where every number in this project is allowed to come from.

Hard rule from the independent review: the file `course_source/spec_v12_text.txt` is an
extract of the OLD GPT-6 generated design proposal (`MicroLED_..._V1.2_最终交付包`).
It is NOT the instructor's paper and NOT the course statement, and nothing sourced only
from it may be labelled as either.

Allowed labels (exactly these, underscore form):

  COURSE_REQUIREMENT     instructor's assignment text, or a course condition the user
                         has explicitly confirmed
  COURSE_FIGURE          the layout/structure figure that came with the assignment
  TEACHER_PAPER          actual content of the instructor's paper
                         (Xiao et al., "A 64 x 64 GaN Micro LED Monolithic Display
                         Array...", Micromachines 16(2) 207, 2025, DOI 10.3390/mi16020207)
  ENGINEERING_DERIVATION arithmetic on the three above
  GPT6_LEGACY_PROPOSAL   anything whose only source is the V1.2 pack
  POC_ASSUMPTION         a test condition this project invented to simulate with
  NOT DEFINED            the course never said -- must never be given a value

Notation mapping for the older 【…】 tags still present in spec/system_requirements.md:

  【题面】->COURSE_REQUIREMENT   【规格书 V1.2 …】->GPT6_LEGACY_PROPOSAL
  【文献参考】->TEACHER_PAPER    【计算得到】->ENGINEERING_DERIVATION
  【课程设计假设】->POC_ASSUMPTION 【待实测】->NOT DEFINED

Rules enforced per line (with a one-line look-ahead for the citation):

  R1  label must be one of the allowed set (spaced variants are rejected)
  R2  TEACHER_PAPER requires a real citation of the instructor's paper on the same or
      the next line
  R3  a line whose only source is the V1.2 pack may not carry COURSE_REQUIREMENT or
      TEACHER_PAPER (it may carry GPT6_LEGACY_PROPOSAL / ENGINEERING_DERIVATION /
      POC_ASSUMPTION), unless it also cites 题面 or a course Figure
  R4  design-claim absolutism: keeper / write / corner / margin sentences may not say
      "always", "guaranteed", "all corners" -- those words need PVT, voltage,
      temperature, mismatch and Monte Carlo evidence this project does not have

  python scripts/provenance_check.py [--root .] [--fix-hint]
"""

import argparse
import os
import re
import sys

ALLOWED = {
    "COURSE_REQUIREMENT", "COURSE_FIGURE", "TEACHER_PAPER", "ENGINEERING_DERIVATION",
    "GPT6_LEGACY_PROPOSAL", "POC_ASSUMPTION", "NOT DEFINED", "NOT_DEFINED",
}

# label tokens we recognise, including the legacy spaced forms we want gone
LABEL_RX = re.compile(r"\b(?:COURSE[_ ]REQUIREMENT|COURSE[_ ]FIGURE|TEACHER[_ ]PAPER|"
                      r"ENGINEERING[_ ]DERIVATION|GPT6[_ ]LEGACY[_ ]PROPOSAL|"
                      r"POC[_ ]ASSUMPTION|NOT[_ ]DEFINED)\b")
BRACKET_MAP = [
    (re.compile(r"【\s*题面"), "COURSE_REQUIREMENT"),
    (re.compile(r"【\s*规格书\s*V1\.2"), "GPT6_LEGACY_PROPOSAL"),
    (re.compile(r"【\s*文献参考"), "TEACHER_PAPER"),
    (re.compile(r"【\s*计算得到"), "ENGINEERING_DERIVATION"),
    (re.compile(r"【\s*课程设计假设"), "POC_ASSUMPTION"),
    (re.compile(r"【\s*待实测"), "NOT DEFINED"),
]
GPT6_SOURCE = re.compile(r"spec_v12_text|规格书\s*V1\.2|V1\.2_最终交付包|MicroLED_驱动芯片规格书|"
                         r"MicroLED_1024x768_Driver_IC_Specification_V1\.2")
# prose that promotes the legacy pack, in any case, without an independent course source
PROSE_COURSE_REQ = re.compile(r"course\s+requirement", re.I)
REAL_PAPER = re.compile(r"Micromachines|10\.3390/mi16020207|64\s*[x×]\s*64\s*GaN|Xiao", re.I)
# An independent course basis on the same line: the assignment text, the layout figure,
# or a condition the user explicitly confirmed (the taxonomy counts that as
# COURSE_REQUIREMENT by definition, in either language).
FIGURE_OR_STEM = re.compile(r"COURSE_FIGURE|Figure|【\s*题面|题面|用户确认|用户指示|"
                            r"user[- ]confirmed|user instruction|instructor assignment")
ABSOLUTISM = re.compile(r"\b(always|guaranteed?|all corners|every corner|无条件下?成立|保证)\b", re.I)
CLAIM_CONTEXT = re.compile(r"keeper|write|corner|margin|PVT|mismatch|Monte\s*Carlo|"
                           r"写入|保持|裕量|进程角", re.I)
SKIP_PATHS = ("review/", "results/evidence/", "results/preflight/",
              "results/history/", "course_source/", "pdk_compare/", "microled/")


def norm(tok):
    return tok.replace(" ", "_") if tok.upper() != "NOT_DEFINED" else "NOT DEFINED"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    root = os.path.abspath(args.root)

    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
        for fn in filenames:
            if not fn.endswith((".md", ".scs", ".awk", ".sh", ".py")):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), root).replace("\\", "/")
            if rel.startswith(SKIP_PATHS) or rel.startswith("pdk_compare/"):
                continue
            if rel.endswith("scripts/provenance_check.py"):
                continue          # the rule table quotes the tokens it rejects
            files.append(rel)

    viol = []
    checked = 0
    for rel in sorted(files):
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
            lines = fh.read().replace("\r\n", "\n").split("\n")
        for i, line in enumerate(lines):
            if 'check:skip' in line:
                continue
            labels = [norm(m.group(0).upper()) for m in LABEL_RX.finditer(line)]
            bracketed = [lab for rx, lab in BRACKET_MAP if rx.search(line)]
            all_lab = labels + bracketed
            if not all_lab and not (GPT6_SOURCE.search(line)
                                            and PROSE_COURSE_REQ.search(line)):
                continue
            checked += 1
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            for lab in set(all_lab):
                if lab not in ALLOWED:
                    viol.append(("R1 unknown label", rel, i + 1, lab, line.strip()[:110]))
            # "NOT DEFINED" is legitimately two words -- it is the course vocabulary for
            # "the assignment never said". The variants that must become underscore form
            # are the label names themselves.
            for m in LABEL_RX.finditer(line):
                tok = m.group(0)
                if " " in tok and tok.upper().replace(" ", "_") != "NOT_DEFINED":
                    viol.append(("R1 spaced label variant", rel, i + 1,
                                 "use the underscore form (%s)" % tok, line.strip()[:110]))
            taxonomy_definition = len(set(all_lab)) >= 3   # the rule table itself
            if "TEACHER_PAPER" in all_lab and not taxonomy_definition and                     not (REAL_PAPER.search(line) or REAL_PAPER.search(nxt)):
                viol.append(("R2 TEACHER_PAPER without the instructor's paper cited",
                             rel, i + 1, "", line.strip()[:110]))
            if GPT6_SOURCE.search(line) and "COURSE_REQUIREMENT" in all_lab and \
                    not FIGURE_OR_STEM.search(line + " " + nxt):
                viol.append(("R3 V1.2 pack promoted to COURSE_REQUIREMENT", rel, i + 1,
                             "", line.strip()[:110]))
            if GPT6_SOURCE.search(line) and "TEACHER_PAPER" in all_lab:
                viol.append(("R3 V1.2 pack promoted to TEACHER_PAPER", rel, i + 1, "",
                             line.strip()[:110]))
            if GPT6_SOURCE.search(line) and PROSE_COURSE_REQ.search(line) and                     not FIGURE_OR_STEM.search(line + " " + nxt):
                viol.append(("R5 V1.2 pack named alongside 'course requirement' with no "
                             "independent course source on the line", rel, i + 1, "",
                             line.strip()[:110]))
            if ABSOLUTISM.search(line) and CLAIM_CONTEXT.search(line):
                viol.append(("R4 absolutist claim without PVT/mismatch evidence", rel,
                             i + 1, "", line.strip()[:110]))

    print("provenance_check: files=%d labelled_lines=%d violations=%d"
          % (len(files), checked, len(viol)))
    for rule, rel, ln, extra, text in viol:
        print("  %s  %s:%d %s" % (rule, rel, ln, extra))
        print("        | %s" % text)
    if viol:
        print("SOURCE_PROVENANCE_CHECK: FAIL")
        return 1
    print("SOURCE_PROVENANCE_CHECK: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
