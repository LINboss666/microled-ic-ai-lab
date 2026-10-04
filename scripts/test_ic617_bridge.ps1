#requires -Version 5.1
<#
 One-shot test of the whole Windows -> VMware -> RHEL6 -> Cadence SKILL bridge.

 Stages (each one reports PASS/FAIL and stops on first failure):
   1 vmrun found + target VM running
   2 guest IP resolved (Tools, then TCP sweep, then optional Tools recovery)
   3 SSH key auth working (legacy OpenSSH_5.3 algorithms, per-connection only)
   4 sandbox present + repo SKILL files synced into it
   5 dbAccess -load smoke test executed with a timeout
   6 log pulled back to Windows and success token verified

 SAFETY: this script never powers, suspends, resets or snapshots a VM, and never
 edits a .vmx. Recovery action it may take is limited to `dhclient eth0` inside
 the guest, and only when QODER_GUEST_PW is exported.
#>
param(
    [string]$VmxHint = 'RHEL6_WORK.vmx',
    [string]$VmrunPath = '',
    [string]$GuestIp = '',
    [string]$SshUser = 'root',
    [string]$SshKey = "$env:USERPROFILE\.ssh\id_rsa_ic617",
    [string]$SkillFile = '',
    [string]$Token = 'QODER_IC617_SKILL_SMOKE_TEST_OK',
    [int]$SkillTimeoutSec = 180,
    [int]$Repeat = 1
)
$ErrorActionPreference = 'Continue'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$CredFile = Join-Path $RepoRoot '.ic617_agent_bridge_credentials'

# Reads a NAME='value' entry from the local credentials file. That file holds the
# guest root password (persisted on 2026-10-04 at the user's explicit request):
# it must never be printed, copied into a report, or committed.
function Get-BridgeSetting([string]$Name) {
    if (-not (Test-Path $CredFile)) { return '' }
    $hit = Select-String -Path $CredFile -Pattern "^\s*$Name='([^']*)'" | Select-Object -First 1
    if ($hit) { return $hit.Matches[0].Groups[1].Value }
    return ''
}

if (-not $env:QODER_GUEST_USER) { $env:QODER_GUEST_USER = Get-BridgeSetting 'QODER_GUEST_USER' }
if (-not $env:QODER_GUEST_PW)   { $env:QODER_GUEST_PW   = Get-BridgeSetting 'QODER_GUEST_PW' }

if (-not $SkillFile) { $SkillFile = Join-Path $RepoRoot 'skill\skill_smoke_test.il' }
$Sandbox = '/root/qoder_ic617_sandbox'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$LogDir = Join-Path $RepoRoot 'logs'
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

# RHEL6 ships OpenSSH_5.3: it only offers ssh-rsa/ssh-dss host keys, which modern
# OpenSSH disables by default. These flags are applied per invocation only --
# no global SSH client configuration is modified.
$SshOpts = @('-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', '-o', 'StrictHostKeyChecking=accept-new',
             '-o', 'HostKeyAlgorithms=+ssh-rsa', '-o', 'PubkeyAcceptedKeyTypes=+ssh-rsa', '-i', $SshKey)

function Invoke-Native {
    param([string]$Exe, [string[]]$ArgList)
    $prevEap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    $raw = & $Exe @ArgList 2>&1
    $ErrorActionPreference = $prevEap
    $text = ($raw | ForEach-Object { "$_" }) -join "`n"
    [pscustomobject]@{ Code = $LASTEXITCODE; Text = $text }
}

$Stages = New-Object System.Collections.ArrayList
function Add-Stage([string]$Name, [string]$Status, [string]$Detail) {
    [void]$Stages.Add([pscustomobject]@{ Stage = $Name; Status = $Status; Detail = $Detail })
    Write-Host ('[{0}] {1}  {2}' -f $Status.PadRight(4), $Name, $Detail)
}

function Fail([string]$Name, [string]$Detail) {
    Add-Stage $Name 'FAIL' $Detail
    Write-Host ''
    Write-Host ('RESULT: FAIL  stage={0}' -f $Name)
    Write-Host ('DETAIL: {0}' -f ($Detail -split "`n")[0])
    Write-Host 'HINTS:'
    Write-Host '  - VM not running            : start RHEL6_IC617 in Workstation, then re-run.'
    Write-Host '  - no guest IP               : the interface is down inside the guest. Export QODER_GUEST_USER/QODER_GUEST_PW and re-run to let this script issue `dhclient eth0`, or run it by hand in the VM console.'
    Write-Host '  - ssh auth rejected         : /root/.ssh/authorized_keys no longer holds this key; re-run the bootstrap step in README.md.'
    Write-Host '  - no matching host key type : OpenSSH gained another default restriction; add the reported algorithm to $SshOpts only.'
    Write-Host '  - token missing             : open the pulled log in logs\ and read the Cadence error (licence / SKILL / PATH).'
    Write-Host 'NO VM POWER OPERATION WAS ATTEMPTED AND NONE WILL BE.'
    exit 1
}

# ---- stage 1: vmrun + running VM -------------------------------------------
$found = @()
if ($VmrunPath -and (Test-Path $VmrunPath)) { $found += $VmrunPath }
foreach ($c in @(
    "${env:ProgramFiles(x86)}\VMware\VMware Workstation\vmrun.exe",
    "${env:ProgramFiles}\VMware\VMware Workstation\vmrun.exe",
    "${env:ProgramFiles(x86)}\VMware\VMware Player\vmrun.exe")) {
    if (Test-Path $c) { $found += $c }
}
if (-not $found.Count) { Fail '1.vmware' 'vmrun.exe not found; pass -VmrunPath' }
$vmrun = (Resolve-Path $found[0]).Path

$listRaw = Invoke-Native $vmrun @('list')
$vms = @($listRaw.Text -split "`r?`n" | Where-Object { $_ -match '\.vmx\s*$' } | ForEach-Object { $_.Trim() })
$target = @($vms | Where-Object { $_ -like "*$VmxHint" })
if (-not $target.Count) { Fail '1.vmware' ("no running VM matching '$VmxHint'; running: " + ($vms -join ', ')) }
$vmx = $target[0]
$tools = (Invoke-Native $vmrun @('checkToolsState', $vmx)).Text.Trim()
Add-Stage '1.vmware' 'PASS' ("vmx=$vmx tools=$tools")

# ---- stage 2: guest IP ------------------------------------------------------
$ipNote = ''
if ($GuestIp) {
    Add-Stage '2.guest-ip' 'PASS' "supplied by -GuestIp=$GuestIp"
} else {
    $ipTxt = (Invoke-Native $vmrun @('getGuestIPAddress', $vmx)).Text.Trim()
    if ($ipTxt -match '(\d{1,3}(?:\.\d{1,3}){3})') { $GuestIp = $Matches[1] }
}

if (-not $GuestIp) {
    # The interface may have lost its lease (it is not persisted). Recover through the
    # Tools channel only, and only if credentials are present in the environment.
    if ($env:QODER_GUEST_USER -and $env:QODER_GUEST_PW) {
        Write-Host '  no IP yet -> asking the guest for a lease through VMware Tools'
        $node = (Get-Command node.exe -ErrorAction SilentlyContinue)
        if ($node) {
            $env:QODER_VMX = $vmx
            $recovery = Invoke-Native $node.Source @((Join-Path $PSScriptRoot 'vmguest.mjs'),
                'dhclient -1 eth0 >/dev/null 2>&1; sleep 2; ip -4 addr show dev eth0 | grep -oE "inet [0-9.]+" | head -1', '90')
            if ($recovery.Text -match '(\d{1,3}(?:\.\d{1,3}){3})') { $GuestIp = $Matches[1] }
        }
    }
}
if (-not $GuestIp) {
    # last resort: the address recorded in the local credentials file (may be stale
    # after a reboot -- the tcp/22 probe right below is what actually validates it)
    $fileIp = Get-BridgeSetting 'QODER_GUEST_IP'
    if ($fileIp) { $GuestIp = $fileIp; $ipNote = ' (from credentials file, not from Tools)' }
}
if (-not $GuestIp) {
    Fail '2.guest-ip' 'guest has no IPv4 address. Fix: run `dhclient -1 eth0` in the VM console, or export QODER_GUEST_USER/QODER_GUEST_PW so this script can do it through VMware Tools'
}

$tcp = $false
try {
    $c = New-Object System.Net.Sockets.TcpClient
    $ar = $c.BeginConnect($GuestIp, 22, $null, $null)
    if ($ar.AsyncWaitHandle.WaitOne(2500) -and $c.Connected) { $tcp = $true }
    $c.Close()
} catch { }
if (-not $tcp) { Fail '2.guest-ip' "tcp/22 closed on ${GuestIp}: sshd stopped, IP stale, or guest firewall changed" }
Add-Stage '2.guest-ip' 'PASS' "ip=$GuestIp$ipNote tcp22=open"

# ---- stage 3: ssh key auth --------------------------------------------------
$who = Invoke-Native ssh ($SshOpts + @("$SshUser@$GuestIp", 'echo BRIDGE_OK; hostname; whoami; uname -r'))
if ($who.Code -ne 0 -or $who.Text -notmatch 'BRIDGE_OK') {
    $first = ($who.Text -split "`n" | Where-Object { $_ -match 'denied|matching|route|verification|timeout|refused' } | Select-Object -First 1)
    if ($first) { Fail '3.ssh' $first } else { Fail '3.ssh' $who.Text }
}
$remoteIdent = ($who.Text -split "`n" | Where-Object { $_ -match '\S' } | Select-Object -Skip 1) -join ' / '
Add-Stage '3.ssh' 'PASS' $remoteIdent

# ---- stage 4: sandbox + sync ------------------------------------------------
$mk = Invoke-Native ssh ($SshOpts + @("$SshUser@$GuestIp",
    "mkdir -p $Sandbox/bin $Sandbox/logs $Sandbox/work $Sandbox/home && test -r /etc/env/virtuoso && echo SANDBOX_READY"))
if ($mk.Text -notmatch 'SANDBOX_READY') { Fail '4.sync' ("sandbox prep failed: " + $mk.Text) }

$toPush = @(@{ Local = (Join-Path $RepoRoot 'skill\cad_env.sh'); Remote = "$Sandbox/bin/cad_env.sh" },
            @{ Local = (Join-Path $RepoRoot 'skill\run_skill.sh'); Remote = "$Sandbox/bin/run_skill.sh" },
            @{ Local = $SkillFile; Remote = "$Sandbox/bin/$(Split-Path -Leaf $SkillFile)" })
foreach ($f in $toPush) {
    if (-not (Test-Path $f.Local)) { Fail '4.sync' ("missing local file: " + $f.Local) }
    $r = Invoke-Native scp ($SshOpts + @('-q', $f.Local.Replace('\', '/'), "${SshUser}@${GuestIp}:$($f.Remote)"))
    if ($r.Code -ne 0) { Fail '4.sync' ("scp push failed for $($f.Remote): " + $r.Text) }
}
$chmod = Invoke-Native ssh ($SshOpts + @("$SshUser@$GuestIp", "chmod +x $Sandbox/bin/run_skill.sh $Sandbox/bin/cad_env.sh && echo SYNC_OK"))
if ($chmod.Text -notmatch 'SYNC_OK') { Fail '4.sync' $chmod.Text }
Add-Stage '4.sync' 'PASS' ("pushed {0} files to $Sandbox/bin" -f $toPush.Count)

# ---- stages 5+6: run SKILL, verify token, repeated -------------------------
$remoteIl = "$Sandbox/bin/$(Split-Path -Leaf $SkillFile)"
$runs = @()
for ($i = 1; $i -le $Repeat; $i++) {
    $run = Invoke-Native ssh ($SshOpts + @("$SshUser@$GuestIp", "bash $Sandbox/bin/run_skill.sh $remoteIl $SkillTimeoutSec"))
    $logPath = ([regex]::Match($run.Text, 'LOGFILE\s+(\S+)')).Groups[1].Value
    $localLog = Join-Path $LogDir ("smoke_{0}_{1}_{2}.log" -f $Stamp, $i, (Split-Path -Leaf $remoteIl))

    if ($run.Code -eq 124 -or $run.Text -match 'rc=124') { Fail "5.skill[run$i]" "dbAccess exceeded ${SkillTimeoutSec}s (timeout); log so far:`n$($run.Text)" }
    if ($logPath) {
        $pull = Invoke-Native scp ($SshOpts + @('-q', "${SshUser}@${GuestIp}:$logPath", $localLog.Replace('\', '/')))
        if ($pull.Code -ne 0) { Fail "6.log[run$i]" "cannot pull $logPath : $($pull.Text)" }
        $verifySource = Get-Content -LiteralPath $localLog -Raw
        $logNote = "log -> $localLog"
    } else {
        $verifySource = $run.Text
        $logNote = 'LOGFILE line absent; verified from echoed stdout'
    }

    if ($verifySource -notmatch [regex]::Escape($Token)) {
        $bad = ($verifySource -split "`n" | Where-Object { $_ -match '(?i)(licen|error|fatal|cannot|unable|segmentation|abort)' } | Select-Object -First 4) -join ' | '
        if ($bad) { Fail "6.token[run$i]" "token '$Token' absent. Cadence says: $bad" }
        Fail "6.token[run$i]" "token '$Token' absent. Full output:`n$verifySource"
    }
    $rc = ([regex]::Match($run.Text, 'rc=(\d+)')).Groups[1].Value
    $elapsed = ([regex]::Match($run.Text, 'elapsed=(\d+)s')).Groups[1].Value
    Add-Stage "5.skill[run$i]" 'PASS' "dbAccess rc=$rc elapsed=${elapsed}s"
    $hashNote = ''
    if (Test-Path $localLog) { $hashNote = " local md5=$(( (Get-FileHash -LiteralPath $localLog -Algorithm MD5).Hash.Substring(0,8)) )"
    } else { $localLog = '' }
    Add-Stage "6.token[run$i]" 'PASS' "$logNote; token found$hashNote"
    $runs += [pscustomobject]@{ Run = $i; Rc = $rc; ElapsedSec = $elapsed; TokenFound = $true; Log = $localLog }
}

$result = if ($Repeat -gt 1 -and @($runs | Where-Object { -not $_.TokenFound }).Count -gt 0) { 'FAIL' } else { 'PASS' }
$summary = [ordered]@{
    Result        = $result
    Repeat        = $Repeat
    Vmx           = $vmx
    GuestIp       = $GuestIp
    SshUser       = $SshUser
    Token         = $Token
    SkillFile     = $SkillFile
    Sandbox       = $Sandbox
    Runs          = $runs
    Stages        = $Stages
    Timestamp     = (Get-Date).ToString('s')
    VmPowerTouched = $false
}
$json = $summary | ConvertTo-Json -Depth 5
Set-Content -LiteralPath (Join-Path $LogDir "bridge_$Stamp.json") -Value $json -Encoding UTF8

Write-Host ''
Write-Host '================= BRIDGE TEST ================='
$Stages | Format-Table -AutoSize | Out-String -Width 200 | Write-Host
Write-Host ('RESULT: ' + $result)
if ($result -ne 'PASS') { exit 1 }
if ($Repeat -gt 1) { Write-Host ('REPEATABLE over {0} runs (elapsed: {1}s)' -f $Repeat, (($runs.ElapsedSec | Measure-Object -Maximum).Maximum)) }
exit 0
