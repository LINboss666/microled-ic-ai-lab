# NET-1: GitHub Git transport diagnosis (Windows host, HTTPS smart-http)

Date of measurement: 2026-10-09, one continuous session of roughly 40 minutes.
Repository: `D:\ic617_agent_bridge` -> `https://github.com/LINboss666/microled-ic-ai-lab.git`
Every number below comes from a command in this session; the command is named in the row.
Privacy: no token, no credential, no Authorization header, no cookie and no proxy password appears
in this file. The proxy endpoint used here carries no userinfo component (`http://127.0.0.1:7892`),
so nothing needed masking; the process name of the local proxy service was observed in-session and
is deliberately not written down, so this report stays safe to publish.

## 0. Where git actually runs (settled first, because it changes every later conclusion)

`OBSERVED_FACT`

| item | value | source |
|---|---|---|
| git execution host | Windows, `LAPTOP-0AICPJF1` | `git_transport_probe.ps1` HOST line |
| git build | `git version 2.49.0.windows.1` (Git for Windows, libcurl) | same |
| git TLS backend | `http.sslBackend = schannel`, `http.sslVerify` unset (= default, verifying) | `git config --get` |
| RHEL guest involvement in push | none — the guest is never contacted for git operations | push commands run only on Windows |

The RHEL 6.5 VM and its network stack are not on the git path at all. Windows proxy settings and
guest network configuration are therefore two unrelated subjects; only the former matters here.
Neither VMware NAT, guest networking, nor the SSH bridge was modified for this investigation.

## 1. Proxy / configuration inventory

`OBSERVED_FACT` — measured with `git config --global/--get-regexp`, `printenv`,
`[Environment]::GetEnvironmentVariable(..., 'User'|'Machine')`, registry `HKCU:\...\Internet Settings`,
`netsh winhttp show proxy`.

| layer | result |
|---|---|
| git `http.proxy` / `https.proxy` / `socks5.proxy`, global | unset |
| git `http.proxy` / `https.proxy` / `socks5.proxy`, repository | unset |
| git URL-scoped `http.<url>.proxy`, remote-scoped | none |
| env `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY`/`NO_PROXY` (+lowercase), process | unset |
| same, User scope / Machine scope | unset |
| Windows **WinINET** (per-user, what browsers and many apps use) | `ProxyEnable=1`, `ProxyServer=http://127.0.0.1:7892` |
| Windows **WinHTTP** service proxy | direct (no proxy) |
| `gh` (Go binary, `ProxyFromEnvironment`) | no proxy configured -> goes direct |
| proxy endpoint liveness | TCP connect to `127.0.0.1:7892` = `OPEN`, with active connections |
| proxy forwarding ability | GitHub HTTPS through it = `HTTP/405` and `git ls-remote` OK |

Two consequences, both measured rather than assumed:

1. **git is not told about the user's proxy.** It resolves `github.com` and connects directly.
2. **The candidate root cause "gh api uses proxy / git push bypasses proxy" is FALSIFIED.** `gh` is a
   Go program using `ProxyFromEnvironment`; with no proxy env var set anywhere it also goes direct.
   So the difference between "gh keeps working" and "git push fails" is *not* proxy awareness.

The real asymmetry is the destination host:

`OBSERVED_FACT` (`Resolve-DnsName`, IPv4 and IPv6 recorded separately)

| host | A (IPv4) | AAAA (IPv6) | used by |
|---|---|---|---|
| `github.com` | `20.205.243.166` | none | git smart-http (fetch **and** push) |
| `api.github.com` | `20.205.243.168` | none | `gh api` |
| `ssh.github.com` | `20.205.243.160` | none | SSH over 443 |

Three different IPs, all IPv4-only. IPv6 could not have been the failure, so nothing was done to it:
no `hosts` entry, no IPv6 disable, no DNS change.

## 2. Layered results per endpoint

`OBSERVED_FACT` — `scripts/git_transport_probe.ps1 -Rounds 5`, 1.2 s between rounds, every probe
bounded (TCP `WaitOne` 6 s, HTTP 10 s, git wrapped in `timeout`). A response code can only exist on a
completed TLS session, so `HTTP/n` also proves `TLS_HANDSHAKE` succeeded; certificate-validation
failures were classified separately and none occurred (validation was never disabled).

Window A (first 5 rounds, all "up"):

| stage | github.com:443 | api.github.com:443 | ssh.github.com:443 |
|---|---|---|---|
| DNS_RESOLUTION | `20.205.243.166`, 5/5 | `...168`, 5/5 | `...160`, 5/5 |
| TCP_CONNECTION | OPEN 5/5 | OPEN 5/5 | OPEN 5/5 |
| PROXY_CONNECTION (loopback proxy) | OPEN 5/5 | — | — |
| TLS+HTTP_RESPONSE direct | `HTTP/405` 5/5 | `HTTP/405` 5/5 | n/a |
| TLS+HTTP_RESPONSE via proxy | `HTTP/405` 5/5 | — | — |
| GIT_SMART_HTTP direct | `GIT_OK` 5/5 | n/a | n/a |
| GIT_SMART_HTTP via proxy | `GIT_OK` 5/5 | n/a | n/a |
| GIT_AUTHENTICATION | succeeded (push landed) | succeeded | **failed, no identity** (see §4) |

`HTTP/405` is the expected answer to `HEAD` on `.../info/refs?service=git-upload-pack` — it proves the
request reached GitHub's git endpoint, not that something is wrong.

Window B (later in the same session, same commands, same host):

| test | direct | via proxy |
|---|---|---|
| `git ls-remote` x3 consecutive | 3/3 FAIL | 3/3 OK (`rc=0`) |
| failure text observed | `Failed to connect to github.com port 443 after 21114 ms: Could not connect to server`; and `fatal: expected flush after ref listing`; and a hang needing an external kill | none |
| `gh api .../git/refs/heads/<branch>` | returned the SHA | — |

Window C (the §8 mandated consecutive test, ~4 s spacing, both routes back to back):

| route | consecutive `git ls-remote` | `git push --dry-run` |
|---|---|---|
| configured proxy | **5/5 OK** | **2/2 OK** |
| forced direct (`-c http.proxy=`) | **0/5** — 4x `Failed to connect ... port 443`, 1x `RPC failed; curl 28 Operation too slow. Less than 1024 bytes/sec` | not reached |

`OBSERVED_FACT`: the direct route flapped between 5/5 and 0/5 inside one session. The proxy route did
not fail once across every attempt recorded here (probe 5, script runs 5, consecutive 5, trials 6,
dry-runs 2, push 1, read-backs 2).

`OBSERVED_FACT`: the same route also failed at **two different layers** — TCP connect never
completing, and a connected session whose smart-http stream stalled or was truncated
(`expected flush after ref listing`, `curl 28`). A single-layer explanation would be wrong.

## 3. Direct vs configured proxy: which is more stable

`ROOT_CAUSE_CONFIRMED` (the failing stage — repeatable in three independent windows, same host, same
binary, same credentials, minutes apart):

> Push failures happen on the **direct HTTPS route from this Windows host to
> `github.com:443` / `20.205.243.166`**. The failure is intermittent and manifests at TCP connect and
> at smart-http stream level. Through the user's configured loopback proxy the identical git operation
> completes. Because git carried no proxy configuration at any scope and no fallback existed, a dip
> on that one edge turned into a hard `git push` failure, while `gh` kept working — `gh` talks to
> `api.github.com` (`...168`), a different edge that stayed healthy.

`ROOT_CAUSE_HYPOTHESIS` (not proven, deliberately not promoted):

* Why that edge flaps is **not determined**. Candidates that were not tested: routing/peering between
  this ISP and GitHub's fronting address, the local proxy/security software interfering with direct
  outbound 443 selectively, GitHub-side load-balancer rotation between healthy and unhealthy backends.
  Nothing on this host was changed that could explain it, and no measurement here can distinguish
  those three.
* `HTTP/1.1` as a fix: **unproven, and not adopted as a conclusion.** One trial used
  `-c http.version=HTTP/1.1` in a window when the route was already failing and it did not help; the
  successful pushes were made with git's default HTTP. Recording `HTTP/1.1 = FIXED` would be
  unsupported by this evidence.

Explicitly ruled out as causes, each by measurement in §1: git proxy misconfiguration *symmetry*
(both tools go direct), missing credentials (auth succeeded), TLS validation (never disabled, no
certificate error ever observed), IPv6 (no AAAA records at all), DNS resolution (always succeeded),
VMware/guest networking (not on the path), and repository state (remote was always a strict ancestor).

## 4. SSH over 443

`OBSERVED_FACT`

* `ssh.github.com:443` TCP open; server offered `SSH-2.0-...`.
* `ssh-keyscan -p 443 ssh.github.com` returned three host keys. Their SHA256 fingerprints were
  compared against GitHub's **published key material** from `GET /meta` (`gh api meta --jq
  .ssh_keys[]`), fingerprinted locally with `ssh-keygen -lf`:

| algo | observed at `ssh.github.com:443` | from `api.github.com/meta` | match |
|---|---|---|---|
| ED25519 | `SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU` | same | yes |
| RSA (3072) | `SHA256:uNiVztksCsDhcc0u9e8BujQXVUpKZIDTMczCvj3tD2s` | same | yes |
| ECDSA | `SHA256:p2QAMXNIC1TJYWeIOttrVc98/R1BUFWu3/LiyKgUfQM` | same | yes |

  So the endpoint is genuinely GitHub and the proxy is **not** terminating the SSH session.
* Authentication was attempted with `StrictHostKeyChecking=yes` (never `no`, no auto-accept) and
  `BatchMode=yes`, using a `UserKnownHostsFile` in `/tmp` seeded from the verified `/meta` key, so
  `~/.ssh` stayed untouched: `git@github.com: Permission denied (publickey).`
* Local key inventory: only `id_rsa_ic617(.pub)`, which is the guest/VM key. No GitHub entry in
  `~/.ssh/known_hosts`. Listing the account's registered keys via `gh api user/keys` returns HTTP 404
  because the token lacks `admin:public_key`; requesting that scope would have been a credential
  change, so it was **not** done.

Verdict: `SSH_443: AUTH_NOT_CONFIGURED`. Reachable and host-authentic, but there is no usable GitHub
SSH identity on this host. Per the task boundary, the step stops here rather than generating or
registering a key. `origin` remains the HTTPS URL; it was not swapped.

## 5. What was changed on this machine

`OBSERVED_FACT`

* Global git config: **unchanged**. Windows proxy: **unchanged**. Proxy software: **unchanged**,
  never restarted or closed. Registry: read-only. `~/.ssh`, `git config --global`, DNS, hosts,
  firewall: **untouched**. No `http.sslVerify=false`, no `--force`, no `--no-verify`, no
  `--force-with-lease`, no REST ref rewrite.
* Only command-level, per-invocation flags were used (`-c http.proxy=...`, `-c http.lowSpeed*`,
  `-c http.version=...`), plus a temporary `UserKnownHostsFile` under `/tmp`.
* Repository-level transport config (`http.https://github.com.proxy`) was deliberately **not
  persisted**: it would make bare `git push` depend on the proxy process running, and would convert a
  future "proxy app closed" into a new failure mode, while the tested script already probes both
  routes and falls back. This is offered as an option for the user to authorise, not applied:
  `git -C D:\ic617_agent_bridge config --local http.https://github.com.proxy http://127.0.0.1:7892`
  (undo with `--unset`).

## 6. Consequence for how pushes should be done

The transport is now chosen by measurement at run time instead of by memory: probe both routes,
prefer the one that answers, retry on the other only for transport-class failures, and never report
success without re-reading the remote SHA through a route independent of the push. Implemented in
`scripts/git_push_reliable.ps1`; results in `reports/lessons_learned/git_transport_instability.md`.
