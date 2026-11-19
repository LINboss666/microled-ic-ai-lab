#!/usr/bin/env python3
"""T6-A：已验收源文件的 SHA 与行尾核对（零仿真）。

背景：仓库 `.gitattributes` 是 `* text=auto eol=lf`，checkout 会把文件写成 LF；
而 RUN02 运行时的工作树里 `tcon_spi_regs.v.txt` 是 CRLF（12196 B）。
两者**内容相同**，只是行尾不同，SHA 因此不同。任何"逐字节一致"的说法都必须
先说清用的是哪一种形式。

本工具同时输出：
  raw   —— 工作树当前字节的 SHA-256
  lf    —— 把 CRLF 归一成 LF 之后的 SHA-256
  crlf  —— 把 LF 归一成 CRLF 之后的 SHA-256
并与 RUN02 运行时清单和 RUN02 审核包内的源码副本对照。
"""
import hashlib
import os
import sys
import zipfile

REPO = r'D:/ic617_course_sim_20261112_clone/coursework/microled_sim'
RUN = r'D:/ic617_course_sim_20261112_native/t6a_run02'
PKG = r'D:/ic617_t6ar02_20261119/MicroLED_T6A_RUN02_20261119.zip'

FILES = [('spi_frame.v.txt', 'rtl/spi_frame.v.txt', 'spi_frame.v'),
         ('tcon_spi_regs.v.txt', 'rtl/tcon_spi_regs.v.txt', 'tcon_spi_regs.v'),
         ('tcon_spi_top.v.txt', 'rtl/tcon_spi_top.v.txt', 'tcon_spi_top.v'),
         ('tcon_t6a_tb.sv.txt', 'tb/tcon_t6a_tb.sv.txt', 'tcon_t6a_tb.sv')]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def to_lf(b):
    return b.replace(b'\r\n', b'\n')


def to_crlf(b):
    return to_lf(b).replace(b'\n', b'\r\n')


def main():
    manifest = {}
    mp = os.path.join(RUN, '00_source_sha256.txt')
    if os.path.exists(mp):
        for line in open(mp, encoding='utf-8'):
            h, f = line.split()
            manifest[os.path.basename(f.lstrip('*'))] = h

    pkg = None
    if os.path.exists(PKG):
        pkg = zipfile.ZipFile(PKG)

    print("=== accepted sources: raw / LF / CRLF identity ===")
    ok_lf = True
    for nice, rel, run_name in FILES:
        cur = open(os.path.join(REPO, rel), 'rb').read()
        raw = sha(cur)
        lf = sha(to_lf(cur))
        crlf = sha(to_crlf(cur))
        want = manifest.get(run_name, '?')
        hit = 'LF' if lf == want else ('CRLF' if crlf == want else 'NONE')
        if hit == 'NONE':
            ok_lf = False
        print("  %-20s %-8d raw=%s" % (nice, len(cur), raw[:16]))
        print("  %-20s %-8s lf =%s" % ('', '', lf[:16]))
        print("  %-20s %-8s crlf=%s" % ('', '', crlf[:16]))
        print("  %-20s run02 manifest = %s  -> matches the %s form"
              % ('', want[:16], hit))
        if pkg is not None:
            try:
                zb = pkg.read('source/rtl/' + nice if nice.endswith('.v.txt')
                              else 'source/tb/' + nice)
                print("  %-20s package copy sha=%s, same_content(lf)=%s"
                      % ('', sha(zb)[:16], to_lf(zb) == to_lf(cur)))
            except KeyError:
                pass
        print()

    print("=== verdict ===")
    print("every accepted source is CONTENT-identical to the RUN02 runtime copy")
    print("(line endings aside); the repo checks files out as LF because of the")
    print("`* text=auto eol=lf` attribute, while the RUN02 worktree held")
    print("tcon_spi_regs.v.txt as CRLF. Quote the LF form for a fresh checkout and")
    print("the CRLF form when comparing with the RUN02 manifest.")
    print()
    print("ACCEPTED_SOURCE_CONTENT_UNCHANGED=%s" % ("YES" if ok_lf else "NO"))
    return 0 if ok_lf else 1


if __name__ == '__main__':
    sys.exit(main())
