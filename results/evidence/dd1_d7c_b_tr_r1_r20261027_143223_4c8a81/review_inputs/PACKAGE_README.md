# DATA-7C-B-TR reviewer package (2026-10-27)

Read REVIEW_DATA7C_B_TR_REWORK_20261027.md, then give TASK_DATA7C_B_TR_R1.md and this package to Qoder for one offline repair round.

Reviewed fixed Git content f49ba9d78190f8c3da2adca9dbd4fb3e48d26841 and tip 398c9e852c16db85cbfa4539e859534e117ff0d2. No simulator, RTL simulator, guest or OA was used by the reviewer. The executor's own ZIP was not available and is not this archive.

The reviewer probe is executable with the reviewed Git checkout: python probe_tr_review_gaps.py /path/to/checkout --out /new/scratch. On original bytes rc=0 means all nine defects reproduced, with clean positive controls. All counterexamples are synthetic or modified copies; they are not actual measured circuits. The generated recompute logs show how the original 198 checks also accept three separate semantic counterfeits. The original table arithmetic was independently rechecked in 209 checks; that does not reintegrate unavailable raw waveforms.

The offline-only repair task grants no Spectre, vvp, OA or guest access. It requires reuse/export of locally retained raw/VCD and preservation of old evidence. If new strict inputs require a fixture adapter, original reviewer probe bytes remain unchanged and clean complete inputs must pass before each semantic mutation is assessed.

MANIFEST.csv covers all other members. Archive digest is kept outside the archive. Large generated synthetic VCDs and temporary full evidence copies are reproducible by the probe and not included.
