#requires -Version 5.1
# Phase-2 SSH channel test for the RHEL6 guest.
#  - proves TCP/22 + captures the server banner (tells us the OpenSSH version)
#  - proves non-interactive key auth
#  - never edits global SSH config; compatibility flags are per-invocation only
param(
    [Parameter(Mandatory = $true)][string]$TargetIp,
    [string]$User = 'root',
    [string]$KeyPath = "$env:USERPROFILE\.ssh\id_rsa_ic617",
    [string]$KnownHostsFile = '',
    [int]$ConnectTimeoutSec = 8,
    [string[]]$CompatFlag = @('-oHostKeyAlgorithms=+ssh-rsa', '-oPubkeyAcceptedKeyTypes=+ssh-rsa')
)

$r = [ordered]@{
    Target        = $TargetIp
    Tcp22Open     = $false
    Banner        = ''
    KeyExists     = (Test-Path -LiteralPath $KeyPath)
    BatchAuthOk   = $false
    RemoteOutput  = ''
    CompatFlags   = @()
    Diagnosis     = ''
    ExitCode      = -1
}

# --- TCP 22 + banner ---------------------------------------------------------
try {
    $c = New-Object System.Net.Sockets.TcpClient
    $ar = $c.BeginConnect($TargetIp, 22, $null, $null)
    if ($ar.AsyncWaitHandle.WaitOne(2500) -and $c.Connected) {
        $c.EndConnect($ar)
        $r.Tcp22Open = $true
        $ns = $c.GetStream(); $ns.ReadTimeout = 2000
        $buf = New-Object byte[] 120
        try { $n = $ns.Read($buf, 0, 120); if ($n -gt 0) { $r.Banner = ([Text.Encoding]::ASCII.GetString($buf, 0, $n) -split "`r?`n")[0] } } catch { }
    }
    $c.Close()
} catch { $r.Diagnosis = "tcp connect failed: $($_.Exception.Message)" }

if (-not $r.Tcp22Open) {
    $r.Diagnosis = 'TCP/22 closed -> sshd is not running or not listening, or the guest interface is down'
    $r | ConvertTo-Json
    exit 3
}

# --- per-connection options only (no global config touched) ------------------
# RHEL6 ships OpenSSH_5.3, which offers only ssh-rsa/ssh-dss host keys; OpenSSH >=
# 8.8 disables those by default, so they are re-enabled for THIS connection only and
# are overridable via -CompatFlag. Nothing is written to any SSH config file.
$common = @(
    '-o', "ConnectTimeout=$ConnectTimeoutSec",
    '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=accept-new',
    '-i', $KeyPath
) + @($CompatFlag)
if ($KnownHostsFile) { $common += @('-o', "UserKnownHostsFile=$KnownHostsFile") }

$raw = & ssh @common "$User@$TargetIp" 'hostname; whoami; uname -s -r' 2>&1
$probe = ($raw | ForEach-Object { "$_" }) -join "`n"
$r.ExitCode = $LASTEXITCODE
$r.RemoteOutput = ($probe -split "`n" | Where-Object { $_ -match '\S' -and $_ -notmatch 'WARNING|post-quantum|may not want' }) -join ' | '

if ($r.ExitCode -eq 0 -and $r.RemoteOutput -match '\S') {
    $r.BatchAuthOk = $true
    $r.Diagnosis = 'OK: key-based non-interactive SSH works'
} else {
    # classify the negotiation problem instead of blindly loosening settings
    if ($probe -match 'no matching host key type found\.\s*Their offer:\s*([^\r\n]+)') {
        # wording used by OpenSSH >= 8.8 against old servers (only SHA-1 keys offered)
        $offer = ($Matches[1] -split ',')[0].Trim()
        $r.CompatFlags += "-oHostKeyAlgorithms=+$offer"
        $r.CompatFlags += "-oPubkeyAcceptedKeyTypes=+$offer"
        $r.Diagnosis = "server only offers $offer (SHA-1). Retry with these per-connection flags only; do not persist them."
    } elseif ($probe -match 'no matching (key exchange|cipher|hmac|mac) method') {
        $m = ([regex]'no matching (key exchange|cipher|hmac|mac|host key signature) method found: (\S+)').Match($probe)
        $need = if ($m.Success) { $m.Groups[2].Value } else { '' }
        switch ($m.Groups[1].Value) {
            'key exchange' { $r.CompatFlags += "-oKexAlgorithms=+$need" }
            'cipher'       { $r.CompatFlags += "-oCiphers=+$need" }
            'hmac'         { $r.CompatFlags += "-oMACs=+$need" }
            'mac'          { $r.CompatFlags += "-oMACs=+$need" }
            default        { $r.CompatFlags += "-oHostKeyAlgorithms=+$need" }
        }
        $r.Diagnosis = "legacy-algorithm mismatch ($need). Retry ONCE with the listed per-command flag; do not persist it."
    } elseif ($probe -match 'Permission denied') {
        $r.Diagnosis = 'auth rejected: key not installed in the guest authorized_keys, or wrong user'
    } elseif ($probe -match 'No route to host|Connection timed out|Connection refused') {
        $r.Diagnosis = 'network path broken (guest IP changed, interface down, or guest firewall rejects)'
    } elseif ($probe -match 'Host key verification failed') {
        $r.Diagnosis = 'known_hosts conflict; use -KnownHostsFile for a sandboxed file'
    } else {
        $r.Diagnosis = ($probe -split "`r?`n" | Select-Object -Last 3) -join ' | '
    }
}

$r | ConvertTo-Json -Depth 4
if ($r.BatchAuthOk) { exit 0 } else { exit 4 }
