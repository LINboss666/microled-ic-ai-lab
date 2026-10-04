# Final validation (Phase 6 + Bonus)

Executed 2026-10-04, all stages run by the agent; no manual test requested from the user.
Commands and outputs are quoted as produced.

## Actual architecture realised

```
Qoder (Windows 11) --ssh/scp, RSA key, no password--> RHEL6 (192.168.3.128) --bash -l-->
   /root/qoder_ic617_sandbox/bin/run_skill.sh --> source /etc/env/virtuoso exports -->
   dbAccess -load <skill>.il  (Virtuoso 6.1.7-64b)  --> log --> scp back to Windows
                                   ^
                                   └ fallback: vmrun guest-ops over VMware Tools (needs one-time credentials)
```

## TEST 1-7

| Test | Result | Evidence |
|---|---|---|
| TEST1 VMware detection | PASS | `vmrun list` -> `D:\BaiduNetdiskDownload\RHEL6_ic617\RHEL6_ic617\RHEL6_ic617\RHEL6_WORK.vmx`; `checkToolsState` -> `running`; `probe_vm.ps1` JSON `DisplayName=RHEL6_IC617` |
| TEST2 Guest IP reliable | PASS | `vmrun getGuestIPAddress` -> `192.168.3.128`, `IpSource=vmrun-tools`; TCP/22 open; banner `SSH-2.0-OpenSSH_5.3`. Caveat: lease is temporary (`ONBOOT=no`), see "recovery" below |
| TEST3 Windows -> RHEL6 shell | PASS | `test_ssh.ps1`: `BatchAuthOk=true`, `RemoteOutput="work-eda \| root \| Linux 2.6.32-431.el6.x86_64"`, `ExitCode=0`, key auth, no password |
| TEST4 IC617 environment found | PASS | `virtuoso -V` -> `@(#)$CDS: virtuoso version 6.1.7-64b 11/09/2015 12:45 (sjfnl165) $`; `dbAccess=/opt/IC617//tools/dfII/bin/dbAccess`; `CDS=/opt/IC617/`; `MMSIM_ROOT=/opt/MMSIM151`; env harvested from `/etc/env/virtuoso` by `cad_env.sh` |
| TEST5 SKILL smoke test | PASS | `RUN name=skill_smoke_test rc=0 elapsed=0s`; log contains `QODER_IC617_SKILL_SMOKE_TEST_OK`; license line `Virtuoso Framework License (111) was checked out successfully` |
| TEST6 End-to-end one command | PASS | Final run with **no credential env vars set at all** (`env -u QODER_GUEST_USER -u QODER_GUEST_PW -u QODER_GUEST_IP`) -> `RESULT: PASS`, all 6 stages `[PASS]`, JSON at `logs/bridge_20261004_165251.json`; the toolchain self-serves its credentials from `.ic617_agent_bridge_credentials` |
| TEST7 Repeatability | PASS | `-Repeat 3` -> all stages PASS x3, `REPEATABLE over 3 runs`; a later `-Repeat 2` run also PASS. The pulled logs are **byte-identical in SKILL output** (local md5 `A1AF0F6F` on every run); only the licence checkout duration drifts (`0.15s` on a cold first run vs `0.03s` afterwards) |
| Bonus `cadence_agent_test.il` | PASS | one command: `test_ic617_bridge.ps1 -SkillFile skill\cadence_agent_test.il -Token CADENCE_AGENT_TEST_OK` -> `RESULT: PASS`, log: `time_utc=2026-10-04T08:43:18Z`, `cwd=/root/qoder_ic617_sandbox/work`, `user=root`, `host=work-eda`, `cds_root=/opt/IC617/`, `marker=QODER-IC617-BRIDGE-LIVE`, `CADENCE_AGENT_TEST_OK` |

**QODER -> RHEL6 -> IC617 AUTOMATION BRIDGE: PASS**

## Failures encountered, root cause, fix

All three were real defects in my own tooling, found by measurement rather than guesswork:

1. `vmrun -gp` auth rejected with the first credential pair. Root cause: the credential itself, not the transport — proven by submitting the same secret through both direct Unicode and a GBK round-trip (Node-side codepoints verified as `e5af86e7a081`), and by not brute-forcing. Fix: user supplied the correct credential.
2. Guest had no IP and TCP/22 was closed on 508 scanned addresses. Root cause: `ifcfg-eth0` `ONBOOT=no`, interface never configured (`vmnetdhcp.leases` empty, guest MAC never seen in ARP, while `vmware.log` showed the virtual link up). Fix: `dhclient -1 eth0` -> `192.168.3.128/24`. sshd and the firewall needed no change (sshd already running, `-A INPUT -p tcp --dport 22 -j ACCEPT` already present).
3. `ssh: no matching host key type found. Their offer: ssh-rsa,ssh-dss`. Root cause: OpenSSH_5.3 offers only SHA-1 host keys, disabled by default since OpenSSH 8.8. Fix: per-invocation `-oHostKeyAlgorithms=+ssh-rsa -oPubkeyAcceptedKeyTypes=+ssh-rsa`, RSA-3072 key (ed25519 is unsupported by 5.3). No global SSH config touched.
4. `vmfile` wrote 0-byte files and vmrun reported "文件名无效" for `copyFileFromHostToGuest`. Root causes: (a) Git Bash rewrites POSIX-looking argv **and env values** into Windows paths, corrupting guest paths; (b) that vmrun sub-command does not work in this environment. Fix: paths travel base64-encoded, uploads use `runProgramInGuest` + `base64 -d`, every push/pull is md5-verified end to end.
5. `[guest rc=]` — exit codes never propagated. Root cause: vmrun strips `$rc`/`$?` from the outer launcher argument. Fix: the payload reports its own status via an EXIT trap inside the base64 layer; verified `rc=1` for `false`, `rc=7` for `exit 7`.
6. Bonus script aborted: `fprintf/sprintf: format spec incompatible with data - argument #2 is nil`. Root cause: `getShellEnvVar("HOSTNAME")` is nil (bash does not export HOSTNAME in a non-login shell) and SKILL's `printf` treats nil `%s` as a fatal error. Fix: `qSv()` nil-guard inside the SKILL file + `QODER_HOST` injected by `run_skill.sh`. Attempt 1 of 3.
7. `cad_env.sh: line 27: D_LIBRARY_PATH: unbound variable`. Root cause: `/etc/env/virtuoso` contains the typo `$D_LIBRARY_PATH`. Fix: pre-seed that name from `LD_LIBRARY_PATH`; the shipped wrapper was left unmodified. Attempt 1 of 1.

## Files created / modified by this session

Windows (`D:\ic617_agent_bridge\`, new project, nothing pre-existing was changed):

- `README.md`, `AGENTS.md`
- `scripts/probe_vm.ps1`, `scripts/test_ssh.ps1`, `scripts/test_ic617_bridge.ps1`
- `scripts/vmguest.mjs`, `scripts/vmfile.mjs`, `scripts/guest.sh`, `scripts/scan_tcp.mjs`
- `skill/cad_env.sh`, `skill/run_skill.sh`, `skill/skill_smoke_test.il`, `skill/cadence_agent_test.il`, `skill/probe_skill_{builtins,builtins2,time}.il`
- `reports/environment_probe.md`, `reports/cadence_probe.md`, `reports/final_validation.md`
- `logs/*` — pulled Cadence logs and `bridge_*.json` run records
- `~/.ssh/id_rsa_ic617{,.pub}` — new key pair created for this bridge
- `.ic617_agent_bridge_credentials` — added afterwards at the user's explicit request (guest user/password, recorded guest IP, SSH compat options); excluded from version control by:
- `.gitignore` — excludes the credentials file and `logs/*` content

Guest (complete list):

- `dhclient -1 eth0` (temporary lease `192.168.3.128/24`)
- `/root/.ssh/authorized_keys` — one key, mode 600
- `/root/qoder_ic617_sandbox/{bin,logs,work,home}` with the 7 pushed files and 8 run logs
- Desktop-session bookkeeping touched incidentally while probing (before the `HOME` redirect existed): `/root/.gconfd/saved_state` (GNOME gconf cache rewritten when `dbAccess -h` connected). `/root/CDS.log` and `/root/CDS.log.cdslck` are from **2022-05-09**, i.e. pre-existing image files, not written this session.
- Scratch files I created and then deleted: `/root/qoder_probe`, `/root/.ssh/qoder_probe`, `/root/.ssh/authorized_keys.chbak`, `sandbox/bin/{scp_smoke.il,cad_env_legacy.sh}`

## Safety boundary confirmation

| Question | Answer |
|---|---|
| Modified the PDK? | **No.** `find /opt/IC617 -maxdepth 2 -newermt 2026-10-04` -> empty; no `cds.lib`/tech file modified anywhere (`find ... -name cds.lib -newermt` -> empty) |
| Modified an existing Cadence library / schematic / layout? | **No.** No `dbOpen*`/`geOpen*`/`tech*`/`libManager*` call was ever made; the SKILL files only print and read environment variables. `sandbox/work` and `sandbox/home` are empty after all runs |
| Modified VM configuration? | **No.** `RHEL6_WORK.vmx` mtime is `2026-10-04 15:52:38`, which predates this session (first probe 16:12). `RHEL6_WORK.vmsd` mtime is `2017-04-11 09:18:19`, so no snapshot was created, deleted or reverted |
| Powered off / reset / suspended / rebooted anything? | **No.** The VM stayed running throughout; `vmrun` was only ever called with `list`, `checkToolsState`, `getGuestIPAddress` and guest-operations. `test_ic617_bridge.ps1` contains no power operation and its recovery path is limited to `dhclient eth0`, which only runs when credentials are present in the environment |
| Lowered Windows SSH security globally? | **No.** Legacy algorithms are passed per invocation; no SSH config file was created or edited |
| Credentials / licence values written to disk? | **Password: yes, at the user's explicit instruction on 2026-10-04** (this supersedes the original "no credentials in files" red line). It lives only in `D:\ic617_agent_bridge\.ic617_agent_bridge_credentials`, which `.gitignore` excludes, and its value appears in no report, log, `bridge_*.json`, README or memory file. Everything after the one-time key install runs key-based, so normal use never needs it. **Licence values: never copied** -- `cad_env.sh` harvests `CDS_LIC_FILE`/`LM_LICENSE_FILE` from `/etc/env/virtuoso` at run time, and all reports mask them. |

## What is deliberately NOT done

- `ONBOOT` was left `no`, so a reboot returns the guest to "no network" by design (README section 3 documents recovery).
- No attempt was made to explain why licence checkout succeeds although no process listens on the port in `CDS_LIC_FILE`; that would require touching licensing.
- No GUI automation, no Micro LED project work, no netlist/simulation runs — as instructed, the bridge stops here.
