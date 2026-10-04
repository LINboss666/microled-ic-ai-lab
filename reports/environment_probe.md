# Environment probe (Phase 1)

Probed on 2026-10-04. Read-only probing; no VM state, no .vmx, no snapshot was touched.
No credential material is recorded in this file.

## Host (Windows)

| Item | Detected value |
|---|---|
| OS | Windows 11 Home China, build 10.0.26100 |
| PowerShell | 5.1.26100.5074 (Windows PowerShell; no `pwsh` / PS7 found -> `-Parallel` unavailable) |
| Bash | Git Bash (MSYS2), used as the agent shell |
| User | <windows-user> |
| OpenSSH client | `ssh` 9.9p2 / OpenSSL 3.2.4 (`/usr/bin/ssh`, also Windows built-in) |
| `sshpass` / `plink` / `pscp` / `expect` | not installed |
| Node.js | v24.15.0 (usable for concurrent TCP probing) |
| Python | 3.12 at `AppData/Local/Programs/Python/Python312` |
| Host-side `sshd` | not running (host TCP 22 closed) |

## VMware

| Item | Detected value |
|---|---|
| Product | VMware Workstation 17.6.3, build 24583834 |
| `vmrun.exe` | `C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe` (510,840 bytes, 2025-02-20). Not on PATH; full path is used. |
| `vmrun list` | works without credentials (VMAuthdService running) |
| Services | VMAuthdService, VMnetDHCP, VMUSBArbService, VMware NAT Service = Running; VmwareAutostartService = Stopped |
| Processes | `vmware`, `vmware-vmx`, `vmnat`, `vmnetdhcp`, `vmware-authd`, `vmware-usbarbitrator64`, `vmware-tray` |

## Running VM

| Item | Detected value |
|---|---|
| displayName | `RHEL6_IC617` |
| .vmx | `D:\BaiduNetdiskDownload\RHEL6_ic617\RHEL6_ic617\RHEL6_ic617\RHEL6_WORK.vmx` |
| guestOS | `rhel6-64` |
| vmx process | `x64\vmware-vmx.exe ... -# product=1;...version=17.6.3;buildnumber=24583834` |
| Network | `ethernet0.connectionType = nat`, `virtualDev = e1000`, generated MAC `00:0c:29:9d:61:09` |
| Disk | `scsi0.virtualDev = lsilogic`, split vmdk `RHEL6_WORK-s001..s0xx` (~60 GB grown; 2026-10-04 writes visible) |
| Memory | `mem.hotadd = TRUE` (vmx does not pin a fixed size line; hot-add enabled) |
| Tools | `vmrun checkToolsState` -> `running`; legacy tools version 10245, toolbox + toolbox-dnd active in log |
| Second VM in inventory | `C:\Users\<windows-user>\Documents\Virtual Machines\Ubuntu 64 位\Ubuntu 64 位.vmx` (not running) |

## Guest IP discovery - NOT yet obtained

Evidence collected:

1. `vmrun getGuestIPAddress <vmx> -verbose` -> `Error: Unable to get the IP address`.
   Tools is `running` but does not report `guestinfo.ipaddress` (typical when no interface is up, or old open-vm-tools does not push the network payload).
2. `C:\ProgramData\VMware\vmnetdhcp.leases` -> header only, **zero leases**. The guest never requested a DHCP address.
3. NAT segment is `192.168.3.0/24` (`ip = 192.168.3.2/24` in `vmnetnat.conf`; host VMnet8 adapter = `192.168.3.1`, gateway = `.2`, MAC `00-50-56-E4-04-B5`).
4. Concurrent TCP/22 sweep over `192.168.3.1-254` and `192.168.142.1-254` (508 hosts, banner capture) -> `NONE_OPEN`.
5. After that sweep, `Get-NetNeighbor`: VMnet8 gateway `.254` is present, every `192.168.3.x` is `Unreachable`, and the guest MAC `00-0C-29-*` **never appears**. A live guest would have answered those SYNs (RST or SYN/ACK) and appeared as a neighbour.
6. `vmware.log` shows `ethernet0` link state went up (`MACVNetLinkStateEventHandler: event, up:1`), i.e. the virtual cable is connected - so this is a guest-side interface problem, not a host/VMware configuration problem.

**Conclusion:** the guest's network interface is down / has no address. ICMP, TCP 22 and `vmrun getGuestIPAddress` all fail for the same reason. The automation channel therefore cannot start with SSH until an interface is configured inside RHEL6.

## Channel status

| Channel | Status |
|---|---|
| `vmrun` VM management (list, state, snapshot query) | Working |
| `vmrun` guest operations (run / copy / delete) | Reachable, but **authentication rejected** -> blocked on credentials |
| SSH Windows -> RHEL6 | Blocked (no guest IP, no listening TCP 22) |

Authentication was diagnosed, not guessed: the supplied credential was submitted through two byte-encodings (direct Unicode, and a GBK round-trip so the guest would receive raw UTF-8 bytes). Both returned `Error: Invalid user name or password for the guest OS`. Node's receive-side encoding was verified (`utf8hex=e5af86e7a081`), so the Windows->vmrun argument path is correct; the credential itself does not match the guest. No password-guessing or brute-force attempts were made.

## Not done (per red lines)

- No power operations, no snapshot create/delete/revert, no `.vmx` edit
- No PDK / Cadence library / schematic / layout access
- No firewall or license change
- No credentials written to any file
