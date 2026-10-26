#!/usr/bin/env node
// Run CloudTAK's own build gates against this plugin, the way its Docker build does, without
// installing anything into a real deploy.
//
//   CLOUDTAK_DIR=/path/to/CloudTAK node cloudtak/check-in-cloudtak.mjs
//
// Handles both CloudTAK source layouts (see install.sh): copies the web half and the server
// route into place (rewriting the route's imports for the 13.1xx+ layout exactly as install.sh
// does), runs web lint + vue-tsc and — if the API's node_modules exist — the API's tsc, then
// removes the copies. Needs `npm install` done in the web app dir (and optionally api/).
import { cpSync, existsSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const cloudtak = process.env.CLOUDTAK_DIR;
if (!cloudtak) {
    console.error('Set CLOUDTAK_DIR to a CloudTAK checkout.');
    process.exit(2);
}

const split = existsSync(join(cloudtak, 'app', 'plugin.ts'));
const web = split ? join(cloudtak, 'app') : join(cloudtak, 'api', 'web');
const routes = split ? join(cloudtak, 'api', 'stateless', 'routes') : join(cloudtak, 'api', 'routes');
if (!existsSync(join(web, 'plugin.ts'))) {
    console.error(`${cloudtak} doesn't look like a CloudTAK checkout.`);
    process.exit(2);
}
const version = JSON.parse(readFileSync(join(cloudtak, 'package.json'), 'utf8')).version;
console.log(`CloudTAK ${version} (${split ? 'split app/ + api/stateless' : 'legacy api/web'} layout)`);

const pluginDest = join(web, 'plugins', 'aleph');
const routeDest = join(routes, 'plugin-aleph.ts');
rmSync(pluginDest, { recursive: true, force: true });
cpSync(join(here, 'plugin'), pluginDest, {
    recursive: true,
    filter: (src) => !/node_modules|package(-lock)?\.json$/.test(src),
});
let route = readFileSync(join(here, 'server', 'plugin-aleph.ts'), 'utf8');
if (split) {
    route = route
        .replace("from '../lib/auth.js'", "from '../../common/auth.js'")
        .replace(/^import Config from '\.\.\/lib\/config\.js';$/m, "import type Config from '../config.js';");
}
writeFileSync(routeDest, route);

const gates = [
    ['web lint', web, ['run', 'lint']],
    ['web vue-tsc', web, ['run', 'check']],
];
if (existsSync(join(cloudtak, 'api', 'node_modules'))) gates.push(['api tsc', join(cloudtak, 'api'), ['exec', 'tsc', '--', '--noEmit']]);
else console.log('(api/node_modules missing — skipping the server-route type check)');

let failed = false;
try {
    for (const [label, cwd, args] of gates) {
        console.log(`\n=== ${label} ===`);
        const run = spawnSync('npm', args, { cwd, stdio: 'inherit', shell: process.platform === 'win32' });
        if (run.status !== 0) {
            console.error(`✗ ${label} failed`);
            failed = true;
        }
    }
} finally {
    rmSync(pluginDest, { recursive: true, force: true });
    rmSync(routeDest, { force: true });
}
console.log(failed ? '\n✗ CloudTAK would refuse to build with this plugin.' : `\n✓ Passes CloudTAK ${version}'s build gates.`);
process.exit(failed ? 1 : 0);
