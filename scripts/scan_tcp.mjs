// Fast concurrent TCP-22 sweep across VMware NAT / host-only subnets.
// Read-only discovery: no VM state changes, no credentials used.
import net from 'node:net';

const prefixes = (process.argv[2] || '192.168.3').split(',');
const port = Number(process.argv[3] || 22);
const timeoutMs = Number(process.argv[4] || 1200);

function probe(host) {
  return new Promise((resolve) => {
    const s = net.createConnection({ host, port });
    let done = false;
    const finish = (open, banner) => {
      if (done) return;
      done = true;
      s.destroy();
      resolve({ host, open, banner });
    };
    s.setTimeout(timeoutMs);
    s.on('connect', () => finish(true));
    s.on('data', (b) => finish(true, b.toString('utf8').split('\r\n')[0].slice(0, 60)));
    s.on('timeout', () => finish(false));
    s.on('error', () => finish(false));
  });
}

const targets = [];
for (const p of prefixes) for (let i = 1; i <= 254; i++) targets.push(`${p}.${i}`);

const found = [];
const queue = [...targets];
async function worker() {
  while (queue.length) {
    const ip = queue.shift();
    const r = await probe(ip);
    if (r.open) found.push(r);
  }
}
await Promise.all(Array.from({ length: 64 }, worker));

console.log(`scanned ${targets.length} hosts on tcp/${port}`);
if (!found.length) console.log('NONE_OPEN');
for (const f of found.sort((a, b) => a.host.localeCompare(b.host, undefined, { numeric: true }))) {
  console.log(`OPEN ${f.host}:${port}${f.banner ? `  banner=${f.banner}` : ''}`);
}
