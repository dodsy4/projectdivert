/**
 * Fail if demo-only code reached a production bundle.
 *
 * The demo role switcher is meant to be absent from a normal build, not merely
 * inert inside one. The difference is invisible in the source: a component that
 * returns null unless a flag is set looks identical in review to one that is
 * never imported, and both behave correctly in the browser. Only the built
 * output tells them apart, which is what this reads.
 *
 * Run against dist/ after `npm run build` with no VITE_DEMO_MODE set.
 */

import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const DIST = new URL('../dist/assets/', import.meta.url).pathname;

// Strings that must never appear in production JavaScript. CSS is not checked:
// rules for a component that is not there match nothing and cost a few bytes.
const FORBIDDEN = [
  'demo.projectdivert.test',
  'Demo mode',
  'DemoRoleSwitcher',
];

let files;
try {
  files = readdirSync(DIST).filter((name) => name.endsWith('.js'));
} catch {
  console.error(`No build found at ${DIST}. Run \`npm run build\` first.`);
  process.exit(1);
}

if (files.length === 0) {
  console.error('No JavaScript in the build output; nothing was checked.');
  process.exit(1);
}

const found = [];
for (const name of files) {
  const source = readFileSync(join(DIST, name), 'utf8');
  for (const needle of FORBIDDEN) {
    if (source.includes(needle)) found.push(`${name}: ${needle}`);
  }
}

if (found.length > 0) {
  console.error('Demo-only code is present in the production bundle:\n');
  for (const hit of found) console.error(`  ${hit}`);
  console.error(
    '\nA runtime guard inside the component is not enough -- the module is still'
    + '\nimported, so it ships. Gate the import itself, behind a build-time flag:'
    + "\n\n  const Thing = import.meta.env.VITE_DEMO_MODE"
    + "\n    ? lazy(() => import('./Thing.jsx'))"
    + '\n    : null;\n',
  );
  process.exit(1);
}

console.log(
  `Checked ${files.length} JavaScript file(s): no demo-only code in the production bundle.`,
);
