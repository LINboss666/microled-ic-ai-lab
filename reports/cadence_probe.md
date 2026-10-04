# IC617 / Virtuoso environment probe (Phase 3) + SKILL smoke test (Phase 4)

Probed read-only over SSH as root on 2026-10-04. Licence material is deliberately not copied into this file.

## Guest identity

| Item | Value |
|---|---|
| Release | Red Hat Enterprise Linux Server 6.5 (Santiago) |
| Kernel | 2.6.32-431.el6.x86_64 |
| hostname command | returns **empty** (no runtime hostname set) |
| Configured hostname | `HOSTNAME=work-eda` in `/etc/sysconfig/network`; `127.0.0.1 work-eda` in `/etc/hosts` |
| User | root (uid 0) |
| Shell | bash 4.1.2, login shell via `bash -l` |
| X | `/usr/bin/Xorg :0` running under gdm, `/tmp/.X11-unix/X0` present, `DISPLAY` unset in SSH sessions |

## Changes actually made inside the guest (complete list)

1. `dhclient -1 eth0` -> lease `192.168.3.128/24`, default via `192.168.3.2`. Temporary: `ifcfg-eth0` still has `ONBOOT=no`, so a reboot returns to the no-IP state. No file was edited.
2. `/root/.ssh/authorized_keys` written with the Windows bridge public key (mode 600, `ssh_home_t` unchanged, `restorecon` not needed).
3. Sandbox created: `/root/qoder_ic617_sandbox/{bin,logs,work,home}`.

Nothing else was touched. sshd was already running; the firewall already had `-A INPUT -p tcp --dport 22 -j ACCEPT`, so **no service or firewall change was needed**.

## Cadence install map

| Item | Value |
|---|---|
| IC version | `@(#)$CDS: virtuoso version 6.1.7-64b 11/09/2015 12:45 (sjfnl165) $` |
| `CDS` | `/opt/IC617/` |
| GUI/batch binary | `/opt/IC617/tools/dfII/bin/virtuoso` |
| SKILL batch binary | `/opt/IC617/tools/dfII/bin/dbAccess` -> real image `/opt/IC617/tools/dfII/bin/64bit/dbAccess` (selected by `CDS_AUTO_64BIT=ALL`) |
| `OA_HOME` | `/opt/IC617/oa_v22.50.036/` |
| MMSIM | `MMSIM_ROOT=/opt/MMSIM151`, spectre at `/opt/MMSIM151/tools/spectre/bin/spectre` |
| Other EDA present | `/opt/IC5141`, `/opt/MMSIM121`, `/opt/calibre2015/aoi_cal_2015.2_36.27`, `/opt/synopsys/{Hspice-2015.06-3, K-2015.06, v11.10, hsim2015, cscope64_2011...}` |

## How the Cadence environment is loaded (the important part)

No login profile sets any Cadence variable. `which virtuoso` only resolves because `/etc/env` is in `PATH`, and `/etc/env/virtuoso` is **a 34-line shell wrapper, not a symlink**:

- it sources the HSPICE `kshrc.meta`
- it exports `MMSIM_ROOT`, `CDS_LIC_FILE`, `LM_LICENSE_FILE`, `CDS_AUTO_64BIT`, `OA_HOME`, `CDS`, `CDS_Netlisting_Mode`, two `PATH` prepends, `LD_LIBRARY_PATH`
- it prints `spectre -V` / `virtuoso -V`
- it finishes with `/opt/IC617/tools/dfII/bin/virtuoso&` -- a background GUI launch with no `wait`

Consequences for automation: running the wrapper headless would open a GUI window on `:0` and return immediately without ever giving a usable handle, and `spectre`/`dbAccess` are **not** on the login `PATH` because the wrapper only exports them inside its own process. So `skill/cad_env.sh` harvests just the `export` lines from the wrapper at run time (never copies their values into the repo, never edits the wrapper) and `dbAccess`/`virtuoso` are then resolvable.

Defect found in the shipped wrapper: its `LD_LIBRARY_PATH` line references `$D_LIBRARY_PATH` (missing the leading `L`), so `LD_LIBRARY_PATH` never inherits the previous value, and under `set -u` sourcing that line aborts. `cad_env.sh` pre-seeds `D_LIBRARY_PATH` from `LD_LIBRARY_PATH` as a compatible workaround. `/etc/env/virtuoso` was **not** modified.

## Licensing

- `CDS_LIC_FILE` / `LM_LICENSE_FILE` are defined inside the wrapper (values intentionally not reproduced here).
- `ss -lntp` shows **nothing listening on the TCP port named in `CDS_LIC_FILE`**; the only FlexLM daemons running are Synopsys (`v11.10`) and Calibre (`mgcld -T work-eda`), and `/etc/hosts` maps `work-eda` to `127.0.0.1`.
- `lmstat -c <the .dat file> -a` reports `No SERVER lines in license file. (-13,66)`.
- In spite of the above, every `dbAccess` run logs `Virtuoso Framework License (111) was checked out successfully. Total checkout time was 0.03s.`

So licence checkout works for batch SKILL. The exact source of that entitlement is not identified from the observable state and was left alone -- no licence configuration was read into the repo, changed, or started.

## Virtuoso GUI state

No `virtuoso` process was running during this session (contrary to the assumption in the task brief); only `lmgrd` x2, `mgcld`, and `gdm-simple-slave` showed up in the Cadence-ish process scan.

## SKILL capability matrix (from three probe runs)

| Works in `dbAccess` SKILL | Verified |
|---|---|
| `printf` with `%s %d %L` | yes |
| `errset`, `foreach`, `let`, literals | yes |
| `getShellEnvVar("PWD")` -> `("/root/qoder_ic617_sandbox/work")` | yes |
| `getShellEnvVar("HOME"/"USER"/"CDS"/<any var>)` | yes |
| `system("date ...")` -> output lands in the log | yes |
| `shell("date ...")` -> returns `(t)` | yes |

| Not available in `dbAccess` SKILL | Result |
|---|---|
| `gettime()`, `time()`, `ctime()`, `time2str()`, `posixtime()`, `today()`, `now()`, `date()`, `getenv()`, `pipe()`, `getshellname()`, `skillVersionName()`, `getBuildInformation()` | all `nil` under `errset` |
| `funcall(<symbol>)` dispatch | returns `nil` for every candidate, even ones callable directly -- so dynamic dispatch cannot be used to probe; call candidates literally |

Because there is no clock built-in, `run_skill.sh` exports `QODER_RUN_TS` (UTC ISO-8601) so a SKILL script can report a time through `getShellEnvVar("QODER_RUN_TS")`.

## dbAccess contract (from `dbAccess -h` on this build)

```
dbAccess -load <fileName>     ; load SKILL file, execute, exit when done
dbAccess                       ; interactive, reads stdin
```
No `-restore`/`-nograph` needed on this path; those belong to `virtuoso`.

## Smoke test result

```
RUN name=skill_smoke_test rc=0 elapsed=0s timeout=180s
Virtuoso Framework License (111) was checked out successfully. Total checkout time was 0.03s.
QODER_IC617_SKILL_SMOKE_TEST_BEGIN
QODER_IC617_SKILL_SMOKE_TEST_OK
```

The script prints tokens only; it calls no `libManager*`/`db*`/`tech*` function, opens no library, and writes nothing. Its cwd is `$SANDBOX/work` and its `HOME` is `$SANDBOX/home`, so Cadence scratch files cannot land outside the sandbox. `run_skill.sh` refuses any `-load` path that is not an existing `.il` under the sandbox.

## Sandbox layout in the guest

```
/root/qoder_ic617_sandbox/
  bin/   cad_env.sh  run_skill.sh  skill_smoke_test.il  probe_skill_builtins*.il  probe_skill_time.il
  logs/  <name>_<YYYYmmdd_HHMMSS>.log   (one per run)
  work/  cwd for every run
  home/  HOME override for every run
```
