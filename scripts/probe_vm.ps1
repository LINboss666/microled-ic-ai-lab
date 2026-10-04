#requires -Version 5.1
# Phase-1 / Phase-2 VM probe. Read-only: never powers, suspends, snapshots or edits a vmx.
# Resolves: vmrun path, running VMs, target .vmx, tools state, guest IP (with fallbacks).
param(
    [string]$VmxHint = 'RHEL6_WORK.vmx',
    [string]$VmrunPath = '',
    [int]$TcpTimeoutMs = 1500
)

$ErrorActionPreference = 'Stop'
$out = [ordered]@{
    VmrunFound   = $false
    VmrunPath    = ''
    RunningVms   = @()
    TargetVmx    = ''
    DisplayName  = ''
    ToolsState   = ''
    GuestIp      = ''
    IpSource     = 'none'
    Tcp22Open    = $false
    SshBanner    = ''
    HostSubnets  = @()
    Errors       = @()
}

function Add-Err([string]$m) { $out.Errors += $m }

# --- locate vmrun ------------------------------------------------------------
$candidates = @()
if ($VmrunPath) { $candidates += $VmrunPath }
$candidates += @(
    "${env:ProgramFiles(x86)}\VMware\VMware Workstation\vmrun.exe",
    "${env:ProgramFiles}\VMware\VMware Workstation\vmrun.exe",
    "${env:ProgramFiles(x86)}\VMware\VMware Player\vmrun.exe",
    "${env:ProgramFiles}\VMware\VMware Player\vmrun.exe"
)
foreach ($c in $candidates) {
    if (Test-Path -LiteralPath $c) { $out.VmrunFound = $true; $out.VmrunPath = (Resolve-Path -LiteralPath $c).Path; break }
}
if (-not $out.VmrunFound) {
    Add-Err 'vmrun.exe not found in the usual locations'
    $out | ConvertTo-Json
    exit 2
}

# --- running VMs -------------------------------------------------------------
try {
    $raw = & $out.VmrunPath list 2>&1 | Out-String
    $lines = $raw -split "`r?`n" | Where-Object { $_ -match '\.vmx\s*$' }
    $out.RunningVms = @($lines | ForEach-Object { $_.Trim() })
} catch { Add-Err ("vmrun list failed: " + $_.Exception.Message) }

# --- target vmx --------------------------------------------------------------
$target = $out.RunningVms | Where-Object { $_ -like "*$VmxHint" } | Select-Object -First 1
if (-not $target) { $target = $out.RunningVms | Select-Object -First 1 }
$out.TargetVmx = if ($target) { $target } else { '' }
if (-not $out.TargetVmx) { Add-Err 'no running VM matched the hint' }

if ($out.TargetVmx) {
    # displayName straight from the vmx text (read-only)
    try {
        $vmx = Get-Content -LiteralPath $out.TargetVmx -Raw -ErrorAction Stop
        if ($vmx -match 'displayName\s*=\s*"([^"]+)"') { $out.DisplayName = $Matches[1] }
    } catch { Add-Err ("cannot read vmx: " + $_.Exception.Message) }

    try { $out.ToolsState = ((& $out.VmrunPath checkToolsState $out.TargetVmx 2>&1) | Out-String).Trim() }
    catch { Add-Err ("checkToolsState failed: " + $_.Exception.Message) }

    # preferred IP source: Tools
    try {
        $ip = ((& $out.VmrunPath getGuestIPAddress $out.TargetVmx 2>&1) | Out-String).Trim()
        if ($ip -match '^(\d{1,3}(?:\.\d{1,3}){3})$') { $out.GuestIp = $Matches[1]; $out.IpSource = 'vmrun-tools' }
    } catch { }
}

# --- host-side NAT / host-only subnets --------------------------------------
try {
    $adapters = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.InterfaceAlias -like 'VMware Network Adapter*' }
    foreach ($a in $adapters) {
        $prefix = ($a.IPAddress -split '\.')[0..2] -join '.'
        $out.HostSubnets += [pscustomobject]@{ Alias = $a.InterfaceAlias; IP = $a.IPAddress; Prefix = $prefix }
    }
} catch { Add-Err ("Get-NetIPAddress failed: " + $_.Exception.Message) }

# --- fallback IP discovery: TCP probe over the NAT prefixes ------------------
if (-not $out.GuestIp) {
    $guestMac = ''
    if ($out.TargetVmx) {
        try {
            $vmx = Get-Content -LiteralPath $out.TargetVmx -Raw
            if ($vmx -match 'generatedAddress\s*=\s*"([0-9a-fA-F:]+)"') { $guestMac = $Matches[1] }
        } catch { }
    }
    foreach ($pfx in ($out.HostSubnets.Prefix | Select-Object -Unique)) {
        $jobs = 1..254 | ForEach-Object {
            $ip = '{0}.{1}' -f $pfx, $_
            $c = New-Object System.Net.Sockets.TcpClient
            $ar = $c.BeginConnect($ip, 22, $null, $null)
            [pscustomobject]@{ IP = $ip; Client = $c; AR = $ar }
        }
        Start-Sleep -Milliseconds $TcpTimeoutMs
        foreach ($j in $jobs) {
            try {
                if ($j.AR.AsyncWaitHandle.WaitOne(0)) {
                    if (-not $j.Client.Connected) { throw 'refused' }
                    $ns = $j.Client.GetStream()
                    $buf = New-Object byte[] 80
                    $ns.ReadTimeout = 800
                    $n = $ns.Read($buf, 0, 80)
                    if ($n -gt 0) { $out.SshBanner = ([Text.Encoding]::ASCII.GetString($buf, 0, $n) -split "`r?`n")[0] }
                    $out.GuestIp = $j.IP; $out.IpSource = 'tcp22-sweep'
                    $j.Client.Close()
                }
            } catch { }
            try { $j.Client.Close() } catch { }
        }
    }
    if ($out.GuestIp) {
        $out.Tcp22Open = $true
    } elseif ($guestMac) {
        # is the guest even answering ARP? distinguishes "network down" from "sshd stopped"
        $nb = Get-NetNeighbor -ErrorAction SilentlyContinue |
            Where-Object { $_.LinkLayerAddress -eq ($guestMac -replace ':', '-' ).ToUpper() }
        if ($nb) {
            $out.GuestIp = $nb[0].IPAddress
            $out.IpSource = 'arp-by-generated-mac (sshd not confirmed)'
        } else {
            Add-Err ("guest MAC $guestMac never appeared in ARP -> guest interface is DOWN; no IP is obtainable until an interface is up inside the guest")
        }
    }
}

$out | ConvertTo-Json -Depth 4
