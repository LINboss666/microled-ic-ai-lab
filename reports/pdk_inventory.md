# PDK / library inventory (Phase 1) — read-only

Method: bounded `find`/`grep`/`sed` over candidate roots (`/root`, `/root/tech`, `/home`, `/opt`, `/data`, `/usr/local`), plus the vendor cards' own headers and this machine's `spectre -h` output. Nothing was assumed and nothing was written: no `cds.lib`, techfile, model file or library was modified, and no Cadence cell was created. Raw machine-readable dump: `logs/pdk_inventory_raw.txt` (364 lines) and in-guest `/root/microled_ai_project/logs/pdk_inventory_raw.txt`.

## 0. Headline answer

**Five process kits are installed, all under `/root/tech/`, all as OpenAccess technology+device libraries:**

| # | OA library | Kit | Node | Gate oxides / nominal supplies | Device model | Status this round |
|---|---|---|---|---|---|---|
| 1 | `tsmc18` | TSMC 0.18 µm CMOS **Mixed-Signal RF General Purpose II**, 1P6M+AL salicide | 0.18 µm | **1.8 V core + 3.3 V IO** | BSIM4 v4.5 | **Simulated, 4/4 checks PASS** |
| 2 | `smic18ee` | SMIC 0.18 µm **EEPROM**, 2P6M | 0.18 µm | **1.8 / 3.3 / 5.0 / 15.5 V** | BSIM3v3 | **Simulated, 4/4 checks PASS** |
| 3 | `tsmc18rf` | TSMC 0.18 µm **Mixed-Signal** salicide, 1P6M+ | 0.18 µm | **1.8 V + 3.3 V** | BSIM3 v3.24 | Inventoried, not simulated |
| 4 | `smic18mmrf` | SMIC 0.18 µm **Mixed-Signal RF**, 1P6M | 0.18 µm | **1.8 V + 3.3 V** | see §4 | Inventoried, not simulated |
| 5 | `tsmcN65` | TSMC **CMU65LP** 65 nm Mixed-Signal RF salicide, Low-K IMD | 65 nm | **1.2 V core, 2.5 V, over-drive 3.3 V** | BSIM4 v4.5 | Inventoried, not simulated; **model delivery is incomplete** (see §5) |

Also present, not a PDK: TSMC 0.18 GP **standard-cell library in Synopsys `.db` form** (`tsmc18-OA/tsmc18/digital/`, 6 files `tcb018gbwp7t{bc,lt,ml,tc,wc,wcl}.db`) — Liberty/DC data, **not** OA cells, so it cannot be dropped into Virtuoso as a device library without conversion.

**No pre-existing design project was found.** `/root/Desktop/libManager.log` is 0 bytes, `/root/Templates/` is empty, and a search for OA `schematic/` directories outside `/root/tech/` returned nothing. So there is no teacher or student library at risk in this image, and equally no example design to learn the intended flow from.

Other EDA installs (context, not PDKs): `/opt/IC5141` (Virtuoso 5), `/opt/MMSIM121`, `/opt/MMSIM151` (Spectre 15.1.0.284.isr1), `/opt/calibre2015/aoi_cal_2015.2_36.27`, `/opt/synopsys/{Hspice-2015.06-3, K-2015.06, v11.10, hsim2015}`.

---

## 1. `tsmc18` — TSMC 0.18 µm MS/RF GP II (VERIFIED)

| Field | Value |
|---|---|
| Library name | `tsmc18` (its `cds.lib` defines `basic`, `analogLib` from `$CDSHOME`, `tsmc18 ./tsmc18`) |
| Path | `/root/tech/tsmc18-OA/tsmc18` (256 MB) |
| OA cells | 374 device/tech cells + `tech.db` |
| Node | 0.18 µm, salicide, **1P6M+ Al** top metal |
| Foundry | **TSMC** — stated verbatim in `ReleaseNote.txt`: "TSMC 0.18 UM CMOS MIXED SIGNAL RF GENERAL PURPOSE II 1P6M+AL SALICIDE 1.8/3.3V PDK", version V1.0a |
| MOS models | `nch`, `pch` (1.8 V core); `nch3`, `pch3` (3.3 V); `nch_rf`, `pch_rf`, `nch_rf33`, `pch_rf33` (RF flavours); `nanch`, `nanch3`, `mench`, `mench3` — the `3` suffix = 3.3 V is consistent with the release note, the `nan/men` prefix reading is **UNKNOWN** (not confirmed from docs) |
| Nominal VDD | 1.8 V core / 3.3 V IO (release note; 1.8 V rail confirmed usable by simulation) |
| Spectre model | **Yes.** Master card `models/spectre/cr018gpii_v1d0.scs`, 59,611 lines, 214 sections, 74 distinct model names: 30 BSIM4 + 66 diode + 15 BJT declarations |
| R / C / D | **Yes, dedicated files**: `cor_res.scs`, `cor_disres.scs`, `cor_rfres_{sa,rpo,hri}.scs` (resistors); `cor_mim.scs`, `cor_fmom.scs`, `cor_rfmom.scs`, `cor_rtmom.scs`, `cor_rfsbd.scs` (caps/substrate); `cor_dio*.scs`, `cor_bip*.scs` (diodes, BJTs); `cor_bbmvar.scs`, `cor_rfmvar*.scs`, `cor_rfjvar.scs` (varactors); `cor_rfesd.scs`; inductors `cor_rfind.scs`. Model-file counts by type inside the card: diode 66, bsim4 30, bjt 15 |
| DRC / LVS | **Both present.** `Assura/` + `assura_tech.lib`, `Calibre/` with `drc/` and `lvs/`, and `PDK_doc/{Calibre_DOC, TSMC_DOC_WM/LVS/{Assura_Doc,Calibre_Doc}}`. Device cells carry per-cell `auLvs` view dirs (Assura LVS extraction data). **Not executed this round.** |
| Std cells | Liberty/DC `.db` set in `digital/` (see headline) |
| Gotchas found | 1) The vendor master `models/spectre/spectre.scs` hardcodes `/opt/cadence/process/.tsmc18/...`, which **does not exist** in this image -> unusable as-is; include the card directly instead. 2) The corner section `tt` references Monte-Carlo noise knobs (`par1fn_mc`) defined in `section stat_noise`; including only `tt` fails with `SFE-1996`. Both are worked around in the netlist, not by editing the PDK. |
| Confidentiality | Card carries TSMC "AS IS" disclaimer text; no parameter values copied into this report |

## 2. `smic18ee` — SMIC 0.18 µm EEPROM 2P6M (VERIFIED, widest voltage range)

| Field | Value |
|---|---|
| Library name | `smic18ee` (from `cds.lib`) |
| Path | `/root/tech/smic18ee_OA/smic18ee_2P6M_20100810` (102 MB) |
| OA cells | 125 + `tech.db` |
| Node | 0.18 µm, **2 poly / 6 metal**, salicide; process flavour = EEPROM (embedded-charge) |
| Foundry | **SMIC** — stated in `models/spectre/e2r018_v1p8_readme_spe.txt`: "SMIC SPICE model for 0.18um EEPROM 1.8V/3.3V/5v/15.5v 2P6M process / For Spectre only" |
| MOS models | `n18e2r`, `p18e2r` (1.8 V); `n33e2r`, `p33e2r` (3.3 V); `n50e2r`, `p50e2r` (5 V); `n155e2r`, `p155e2r` (15.5 V); native/depletion `nz18e2r`, `nz50e2r`, `nz155e2r`; diodes `n/p/wd io*_e2r`; all **BSIM3v3** |
| Nominal VDD | 1.8 V core, 3.3 V, 5.0 V, **15.5 V** devices (explicit in the readme and in the `.scs` header comment) |
| Spectre model | **Yes.** `models/spectre/e2r018_v1p8_spe.scs` (corner parameter sections) + `e2r018_v1p8_spe.mdl` (model statements, 998-line .scs `section tt` includes the .mdl), plus `..._res_spe.{ckt,mdl}`, `..._mim_spe.mdl`, `..._bjt_spe.mdl`, `..._pip_spe.mdl`, `res.va` (Verilog-A resistor) |
| R / C / D | **Yes**: resistor (dedicated `.ckt`/`.mdl` + Verilog-A `res.va`), PIP capacitor (`_pip_spe.mdl`), MIM capacitor (`_mim_spe.mdl`), diodes, PNP BJT |
| Corners | `tt`, `ff`, `ss`, `snfp`, `fnsp` (five corners per the file header); BJT sections separate (`bjt_tt`) |
| Geometry validity | **Hard limits enforced by the card** (found the hard way): `n50e2r` requires `lmin=1.4e-6 lmax=1e-5 wmin=6e-7 wmax=1e-4`. Asking for L=0.5 µm produced `WARNING (CMI-2441) ... does not fit the given lmax-lmin, wmax-wmin ... range` followed by `ERROR (CMI-2434): 'Vsat' = -11.5118e+03 must be positive` -> the thick-oxide devices are long-channel only, which matters for a pixel driver using small L |
| DRC / LVS | **Both present**: `calibre/drc`, `calibre/lvs`, `calibre/xrc/Calibre` (XRC), `assura_smic18ee_tech/`, `icc.rules` (Synopsys). **Not executed this round.** |
| Gotchas found | 1) Its `cds.lib` defines `cdsDefTechLib /opt/eda/cadence/IC618/tools/dfII/etc/cdsDefTechLib` — **IC618 is not installed here**, so opening this library in the OA explorer needs that line fixed in a *copy* of cds.lib (we did not modify it). 2) Model files are dated 2010 (v1.8 of the e2r018 card); PDK_ReleaseNote PDF `PDK_ReleaseNote_RevisionHistory_018EE_183350155.pdf` was not opened. |
| Confidentiality | Files state "No part of this file can be released without the consent of SMIC" -> local use only; no model parameters copied out of the guest, only device names, corner names and geometry limits |

## 3. `tsmc18rf` — TSMC 0.18 µm Mixed-Signal RF (inventoried only)

| Field | Value |
|---|---|
| Library name | `tsmc18rf` |
| Path | `/root/tech/tsmc180rf_OA/tsmc180rf_OA` (75 MB), 139 OA cells + `tech.db` |
| Node | 0.18 µm Mixed-Signal salicide, **1P6M+** |
| Foundry | TSMC (`REVISION` file: "Initial FE PDK Release for QA ... Techfile: Virtuoso4.4_0.18um_Ver2.3b.tf", `PDK_doc/tsmc18rf_pdk_release_notes.pdf`) |
| MOS models | `nch_rf`, `pch_rf` etc., **BSIM3 v3.24** (card `models/spectre/rf018.scs`, 16,825 lines, 52 distinct model names: 40 diode + 25 bsim3v3 + 9 bjt + 3 capacitor + 2 resistor) |
| Nominal VDD | **1.8 V + 3.3 V** (card header "PROCESS : 0.18um Mixed-Signal SALICIDE(1P6M+, 1.8V/3.3V)"). Device dirs also show `pmosmvt2v` / `diodenw3v` -> a 2 V mid-oxide family likely exists; **exact family list UNKNOWN** (not verified) |
| Spectre model | Yes, 25 `.scs` files incl. `cor_std_mos.scs`, RF passives (`cor_rfmim`, `cor_rfind`, `cor_rfres_*`, `cor_rfmvar`, `cor_rfjvar`, `cor_rfesd`) |
| R / C / D | Yes (resistor, MIM, inductor, varactor, diode, BJT) |
| DRC / LVS | `Assura/` and `Calibre/` dirs + per-cell `auLvs`; **not executed** |
| Notes | Card targets "SPECTRE VERSION : 50 MSR" (2002-2005 era) -> compatibility with Spectre 15.1 is **unverified**; the tech line says it was built for Virtuoso 4.4, so the OA library here is an conversion of that era |

## 4. `smic18mmrf` — SMIC 0.18 µm Mixed-Signal RF (inventoried only)

| Field | Value |
|---|---|
| Library name | `smic18mmrf` (its `cds.lib` sits one level deeper: `SMIC_018_MMRF/cds.lib`, **not** at the kit top -> a naive `cds.lib` scan misses it) |
| Path | `/root/tech/smic_018mmrf-OA/smic_018mmrf-OA/SMIC_018_MMRF` (41 MB), 133 OA cells + `tech.db` |
| Node | 0.18 µm Mixed-Signal RF, **1P6M** |
| Foundry | SMIC (`models/spectre/ms018_v1p7_readme_spe.txt`: "SMIC SPICE model for 0.18um Mixed Signal 1.8V/3.3V 1P6M process / For Spectre only") |
| MOS models | `n18`, `p18`, `n33`, `p33`, low-Vt `nmvt18`, `nmvt33`, `pmvt18`, native `nnt18`, `nnt33`, `nwdio`, `nndio18/33`, `ndio18/33`, `pdio18/33` (from `ms018_v1p7_spe.mdl`) |
| Nominal VDD | 1.8 V core + 3.3 V IO |
| Spectre model | Yes, two model sets: `ms018_v1p7_spe.mdl` (+ `..._bjt_spe.mdl`, `..._mim_spe.mdl`) and the RF set `ms018_rf_v1p5_spe.lib` with `..._mos_spe.ckt`, `..._res_spe.ckt`, `..._mim_spe.ckt`, `..._var_spe.ckt`, `..._diff_ind_spe.ckt`, `..._spri_ind_spe.ckt` -> inductors included |
| R / C / D | Yes (resistor, MIM, varactor, diode, BJT, + spiral/diff inductors) |
| DRC / LVS | `DRC/Calibre/SmicDR3T6P_cal018_mixlog_sali_p1mtt4_1833.drc` and `LVS/Calibre/SmicSPM8RR7R_cal018_mixRF_sali_p1mtx_1833.lvs`; **not executed** |
| Notes | 22 `.mdl` files, **0 `.scs`** at kit top -> the include entry point is the `.lib`; not exercised this round |
| **UPDATE (same day)** | 用户指定该库为课程正用库。实测发现**虚拟机这份是 2007-09-20 的老交付，模型为 BSIM3v3**（`ms018_v1p7_spe.lib` 27 KB），与老师给的 `pdk资料.zip`（2025-01-18，`ms018_enhanced_v1p2_rev0` = **BSIM4**，`.lib` 353 KB + RF `mse018_v1p11`，含官方 Calibre DRC/LVS/XRC deck）**零文件名交集**。老师那份已按位校验装入 `/root/microled_ai_project/pdk/smic18mmrf_teacher`，并**用它完成 8 项 Spectre 判据（`MODEL_PROBE_SMIC18MMRF: PASS`）**。详见 `reports/pdk_zip_vs_guest.md`。后续设计以老师副本为准，本节描述的 guest 旧副本只作对照 |

## 5. `tsmcN65` — TSMC CMU65LP 65 nm (largest kit, but model delivery incomplete)

| Field | Value |
|---|---|
| Library name | `tsmcN65` |
| Path | `/root/tech/PDK_tsmc-65nm/PDK_tsmc-65nm` (**2.1 GB**), 1167 OA cells + `tech.db`, plus `CCI`, `skill`, `Techfile`, `Assura`, `Calibre` |
| Node | **65 nm** Mixed-Signal RF salicide, Low-K IMD, model name **CRN65LP** |
| Foundry | TSMC (card header "TSMC SPICE MODEL --- Security B", DOC. NO. `T-N65-CM-SP-007`) |
| MOS models | BSIM4 v4.5. From the 2.5 V card: `nch`/`pch` (1.2 V core) + `nch_hvt/lvt/mlvt/na` and `nch_rf*`, and IO `nch_18`, `nch_25`, `nch_33`, `nch_25od33`, `nch_25ud18` (+ pm counterparts) — 174 distinct model names, 99 BSIM4 + 191 diode + 24 BJT + 4 resistor declarations |
| Nominal VDD | **1.2 V core / 2.5 V IO / 3.3 V over-drive** (explicit card PROCESS line), with 1.8 V-class devices present in the 2.5 V card family |
| Spectre model | **Partial.** Only two model deliveries exist: `models/online/2.5V/spectre/` (v1.7) and `models/online/3.3V/spectre/` (v1.5), each with `toplevel.scs` + card + `_usage.scs`. The kit's own `models/spectre/`, `models/hspice/`, `models/eldo/` are **empty (0 files)**. There is **no 1.2 V core-only delivery folder**, so core devices must come from the 2.5 V card. **No dedicated passive `.ckt`/`.va` files anywhere in the kit (count = 0)** -> resistor/cap/inductor models are only whatever is inside those two cards (4 `model ... resistor` declarations); MIM/MOM/inductor availability = **UNKNOWN / likely missing** |
| Metal stacks | Multiple options under `Techfile/online/`: `1p5m_3X1Z0U`, `1p6m_3X1Z1U`, `1p6m_3X2Z0U`, `1p6m_4X0Z1U`, `1p6m_4X1Z0U`, `1p7m_4X1Z1U`, `1p7m_4X2Z0U`, `1p7m_5X0Z1U`, `1p7m_5X1Z0U`, `1p8m_5X1Z1U`, `1p8m_6X0Z1U`, `1p9m_6X1Z1U` |
| DRC / LVS | `Calibre/drc`, `Calibre/lvs`, `Calibre/online/drc_online/1p8m_6X0Z1U/calibre.drc`, `Assura/online/assura_tech.lib`, `assura_tech.lib`; **not executed** |
| Licensing note | Cards are marked "Security B"; `pdkInstall.cfg` shows the kit was installed from a tarball with metal-layer pruning (`rm -rf tsmcN65/M1*...M5*`). Because the model set is incomplete and TSMC 65 nm licensing is the strictest of the five, **do not plan any 65 nm work without checking the course licence** |

## 6. Things explicitly NOT determined (marked rather than guessed)

- `nan*/men*` device family meaning in the TSMC 0.18 card: **UNKNOWN** (no doc opened)
- Whether `tsmc18rf` ships a 2 V mid-oxide family: **likely from cell names, UNKNOWN**
- 65 nm MIM/MOM/inductor model availability: **UNKNOWN (likely not delivered)**
- DRC/LVS rule *versions* and their run-readiness (need Calibre/Assura licences + a real layout): **UNKNOWN, not attempted**
- Which kit the course/teacher intends: **UNKNOWN — nothing in the image says so** (no libManager history, no project, no README at `/root` level pointing to one)
- SMIC 18EE `2P6M` vs SMIC MMRF `1P6M` metal option actually enabled per cell view: **UNKNOWN** (not extracted)
- `MOSFET` threshold voltage values / exact `toxeq` per family: deliberately **not extracted** (model confidentiality)

## 7. Safety statement for this phase

Read-only. No file under `/root/tech`, `/opt`, or any library was created, modified, or deleted. The only writes in the guest were under `/root/microled_ai_project/` (the new project area) and `/root/microled_ai_project/logs/pdk_inventory_raw.txt`. No Cadence cell, view, `cds.lib`, techfile or model file was touched; no simulation used any PDK output path.
