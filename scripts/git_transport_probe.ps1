<#
.SYNOPSIS
  NET-1: layered, bounded network probe for the GitHub endpoints this repository pushes to.
.DESCRIPTION
  Each layer is measured separately so a failure names its own stage instead of becoming
  "git push failed" again:

    DNS_RESOLUTION      Resolve-DnsName A and AAAA records
    TCP_CONNECTION      TcpClient with an explicit WaitOne timeout (no infinite waits)
    HTTP_RESPONSE       Invoke-WebRequest, optionally -Proxy, status code only, no redirect chase
    TLS_HANDSHAKE       reported through the HTTPS result: a response code can only exist on a
                        completed TLS session, and a certificate-validation failure is classified
                        separately -- nothing here disables validation
    GIT_SMART_HTTP      git ls-remote, direct and through the proxy, with the git error text
    PROXY_CONNECTION    TCP + HTTP against the proxy endpoint that Windows has configured for the
                        current user (WinINET), read from the registry at run time, never assumed

  Runs on the host that actually executes git (this repository pushes from Windows Git for Windows).
  Output is compact and credential-free: any proxy URL is masked before printing.
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/git_transport_probe.ps1 -Rounds 5
#>
param(
    [int]$Rounds = 3,
    [int]$TimeoutMs = 6000,
    [string]$Repo = "D:\ic617_agent_bridge",
    [string]$Ref = "refs/heads/feature/data-driver-virtuoso-schematic"
)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

function Mask([string]$u) {
    if ([string]::IsNullOrEmpty($u)) { return '' }
    return [regex]::Replace($u, '://[^/@]+@', '://***:***@')
}

function Tcpp([string]$h, [int]$p) {
    $c = New-Object Net.Sockets.TcpClient
    try {
        $r = $c.BeginConnect($h, $p, $null, $null)
        if ($r.AsyncWaitHandle.WaitOne($TimeoutMs) -and $c.Connected) { return 'OPEN' }
        return 'FAIL'
    } catch { return 'FAIL' } finally { $c.Close() }
}

function Https([string]$url, [string]$proxy) {
    try {
        $p = @{ Uri = $url; Method = 'Head'; TimeoutSec = [math]::Ceiling($TimeoutMs / 1000) + 4;
               MaximumRedirection = 0; ErrorAction = 'Stop' }
        if ($proxy) { $p['Proxy'] = $proxy }
        $r = Invoke-WebRequest @p
        return "HTTP/$([int]$r.StatusCode)"
    } catch {
        $resp = $_.Exception.Response
        if ($resp) { return "HTTP/$([int]$resp.StatusCode)" }
        $m = $_.Exception.Message
        if ($m -match 'TLS|SSL|certificate') { return 'TLS_FAIL' }
        if ($m -match 'timeout|timed out') { return 'TIMEOUT' }
        if ($m -match 'refused|reset|unreachable|abort') { return 'TCP_FAIL' }
        return ('ERR:' + ($m -replace '\s+', ' ').Substring(0, [Math]::Min(60, $m.Length)))
    }
}

function GitRemote([string]$proxy) {
    $args = @('-C', $Repo, 'ls-remote', 'origin', $Ref)
    if ($proxy) { $args = @('-c', "http.proxy=$proxy") + $args }
    try {
        $out = & git @args 2>&1 | Out-String
        if ($LASTEXITCODE -eq 0) { return 'GIT_OK' }
    } catch { $out = $_.Exception.Message }
    $o = ($out -replace '\s+', ' ')
    if ($o -match 'Connection was reset') { return 'GIT_RESET' }
    if ($o -match 'Failed to connect|Could not connect') { return 'GIT_CONNECT_FAIL' }
    if ($o -match 'timed out') { return 'GIT_TIMEOUT' }
    if ($o -match 'authentication|403|401') { return 'GIT_AUTH' }
    return ('GIT_FAIL:' + $o.Substring(0, [Math]::Min(70, $o.Length)))
}

# where the current Windows user is told to send HTTPS: WinINET, read live, never guessed
$wininet = (Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' `
            -ErrorAction SilentlyContinue)
$sysProxy = ''
if ($wininet -and [int]$wininet.ProxyEnable -eq 1 -and $wininet.ProxyServer) {
    $ps = "$($wininet.ProxyServer)".Split(',')[0].Trim()
    if ($ps -notmatch '^[a-z]+://') { $ps = "http://$ps" }
    $sysProxy = $ps
}
Write-Output ("HOST            : " + $env:COMPUTERNAME + " / git " + (git --version).Replace('git version ', ''))
Write-Output ("WININET_PROXY   : " + (Mask $sysProxy) + " (ProxyEnable=" + $wininet.ProxyEnable + ')')
Write-output ("WINHTTP_PROXY   : " + ((netsh winhttp show proxy) -join ' ' | Select-String -Pattern 'Direct|直接|http://' -SimpleMatch:$false))
Write-Output ("ENV_HTTPS_PROXY : " + (Mask "$env:HTTPS_PROXY$env:https_proxy"))
Write-Output ("GIT_HTTP_PROXY  : " + (Mask "$(git config --get http.proxy)"))
Write-Output ("GIT_HTTP_SSLBACK: " + "$(git config --get http.sslBackend) (sslVerify=" + (git config --get http.sslVerify) + ")")
Write-Output ''
Write-Output ("round  dns4/dns6  tcp_github  tcp_api  tcp_ssh443  https_direct  https_proxy  git_direct  git_proxy  proxy_tcp")

for ($i = 1; $i -le $Rounds; $i++) {
    $a4 = (Resolve-DnsName github.com -Type A -ErrorAction SilentlyContinue |
           Where-Object { $_.IPAddress } | Select-Object -First 1 -ExpandProperty IPAddress)
    $a6 = (Resolve-DnsName github.com -Type AAAA -ErrorAction SilentlyContinue |
           Where-Object { $_.IPAddress } | Select-Object -First 1 -ExpandProperty IPAddress)
    if (-not $a4) { $a4 = 'NONE' }
    if (-not $a6) { $a6 = 'none' }
    $t1 = Tcpp 'github.com' 443
    $t2 = Tcpp 'api.github.com' 443
    $t3 = Tcpp 'ssh.github.com' 443
    $u = 'https://github.com/LINboss666/microled-ic-ai-lab/info/refs?service=git-upload-pack'
    $h1 = Https $u $null
    $h2 = ''
    if ($sysProxy) { $h2 = Https $u $sysProxy } else { $h2 = 'no-proxy-configured' }
    $g1 = GitRemote $null
    $g2 = ''
    if ($sysProxy) { $g2 = GitRemote $sysProxy } else { $g2 = 'no-proxy-configured' }
    $pt = 'n/a'
    if ($sysProxy) {
        $hp = ([System.Uri]$sysProxy)
        $pt = Tcpp $hp.Host $hp.Port
    }
    Write-Output ("{0,5}  {1}/{2}  {3,10}  {4,7}  {5,9}  {6,12}  {7,12}  {8,10}  {9,10}  {10,8}" -f `
        $i, $a4, $a6, $t1, $t2, $t3, $h1, $h2, $g1, $g2, $pt)
    Start-Sleep -Milliseconds 1200
}

Write-Output ''
Write-Output 'LEGEND  dns4=A record; tcp_*=TCP within timeout; https_*=HTTP status or FAIL class;'
Write-Output '        git_*=git ls-remote outcome; proxy_tcp=can we reach the proxy itself.'
Write-Output 'NOTE    one round failing is not proof; compare counts across rounds before concluding.'
