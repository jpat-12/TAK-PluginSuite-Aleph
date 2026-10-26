#!/usr/bin/env node
// Run CloudTAK's own build gates against this plugin, the way its Docker build does
// (`npm run lint && npm run check` in api/web), without installing anything into a real deploy.
//
//   CLOUDTAK_DIR=/path/to/CloudTAK node cloudtak/check-in-cloudtak.mjs
//
// Copies plugin/ → $CLOUDTAK_DIR/api/web/plugins/aleph and server/ → api/routes/, runs the
// gates, then removes the copies again. The checkout needs `npm install` done in api/web.
import { cpSync, existsSync, rmSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const cloudtak = process.env.CLOUDTAK_DIR;
if (!cloudtak || !existsSync(join(cloudtak, 'api', 'web', 'plugin.ts'))) {
    console.error('Set CLOUDTAK_DIR to a CloudTAK checkout (with npm install done in api/web).');
    process.exit(2);
}
const web = join(cloudtak, 'api', 'web');
const pluginDest = join(web, 'plugins', 'aleph');
const routeDest = join(cloudtak, 'api', 'routes', 'plugin-aleph.ts');

rmSync(pluginDest, { recursive: true, force: true });
cpSync(join(here, 'plugin'), pluginDest, {
    recursive: true,
    filter: (src) => !/node_modules|package(-lock)?\.json$/.test(src),
});
cpSync(join(here, 'server', 'plugin-aleph.ts'), routeDest);

let failed = false;
try {
    for (const [label, args] of [['lint', ['run', 'lint']], ['check', ['run', 'check']]]) {
        console.log(`\n=== CloudTAK web: npm ${args.join(' ')} ===`);
        const run = spawnSync('npm', args, { cwd: web, stdio: 'inherit', shell: process.platform === 'win32' });
        if (run.status !== 0) {
            console.error(`✗ ${label} failed`);
            failed = true;
        }
    }
} finally {
    rmSync(pluginDest, { recursive: true, force: true });
    rmSync(routeDest, { force: true });
}
console.log(failed ? '\n✗ CloudTAK would refuse to build with this plugin.' : '\n✓ Passes CloudTAK\'s lint + type check.');
process.exit(failed ? 1 : 0);
