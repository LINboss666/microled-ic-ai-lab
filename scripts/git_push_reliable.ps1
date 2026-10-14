<#
.SYNOPSIS
  NET-1: push one feature branch to GitHub through a transport that is tested before it is used,
  and prove the result by reading the remote SHA back independently.
.DESCRIPTION
  Why this exists: git push from this repository failed repeatedly with
  "Failed to connect to github.com port 443" / "Recv failure: Connection was reset" while
  `gh api` kept working. Diagnosis (see reports/git_network_diagnosis.md) showed the pushes were
  issued by Git for Windows on the Windows host, which is told nothing about the local proxy the
  current user is configured to use for HTTPS (WinINET 127.0.0.1:7892), while the direct path to
  github.com:443 is the one that intermittently breaks. So the rule encoded here is: measure the
  transport, use the one that works, and never declare success without a remote read-back.

  Safety properties, in the order they are enforced:
    1. resolve branch / HEAD, refuse detached or main/master without an explicit -AllowProtected
    2. run the repository safety gate (scripts/precommit_safety_check.py --mode history) and stop on FAIL
    3. read the remote ref (direct, then proxy) BEFORE pushing
    4. refuse anything but a fast-forward: the remote SHA must be an ancestor of local HEAD
    5. probe candidate transports with `git ls-remote`, pick the first that answers
    6. push --dry-run through the chosen transport
    7. push for real, ordinary push only
    8. classify the failure by stage if it fails (connect / reset / auth / hook / non-ff)
    9. read the remote SHA back independently (git ls-remote and, when available, gh api)
   10. print one verdict block

  It never uses --force, --force-with-lease or --no-verify, never merges or rebases, never rewrites
  history, never disables TLS verification, and never prints proxy credentials or tokens.
  The origin URL is never rewritten; SSH transport is not assumed usable (this host has no GitHub
  SSH identity and no trusted ssh.github.com host key).
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/git_push_reliable.ps1 -Branch feature/data-driver-virtuoso-schematic
#>
param(
    [Parameter(Mandatory = $true)][string]$Branch,
    [string]$Repo = 'D:\ic617_agent_bridge',
    [string]$Remote = 'origin',
    [string]$Proxy = '',                 # empty = read the current user's WinINET setting
    [switch]$PersistRepoProxy,           # only with a tested proxy + explicit flag: write repo-level config
    [switch]$AllowProtected,
    [int]$ConnectTimeoutMs = 8000,
    [int]$Attempts = 3
)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

function Mask([string]$s) {
    if ([string]::IsNullOrEmpty($s)) { return '' }
    return [regex]::Replace($s, '://[^/@]+@', '://***:***@')
}
function Step($n, $msg) { Write-Output ("[{0}] {1}" -f $n, $msg) }
# PS 5.1 resolves a command name as aliases -> functions -> cmdlets -> executables, so a helper
# named `Git` shadows git.exe and `& git` inside it recurses until CallDepthOverflow. The helper is
# therefore named InvokeGit and the executable is spelled git.exe.
function InvokeGit([Parameter(ValueFromRemainingArguments = $true)]$a) {
    # PS 5.1 turns a native command's stderr into ErrorRecord objects, and Out-String then prints the
    # record's display ("+ FullyQualifiedErrorId : NativeCommandError") instead of git's own words.
    # git writes normal progress to stderr, so flatten every record back to its message text: the
    # stage classifier must see "Connection was reset", not the wrapper's formatting.
    & git.exe -C $Repo @a 2>&1 | ForEach-Object {
        if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.Exception.Message } else { "$_" }
    } | Out-String
}
function Classify([string]$out) {
    $o = ($out -replace '\s+', ' ')
    if ($o -match 'Connection was reset|Recv failure')          { return 'TRANSPORT_RESET' }
    if ($o -match 'Failed to connect|Could not connect|unreachable') { return 'TRANSPORT_CONNECT' }
    if ($o -match 'timed out|timeout')                          { return 'TRANSPORT_TIMEOUT' }
    if ($o -match 'Authentication failed|403|401|permission')   { return 'AUTHENTICATION' }
    if ($o -match 'non-fast-forward|\[rejected\]')              { return 'NON_FAST_FORWARD' }
    if ($o -match 'pre-push|hook')                              { return 'HOOK_REJECTED' }
    return 'UNCLASSIFIED'
}

function Get-PreArgs($c) {
    # 'direct' must mean *no* proxy even if this repository has http.https://github.com.proxy set,
    # otherwise the two candidates would be the same route and the fallback would be an illusion.
    # The low-speed limits are git's own stall detector: a half-open direct connection was observed
    # to hang with no output until killed externally, and a hang is not a measurable failure.
    $secs = [math]::Max(10, [int]($ConnectTimeoutMs / 1000))
    $a = @('-c', 'http.lowSpeedLimit=1024', '-c', "http.lowSpeedTime=$secs")
    if ($c.Proxy) { $a += @('-c', "http.proxy=$($c.Proxy)") } else { $a += @('-c', 'http.proxy=') }
    return $a
}

$results = [ordered]@{}
$fail = ''

# ---- 1. what would be pushed ---------------------------------------------------------------
$head = (InvokeGit rev-parse --verify "$Branch").Trim()
$detached = (InvokeGit symbolic-ref -q --short HEAD).Trim()
if (-not $head -or $head -notmatch '^[0-9a-f]{40}$') { Write-Output "ABORT: cannot resolve $Branch"; exit 9 }
Step 1 "branch=$Branch local_head=$head HEAD_is=$detached"
if ($Branch -in @('main', 'master') -and -not $AllowProtected) {
    Write-Output 'ABORT: refusing to push a protected branch from this tool (merge is a human decision)'
    exit 9
}
if ($detached -ne $Branch) { Write-Output "ABORT: checked-out branch ($detached) is not $Branch" ; exit 9 }

# ---- 2. safety gate ------------------------------------------------------------------------
Step 2 'running scripts/precommit_safety_check.py --mode history'
$gate = ''
if (Test-Path (Join-Path $Repo 'scripts\precommit_safety_check.py')) {
    $gate = (& python (Join-Path $Repo 'scripts\precommit_safety_check.py') --mode history 2>&1 | Out-String)
}
$gateLine = ($gate -split "`n" | Where-Object { $_ -match 'SAFETY_GATE' }) -join ' '
Write-Output ("     " + $gateLine.Trim())
if ($gateLine -notmatch 'SAFETY_GATE: PASS') { Write-Output 'ABORT: safety gate did not pass'; exit 8 }
$results['SAFETY_GATE'] = 'PASS'

# ---- 3+4. remote state, before touching anything --------------------------------------------
if (-not $Proxy) {
    $w = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction SilentlyContinue
    if ($w -and [int]$w.ProxyEnable -eq 1 -and $w.ProxyServer) {
        $Proxy = "$($w.ProxyServer)".Split(',')[0].Trim()
        if ($Proxy -notmatch '^[a-z]+://') { $Proxy = "http://$Proxy" }
    }
}
# Order is measured, not assumed (see reports/git_network_diagnosis.md, 2026-10-09 window):
# the configured proxy route completed every operation attempted, while the direct route to
# github.com:443 failed repeatedly -- at TCP connect, by hanging mid-request, and by truncating the
# smart-HTTP stream. A proxy that is switched off fails on loopback in milliseconds, so trying it
# first costs nothing and the direct route is still attempted if it does.
$candidates = New-Object System.Collections.Generic.List[object]
if ($Proxy) { $candidates.Add([pscustomobject]@{ Name = 'proxy'; Proxy = $Proxy }) }
$candidates.Add([pscustomobject]@{ Name = 'direct'; Proxy = $null })
Step 3 ("remote state through: " + (($candidates | ForEach-Object { $_.Name }) -join ', ') +
       "   (proxy URL masked: " + (Mask $Proxy) + ')')

$remoteSha = ''
$chosen = $null
foreach ($c in $candidates) {
    $pre = Get-PreArgs $c
    $out = InvokeGit ($pre + @('ls-remote', $Remote, "refs/heads/$Branch"))
    $sha = ([regex]::Match($out, '\b[0-9a-f]{40}\b')).Value
    if ($sha) {
        Step 3 ("  {0,-6} ls-remote OK remote_sha={1}" -f $c.Name, $sha.Substring(0, 8))
        if (-not $remoteSha) { $remoteSha = $sha }
        if (-not $chosen) { $chosen = $c }
    } elseif ($LASTEXITCODE -eq 0) {
        # rc=0 with no line means the transport works and the branch simply does not exist yet
        Step 3 ("  {0,-6} ls-remote OK, branch absent on remote" -f $c.Name)
        if (-not $chosen) { $chosen = $c }
    } else {
        Step 3 ("  {0,-6} ls-remote FAILED -> stage={1}" -f $c.Name, (Classify $out))
    }
}
if (-not $chosen) {
    Write-Output 'ABORT: no transport answered ls-remote; nothing was pushed'
    Write-Output 'STATUS: GIT_TRANSPORT_UNAVAILABLE (report the failing stage, do not loop on the same command)'
    exit 7
}
Step 4 ("chosen transport = " + $chosen.Name)
$results['SELECTED_TRANSPORT'] = $chosen.Name

if ($remoteSha) {
    $anc = InvokeGit @('merge-base', '--is-ancestor', $remoteSha, $head)
    if ($LASTEXITCODE -ne 0) {
        if ($remoteSha -eq $head) { Step 4 'remote already equals local HEAD: nothing to push' }
        else {
            Write-Output "ABORT: remote $remoteSha is not an ancestor of local $head -- the branch moved elsewhere. Fetch and inspect; do not force."
            exit 6
        }
    } else { Step 4 'push is a fast-forward' }
} else {
    Step 4 'remote branch does not exist yet (a new branch push, still non-forced)'
}

# ---- 6. dry run through the chosen transport --------------------------------------------------
$pre = Get-PreArgs $chosen
Step 6 'push --dry-run'
$dry = InvokeGit ($pre + @('push', '--dry-run', $Remote, "refs/heads/$Branch`:refs/heads/$Branch"))
$dryClass = ''
# a dry run of a real push prints a summary line containing "->"; an up-to-date branch prints
# "Everything up-to-date". git indents the summary, so match the arrow itself, not its column.
if ($LASTEXITCODE -ne 0 -or ($dry -notmatch '->' -and $dry -notmatch 'up-to-date')) { $dryClass = Classify $dry }
Write-Output ("     " + (($dry -split "`n" | Where-Object { $_ -match '->|up-to-date|error|fatal|reject' } | Select-Object -First 3) -join ' | ').Trim())
if ($dryClass) { Write-Output "ABORT: dry-run failed at stage $dryClass (hook output above, if any, is real)"; exit 5 }
$results['DRY_RUN_TEST'] = 'PASS'

# ---- 7. the real push -------------------------------------------------------------------------
$pushed = $false
$lastOut = ''
$pushAttempts = 0
for ($i = 1; $i -le $Attempts; $i++) {
    Step 7 "push attempt $i of $Attempts (ordinary push, no force, hooks enabled)"
    $pushAttempts = $i
    $out = InvokeGit ($pre + @('push', $Remote, "refs/heads/$Branch`:refs/heads/$Branch"))
    $lastOut = $out
    Write-Output ("     " + (($out -split "`n" | Where-Object { $_ -match '\->|error|fatal|Everything|remote:' } | Select-Object -First 4) -join ' | ').Trim())
    if ($LASTEXITCODE -eq 0) { $pushed = $true; break }
    $cls = Classify $out
    Write-Output "     attempt $i failed at stage $cls"
    if ($cls -in @('AUTHENTICATION', 'NON_FAST_FORWARD', 'HOOK_REJECTED', 'UNCLASSIFIED')) { break }
    # transport-class failures are the only ones worth retrying, and only with a gap
    if ($i -lt $Attempts) {
        Start-Sleep -Seconds (4 * $i)
        $alt = $candidates | Where-Object { $_.Name -ne $chosen.Name } | Select-Object -First 1
        if ($alt) {
            $chosen = $alt
            $pre = Get-PreArgs $alt
            Write-Output ("     falling back to the '{0}' transport for the next attempt" -f $alt.Name)
        }
    }
}
if (-not $pushed) {
    Write-Output ("STATUS: PUSH_FAILED at stage " + (Classify $lastOut))
    Write-Output '        no --force, no --no-verify and no history rewrite were attempted, by design.'
    exit 4
}
$results['PUSH_TRANSPORT'] = $chosen.Name
$results['PUSH_ATTEMPTS'] = $pushAttempts

# ---- 9. independent read-back ------------------------------------------------------------------
Step 9 'read the remote SHA back independently'
# Independence means not trusting the push's own stdout. Re-read the ref with a fresh ls-remote on
# each candidate route and record which one answered, so the verdict never depends on a route that
# is known to be down. (A List cannot be combined with + here -- PS 5.1 has no op_Addition for it.)
$order = @()
foreach ($c in $candidates) { if ($c.Name -ne $chosen.Name) { $order += $c } }
$order += $chosen
$remoteAfter = ''
$readVia = 'none'
foreach ($c in $order) {
    $v = InvokeGit ((Get-PreArgs $c) + @('ls-remote', $Remote, "refs/heads/$Branch"))
    $remoteAfter = ([regex]::Match($v, '\b[0-9a-f]{40}\b')).Value
    if ($remoteAfter) { $readVia = $c.Name; break }
    Write-Output ("     read-back via {0} failed: {1}" -f $c.Name, (Classify $v))
}
$gh = ''
if (Get-Command gh -ErrorAction SilentlyContinue) {
    $gh = (& gh.exe api "repos/LINboss666/microled-ic-ai-lab/git/refs/heads/$Branch" --jq '.object.sha' 2>&1 |
        ForEach-Object { if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.Exception.Message } else { "$_" } } |
        Out-String).Trim()
}
Write-Output "     git ls-remote ($readVia): $remoteAfter"
Write-Output "     gh api (api.github.com) : $gh"
$results['REMOTE_READ_VIA'] = $readVia
$results['REMOTE_SHA_GIT'] = $remoteAfter
$results['REMOTE_SHA_GH'] = $gh
# gh asks api.github.com -- a different host from github.com, so it is an independent witness, not a
# second try at the same broken route. Prefer a git read when both answer; fall back to gh when the
# git routes are down; never call it PASS on an empty read.
$remoteFinal = $remoteAfter
$finalSrc = "git/$readVia"
if (-not $remoteFinal -and $gh -match '^[0-9a-f]{40}$') { $remoteFinal = $gh; $finalSrc = 'gh/api.github.com' }
$results['REMOTE_SHA'] = $remoteFinal
$results['REMOTE_SHA_SOURCE'] = $finalSrc
if ($remoteFinal -eq $head) { $results['LOCAL_REMOTE_PARITY'] = 'PASS' }
elseif ($remoteFinal) { $results['LOCAL_REMOTE_PARITY'] = "FAIL(remote=$remoteFinal)" }
else { $results['LOCAL_REMOTE_PARITY'] = 'UNVERIFIED' }

# ---- optional, explicitly requested persistence -----------------------------------------------
if ($PersistRepoProxy -and $chosen.Proxy -and $results['LOCAL_REMOTE_PARITY'] -eq 'PASS') {
    Step 10 'persisting the proven proxy as REPOSITORY-local config only'
    InvokeGit @('config', '--local', "http.https://github.com.proxy", $chosen.Proxy)
    Write-Output ("     stored: http.https://github.com.proxy=" + (Mask $chosen.Proxy) + ' (undo: git config --local --unset http.https://github.com.proxy)')
}

Write-Output ''
Write-Output '===== RESULT ====='
$results.GetEnumerator() | ForEach-Object { Write-Output ("{0,-22}: {1}" -f $_.Key, $_.Value) }
Write-Output ("BRANCH                : " + $Branch)
Write-Output ("LOCAL_SHA             : " + $head)
$final = if ($results['LOCAL_REMOTE_PARITY'] -eq 'PASS') { 'PUSH_AND_PARITY: PASS' } else { 'PUSH_REPORTED_SUCCESS REMOTE_PARITY_UNVERIFIED' }
Write-Output $final
if ($results['LOCAL_REMOTE_PARITY'] -ne 'PASS') { exit 3 }
exit 0
