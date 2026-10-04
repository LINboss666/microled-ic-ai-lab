// File transfer over the VMware Tools channel (works even with no guest network).
//
// Why base64 for the paths: Git Bash rewrites env values AND argv that look like a
// POSIX path ("/tmp/x" -> "C:/Users/.../Temp/x") before handing them to a Windows
// exe, which corrupts guest-side paths. Base64 of a path starting with "/" always
// begins with "L", so it survives untouched.
//
// Required env:
//   QODER_GUEST_USER / QODER_GUEST_PW   credentials (never stored in a file)
//   QODER_MODE   push | pull
//   QODER_SRC_B64 / QODER_DST_B64       base64 of the source / destination path
import { execFile } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { readFile, rm, stat } from 'node:fs/promises';
import crypto from 'node:crypto';

const VMRUN = process.env.QODER_VMRUN || 'C:\\Program Files (x86)\\VMware\\VMware Workstation\\vmrun.exe';
const VMX = process.env.QODER_VMX || 'D:\\BaiduNetdiskDownload\\RHEL6_ic617\\RHEL6_ic617\\RHEL6_ic617\\RHEL6_WORK.vmx';
const USER = process.env.QODER_GUEST_USER;
const PW = process.env.QODER_GUEST_PW;
const MODE = process.env.QODER_MODE;
const dec = (v, what) => {
  if (!v) throw new Error(`${what} missing`);
  return Buffer.from(v, 'base64').toString('utf8');
};

const here = path.dirname(fileURLToPath(import.meta.url));

function runGuest(commandText, timeoutSec = 120) {
  return new Promise((resolve) => {
    execFile(process.execPath, [path.join(here, 'vmguest.mjs'), commandText, String(timeoutSec)],
      { env: process.env, maxBuffer: 64 * 1024 * 1024, timeout: (timeoutSec + 120) * 1000, windowsHide: true },
      (err, stdout, stderr) => resolve({ code: err ? (err.code ?? 1) : 0, out: `${stdout || ''}${stderr || ''}` }));
  });
}

async function push(srcHost, dstGuest) {
  // vmrun copyFileFromHostToGuest fails in this environment ("The filename is
  // invalid"), so write through runProgramInGuest with a base64 payload instead.
  const buf = await readFile(srcHost);
  const b64 = buf.toString('base64');
  const localMd5 = crypto.createHash('md5').update(buf).digest('hex');
  const launcher =
    `umask 022; mkdir -p "$(dirname ${dstGuest})"; ` +
    `printf '%s' '${b64}' | base64 -d > ${dstGuest} && chmod 644 ${dstGuest}; ` +
    `echo "WRC=$?"; md5sum ${dstGuest}; ls -l ${dstGuest}`;
  const r = await runGuest(launcher, 90);
  const remoteMd5 = (String(r.out).match(/([0-9a-f]{32})\s+\S+/) || [, ''])[1];
  if (remoteMd5 !== localMd5) {
    throw new Error(`md5 mismatch local=${localMd5} remote=${remoteMd5 || 'none'}\n--- guest output ---\n${String(r.out).trim().slice(0, 800)}`);
  }
  console.log(`push ok: ${srcHost} -> ${dstGuest} (${buf.length} bytes, md5 verified in guest)`);
}

async function pull(srcGuest, dstHost) {
  const r = await runGuest(`ls -l ${srcGuest} && cp -f ${srcGuest} /tmp/qoder_pull.tmp && chmod 644 /tmp/qoder_pull.tmp && md5sum /tmp/qoder_pull.tmp`, 90);
  const m = String(r.out).match(/([0-9a-f]{32})\s+\/tmp\/qoder_pull\.tmp/);
  if (!m) throw new Error(`pull staging failed:\n${String(r.out).trim().slice(0, 800)}`);
  await new Promise((resolve, reject) => {
    execFile(VMRUN, ['-gu', USER, '-gp', PW, 'copyFileFromGuestToHost', VMX, '/tmp/qoder_pull.tmp', dstHost],
      { maxBuffer: 32 * 1024 * 1024, timeout: 300000, windowsHide: true }, (err, so, se) => {
        const line = `${so}${se}`.split('\n').find((l) => l.startsWith('Error:'));
        err && line ? reject(new Error(line)) : resolve();
      });
  });
  const local = crypto.createHash('md5').update(await readFile(dstHost)).digest('hex');
  await runGuest('rm -f /tmp/qoder_pull.tmp', 30);
  if (local !== m[1]) throw new Error(`pull md5 mismatch guest=${m[1]} local=${local}`);
  const s = await stat(dstHost);
  console.log(`pull ok: ${srcGuest} -> ${dstHost} (${s.size} bytes, md5 verified)`);
}

if (!USER || !PW) { console.error('MISSING_CREDENTIALS'); process.exit(9); }
let SRC, DST;
try {
  if (!['push', 'pull'].includes(MODE)) throw new Error('QODER_MODE must be push or pull');
  SRC = dec(process.env.QODER_SRC_B64, 'QODER_SRC_B64');
  DST = dec(process.env.QODER_DST_B64, 'QODER_DST_B64');
} catch (e) {
  console.error(`[vmfile-usage] ${e.message}`);
  process.exit(9);
}

try {
  MODE === 'push' ? await push(SRC, DST) : await pull(SRC, DST);
} catch (e) {
  console.error(`[vmfile-error] ${String(e.message).split('\n').slice(0, 6).join('\n')}`);
  process.exitCode = 1;
}
