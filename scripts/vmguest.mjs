// Windows -> VMware Tools (vmrun guest ops) -> RHEL6 shell bridge.
// Credentials come ONLY from the environment (QODER_GUEST_USER / QODER_GUEST_PW),
// never from a file, so nothing secret is persisted on disk.
// The payload is base64-wrapped to avoid Windows/bash quote mangling.
// Usage: node vmguest.mjs "<shell command>" [timeoutSeconds]
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { readFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

const run = promisify(execFile);

const VMRUN = process.env.QODER_VMRUN || 'C:\\Program Files (x86)\\VMware\\VMware Workstation\\vmrun.exe';
const VMX = process.env.QODER_VMX || 'D:\\BaiduNetdiskDownload\\RHEL6_ic617\\RHEL6_ic617\\RHEL6_ic617\\RHEL6_WORK.vmx';
const USER = process.env.QODER_GUEST_USER;
const PW = process.env.QODER_GUEST_PW;

if (!USER || !PW) {
  console.error('MISSING_CREDENTIALS: set QODER_GUEST_USER and QODER_GUEST_PW');
  process.exit(9);
}
const cmdText = process.argv[2];
if (!cmdText) {
  console.error('usage: node vmguest.mjs "<shell command>" [timeoutSeconds]');
  process.exit(9);
}
const cmdTimeout = Number(process.argv[3] || 120);

const tag = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
const guestCmd = `/tmp/qoder_bridge_${tag}.sh`;
const guestOut = `/tmp/qoder_bridge_${tag}.out`;
const hostOut = path.join(os.tmpdir(), `qoder_bridge_${tag}.out`);
// The rc is self-reported from INSIDE the payload: vmrun strips "$rc"/"$?" from the
// outer launcher argument, but a base64 payload survives verbatim. The EXIT trap also
// catches scripts that call `exit N` themselves.
const payload = `trap 'q=$?; echo "__QODER_RC__=$q" 1>&2' EXIT\n${cmdText}\n`;
const b64 = Buffer.from(payload, 'utf8').toString('base64');

// No shell variables in this string: it is passed as a vmrun argv.
const launcher =
  `umask 077; printf '%s' '${b64}' | base64 -d > ${guestCmd}; ` +
  `timeout ${cmdTimeout} bash ${guestCmd} > ${guestOut} 2>&1; ` +
  `rm -f ${guestCmd}; exit 0`;

const creds = ['-gu', USER, '-gp', PW];

async function vmrun(args, label) {
  const res = await new Promise((resolve, reject) => {
    execFile(VMRUN, args, { windowsHide: true, maxBuffer: 64 * 1024 * 1024, timeout: (cmdTimeout + 90) * 1000 },
      (err, stdout, stderr) => {
        if (err && err.killed) return reject(new Error(`${label}: killed (timeout)`));
        resolve({ code: err ? err.code ?? 1 : 0, out: `${stdout || ''}${stderr || ''}`.trim() });
      });
  });
  const errLine = res.out.split('\n').find((l) => l.startsWith('Error:'));
  if (errLine) throw new Error(`${label}: ${errLine}`);
  if (res.code !== 0) throw new Error(`${label}: exit=${res.code} ${res.out.split('\n').slice(0, 3).join(' | ') || '(no output)'}`);
  return res.out;
}

try {
  await vmrun([...creds, 'runProgramInGuest', VMX, '/bin/bash', '-c', launcher], 'runProgramInGuest');
  await vmrun([...creds, 'copyFileFromGuestToHost', VMX, guestOut, hostOut], 'copyFileFromGuestToHost');
  const body = await readFile(hostOut, 'utf8');
  const m = body.match(/__QODER_RC__=(\d+)/);
  const rc = m ? m[1] : '';
  process.stdout.write(body.replace(/__QODER_RC__=\d+\s*$/, '').replace(/\n+$/, '\n'));
  if (rc === '') {
    console.error(`\n[guest rc=UNKNOWN -- timeout ${cmdTimeout}s exceeded or the guest shell was killed]`);
  } else if (rc !== '0') {
    console.error(`\n[guest rc=${rc}${rc === '124' ? ' TIMEOUT' : ''}]`);
  }
  await rm(hostOut, { force: true });
  process.exitCode = rc === '0' ? 0 : 1;
} catch (e) {
  console.error(`[bridge-error] ${e.message}`);
  process.exitCode = 2;
}
