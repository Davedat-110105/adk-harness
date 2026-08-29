// No remote calls: actual UI + loopback host, fake Auth and Firestore adapters.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { webcrypto } = require('node:crypto');
const root = path.resolve(__dirname, '../../../..');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const { JSDOM } = require(path.join(root, 'ui/approval/node_modules/jsdom'));
const esbuild = require(path.join(root, 'ui/approval/node_modules/esbuild'));
const { Timestamp } = require(path.join(root, 'ui/approval/node_modules/firebase/firestore/lite'));
const dom = new JSDOM(fs.readFileSync(path.join(root, 'ui/approval/index.html'), 'utf8'), { url: input.origin + '/approval#capability=' + input.capability, runScripts: 'outside-only' });
const w = dom.window;
Object.defineProperty(w, 'crypto', { value: webcrypto });
w.TextEncoder = TextEncoder;
w.structuredClone = structuredClone;
const operations = [];
const reconciliationTargets = [];
const failures = [];
const sdkCalls = [];
const stores = { control: new Map(), runtime: new Map() };
const previewSignout = input.mode.startsWith('preview_signout_');
const recovery = input.mode.endsWith('_unknown') || input.mode.startsWith('history_unknown') || input.mode === 'history_metadata_unknown' || input.mode === 'history_two_handles' || input.mode.startsWith('history_signout') || input.mode.startsWith('history_consent_response');
let failOnce = recovery;
let commitsToFail = input.mode === 'history_two_handles' ? 2 : 0;
let releaseCommit;
let pauseNextToken = false;
let releaseToken;
let consentReleased;
let releaseConsent;
let consentDelayUsed = false;
let recoveryAckReleased = false;
let releaseRecoveryAck;
let recoveryAckDelayUsed = false;
let previewReleased = false;
let releasePreview;
let previewDelayUsed = false;
let previewFetches = 0;
let resultAcks = 0;
let resultFailureUsed = false;
let consentFetches = 0;
let tokenCalls = 0;
const user = { uid: 'firebase-1', getIdToken: async () => {
  tokenCalls += 1;
  if (pauseNextToken) {
    pauseNextToken = false;
    await new Promise(resolve => { releaseToken = resolve; });
  }
  return 'synthetic-test-only';
} };
const auth = { currentUser: null };
const observers = [];
function native(value) {
  const result = structuredClone(value);
  for (const slot of [result, result.approval].filter(Boolean)) for (const key of ['expires_at_ts', 'approved_at_ts', 'created_at_ts']) {
    if (slot[key]?.type === 'firestore/timestamp/1.0') slot[key] = new Timestamp(slot[key].seconds, slot[key].nanoseconds);
  }
  return result;
}
const prefix = `projects/${input.manifest.project_id}/workspaces/${input.manifest.workspace_id}/users/firebase-1/tasks/${input.manifest.task_id}`;
stores.runtime.set(prefix + '/manifests/latest', native(input.manifest));
stores.runtime.set(prefix + '/results/' + input.manifest.result_id, native(input.envelope));
w.__sdk = {
  Timestamp, initializeApp: () => ({}), getAuth: () => auth, GoogleAuthProvider: class {}, inMemoryPersistence: {}, setPersistence: async () => {},
  onAuthStateChanged: (_auth, callback) => { observers.push(callback); callback(auth.currentUser); return () => {}; },
  signInWithPopup: async () => { auth.currentUser = user; observers.forEach(fn => fn(user)); return { user }; },
  signOut: async () => { auth.currentUser = null; observers.forEach(fn => fn(null)); },
  getFirestore: (_app, id) => ({ id }), doc: (db, ...parts) => ({ db: db.id, path: parts.join('/') }),
  writeBatch: db => { const writes = []; return { set: (ref, value) => writes.push([ref, value]), commit: async () => {
    sdkCalls.push('commit');
    for (const [ref, value] of writes) stores[db.id].set(ref.path, value);
    if (commitsToFail > 0) { commitsToFail -= 1; throw new Error('synthetic unknown commit response'); }
    if (failOnce && input.mode.startsWith('history_signout')) {
      failOnce = false;
      await new Promise(resolve => { releaseCommit = resolve; });
      if (input.mode !== 'history_signout_success') throw new Error('synthetic response lost across signout');
    }
    if (failOnce && (input.mode.startsWith('history_unknown') || input.mode === 'history_metadata_unknown')) { failOnce = false; throw new Error('synthetic lost commit response'); }
  } }; },
  getDoc: async ref => {
    sdkCalls.push('getDoc');
    if (input.mode === 'download_ack_withdraw' && ref.path.includes('/results/')) pauseNextToken = true;
    if (failOnce && input.mode === 'download_unknown' && ref.path.includes('/results/')) { failOnce = false; throw new Error('synthetic lost read response'); }
    if (input.mode === 'history_two_handles' && ref.path.includes('/results/') && !resultFailureUsed) { resultFailureUsed = true; throw new Error('synthetic second unknown read response'); }
    if (input.mode === 'history_metadata_unknown' && ref.path.includes('/manifests/')) throw new Error('synthetic metadata read unavailable');
    const data = stores[ref.db].get(ref.path);
    return { exists: () => data !== undefined, data: () => data };
  },
};
w.fetch = async (url, options) => {
  const target = new URL(url, input.origin);
  assert.equal(target.origin, input.origin, 'probe refuses non-loopback destination');
  if (target.pathname.endsWith('/consent')) consentFetches += 1;
  if (target.pathname.endsWith('/preview') && options?.body) {
    const previewBody = JSON.parse(options.body);
    if (previewBody.kind === 'reconciliation') reconciliationTargets.push(previewBody.operationId);
  }
  if (target.pathname.endsWith('/ack') && options?.body && JSON.parse(options.body).result) resultAcks += 1;
  const response = await fetch(target, { ...options, headers: { ...options?.headers, Origin: input.origin } });
  const body = await response.clone().json();
  if (!response.ok) failures.push(`${target.pathname}: ${response.status} ${JSON.stringify(body)}`);
  if (previewSignout && target.pathname.endsWith('/preview')) {
    previewFetches += 1;
    if (!previewDelayUsed) {
      previewDelayUsed = true;
      previewReleased = true;
      await new Promise(resolve => { releasePreview = resolve; });
    }
    if (input.mode.endsWith('_failure') && previewFetches > 1)
      return new Response(JSON.stringify({ detail: 'synthetic replacement preview failure' }), { status: 503, headers: { 'Content-Type': 'application/json' } });
  }
  if (target.pathname.endsWith('/consent') && body.instruction) {
    operations.push(body.operation_id);
    if (input.mode.startsWith('history_consent_response') && !consentDelayUsed) {
      consentDelayUsed = true;
      consentReleased = true;
      await new Promise(resolve => { releaseConsent = resolve; });
    }
    if (input.mode === 'history_consent_lost') throw new Error('synthetic unavailable consent response after dispatch');
  }
  if ((input.mode === 'history_signout' || input.mode === 'history_signout_replace') && target.pathname.endsWith('/ack') && options?.body && JSON.parse(options.body).status === 'unknown' && !recoveryAckDelayUsed) {
    recoveryAckDelayUsed = true;
    recoveryAckReleased = true;
    await new Promise(resolve => { releaseRecoveryAck = resolve; });
  }
  return response;
};
async function until(predicate, label) {
  for (let i = 0; i < 250; i++) { if (predicate()) return; await new Promise(resolve => setTimeout(resolve, 10)); }
  throw new Error(`${label}; UI=${w.document.querySelector('#sync-details').textContent} / ${w.document.querySelector('#download-details').textContent}; errors=${failures.join(',')}`);
}
function click(id) { const element = w.document.querySelector(id); assert(!element.disabled && !element.hidden, `control unavailable: ${id}`); element.click(); }
function check(id) { const element = w.document.querySelector(id); element.checked = true; element.dispatchEvent(new w.Event('change', { bubbles: true })); }
async function run() {
  const moduleText = 'const s=window.__sdk; export const {initializeApp,getAuth,GoogleAuthProvider,inMemoryPersistence,onAuthStateChanged,setPersistence,signInWithPopup,signOut,doc,getDoc,getFirestore,writeBatch,Timestamp}=s;';
  const bundle = await esbuild.build({ entryPoints: [path.join(root, 'ui/approval/src/main.ts')], bundle: true, write: false, format: 'iife', logLevel: 'silent', plugins: [{ name: 'offline-firebase', setup(build) {
    build.onResolve({ filter: /^firebase\/(app|auth|firestore\/lite)$/ }, args => ({ path: args.path, namespace: 'offline' }));
    build.onLoad({ filter: /.*/, namespace: 'offline' }, () => ({ contents: moduleText, loader: 'js' }));
  } }] });
  w.eval(bundle.outputFiles[0].text);
  await until(() => w.document.querySelector('#app').dataset.localGoogleSub, 'bootstrap');
  click('#login');
  await until(() => !w.document.querySelector('#manual-sync').hidden, 'login');
  assert.equal(sdkCalls.length, 0, 'login must not transfer task data');
  if (previewSignout) {
    const kind = input.mode.includes('_history') ? 'history' : input.mode.includes('_task') ? 'task' : 'manifest';
    const previewId = kind === 'history' ? '#sync-preview' : kind === 'task' ? '#task-preview' : '#manifest-preview';
    const actionId = kind === 'history' ? '#sync-upload' : kind === 'task' ? '#task-record' : '#manifest-read';
    click(previewId);
    await until(() => previewReleased, `${kind} preview dispatch`);
    click('#logout');
    releasePreview();
    await new Promise(resolve => setTimeout(resolve, 25));
    click('#login');
    await until(() => !w.document.querySelector('#manual-sync').hidden, `${kind} preview return login`);
    assert(!w.document.querySelector(previewId).disabled, `${kind} preview remained disabled after return`);
    click(previewId);
    if (input.mode.endsWith('_failure')) {
      await until(() => w.document.querySelector('#sync-details').textContent.includes('rejected') || w.document.querySelector('#download-details').textContent.includes('rejected'), `${kind} replacement failure`);
      assert(w.document.querySelector(actionId).disabled, `${kind} old consent/action survived replacement failure`);
      assert(!w.document.querySelector(kind === 'manifest' ? '#manifest-consent' : kind === 'task' ? '#task-consent' : '#sync-consent').checked, `${kind} old consent survived replacement failure`);
    } else {
      await until(() => !w.document.querySelector(actionId).disabled, `${kind} replacement preview`);
    }
  } else if (input.mode === 'plan' || input.mode === 'apply') {
    click('#task-preview'); await until(() => !w.document.querySelector('#task-record').disabled, 'task preview');
    assert.equal(sdkCalls.length, 0);
    check('#task-consent'); if (input.mode === 'apply') check('#apply-consent');
    click('#task-record'); await until(() => w.document.querySelector('#sync-details').textContent.includes('atomically'), 'task ack');
  } else if (input.mode.startsWith('history')) {
    click('#sync-preview'); await until(() => !w.document.querySelector('#sync-upload').disabled, 'history preview');
    assert.equal(sdkCalls.length, 0);
    check('#sync-consent');
    if (input.mode === 'history_consent_withdraw') pauseNextToken = true;
    click('#sync-upload');
    if (input.mode === 'history_consent_withdraw') {
      await until(() => releaseToken, 'history consent token boundary');
      const checkbox = w.document.querySelector('#sync-consent');
      checkbox.checked = false;
      checkbox.dispatchEvent(new w.Event('change', { bubbles: true }));
      releaseToken();
      await new Promise(resolve => setTimeout(resolve, 100));
      assert.equal(operations.length, 0, 'consent request sent after withdrawal');
      assert.equal(sdkCalls.length, 0, 'SDK call sent after withdrawal');
    } else if (input.mode === 'history_consent_lost') {
      await new Promise(resolve => setTimeout(resolve, 50));
      assert.equal(sdkCalls.length, 0, 'SDK call sent after unavailable consent response');
      assert(w.document.querySelector('#sync-details').textContent.includes('retained as pending'), `lost response marker not visible: ${w.document.querySelector('#sync-details').textContent}`);
      const beforeReplay = consentFetches;
      click('#sync-upload');
      await new Promise(resolve => setTimeout(resolve, 25));
      assert.equal(consentFetches, beforeReplay, 'consumed consent was reissued');
      click('#logout');
      await new Promise(resolve => setTimeout(resolve, 10));
      click('#login');
      await until(() => !w.document.querySelector('#manual-sync').hidden, 'second login after lost response');
      assert(w.document.querySelector('#sync-details').textContent.includes('pending'), `lost response marker not retained after return: ${w.document.querySelector('#sync-details').textContent}`);
      assert(w.document.querySelector('#sync-reconcile').hidden, 'lost response must not become actionable reconciliation');
    } else if (input.mode.startsWith('history_consent_response')) {
      await until(() => consentReleased, 'released consent response');
      if (input.mode === 'history_consent_response_withdraw') {
        const checkbox = w.document.querySelector('#sync-consent');
        checkbox.checked = false;
        checkbox.dispatchEvent(new w.Event('change', { bubbles: true }));
        releaseConsent();
        await until(() => !w.document.querySelector('#sync-reconcile').hidden, 'same-owner unknown control');
      } else {
        click('#logout');
        releaseConsent();
        await new Promise(resolve => setTimeout(resolve, 25));
        click('#login');
        await until(() => !w.document.querySelector('#manual-sync').hidden, 'second login');
      }
    } else if (input.mode === 'history_metadata_unknown') {
      await until(() => !w.document.querySelector('#sync-reconcile').hidden, 'history recovery before metadata');
      click('#manifest-preview'); await until(() => !w.document.querySelector('#manifest-read').disabled, 'metadata preview after history recovery');
      check('#manifest-consent'); click('#manifest-read');
      await until(() => w.document.querySelector('#download-details').textContent.includes('Manifest read failed') || w.document.querySelector('#download-details').textContent.includes('synthetic metadata read unavailable'), 'metadata read failure');
      assert(!w.document.querySelector('#sync-reconcile').hidden, 'metadata failure hid original recovery target');
    } else if (input.mode === 'history_two_handles') {
      await until(() => !w.document.querySelector('#sync-reconcile').hidden, 'first confirmed recovery');
      click('#manifest-preview'); await until(() => !w.document.querySelector('#manifest-read').disabled, 'metadata preview for second operation');
      check('#manifest-consent'); click('#manifest-read');
      await until(() => !w.document.querySelector('#result-read').disabled, 'metadata read for second operation');
      click('#result-read'); await until(() => !w.document.querySelector('#result-download').disabled, 'result preview for second operation');
      check('#result-consent'); click('#result-download');
      await until(() => !w.document.querySelector('#sync-reconcile').hidden, 'second confirmed recovery');
      await new Promise(resolve => setTimeout(resolve, 100));
      click('#sync-reconcile'); await until(() => !w.document.querySelector('#reconcile-read').disabled, 'first exact recovery preview');
      check('#reconcile-consent'); click('#reconcile-read');
      await until(() => /Reconciliation status: (acknowledged|reconciled)/.test(w.document.querySelector('#sync-details').textContent), 'first exact recovery');
      await until(() => !w.document.querySelector('#sync-reconcile').hidden, 'next exact recovery selection');
    } else if (!recovery) await until(() => w.document.querySelector('#sync-details').textContent.includes('recorded'), 'history ack');
  } else {
    click('#manifest-preview'); await until(() => !w.document.querySelector('#manifest-read').disabled, 'manifest preview');
    assert.equal(sdkCalls.length, 0);
    check('#manifest-consent'); click('#manifest-read');
    await until(() => !w.document.querySelector('#result-read').disabled, 'manifest ack');
    click('#result-read'); await until(() => !w.document.querySelector('#result-download').disabled, 'result preview');
    check('#result-consent'); click('#result-download');
    if (!recovery && input.mode !== 'download_ack_withdraw') await until(() => w.document.querySelector('#download-details').textContent.includes('imported'), 'result ack');
  }
  if (input.mode === 'download_ack_withdraw') {
    await until(() => releaseToken, 'result ack token boundary');
    const checkbox = w.document.querySelector('#result-consent');
    checkbox.checked = false;
    checkbox.dispatchEvent(new w.Event('change', { bubbles: true }));
    releaseToken();
    await new Promise(resolve => setTimeout(resolve, 100));
    assert.equal(resultAcks, 0, 'result/import ack sent after consent withdrawal');
  }
  if (input.mode.startsWith('history_signout')) {
    await until(() => releaseCommit, 'commit dispatch');
    click('#logout');
    releaseCommit();
    await new Promise(resolve => setTimeout(resolve, 25));
    assert(w.document.querySelector('#sync-reconcile').hidden, 'old handle exposed after signout');
    click('#login');
    if (input.mode === 'history_signout' || input.mode === 'history_signout_replace') {
      await until(() => recoveryAckReleased, 'returning-owner unknown callback');
      if (input.mode === 'history_signout_replace') {
        const replacement = { uid: 'firebase-2', getIdToken: async () => 'replacement-token' };
        auth.currentUser = replacement;
        observers.forEach(fn => fn(replacement));
      } else {
        click('#logout');
      }
      releaseRecoveryAck();
      await new Promise(resolve => setTimeout(resolve, 25));
      assert(w.document.querySelector('#manual-sync').hidden, 'stale recovery callback restored old UI');
    } else {
      await until(() => !w.document.querySelector('#manual-sync').hidden, 'second login');
    }
  }
  if (input.mode === 'history_unknown_relogin') {
    await until(() => !w.document.querySelector('#sync-reconcile').hidden, 'confirmed unknown control');
    click('#logout');
    await new Promise(resolve => setTimeout(resolve, 25));
    click('#login');
    await until(() => !w.document.querySelector('#manual-sync').hidden, 'confirmed unknown return login');
    await until(() => !w.document.querySelector('#sync-reconcile').hidden, 'confirmed unknown control after return');
  }
  if (input.mode.startsWith('history_consent_response')) {
    await until(() => !w.document.querySelector('#sync-reconcile').hidden, 'unknown control');
    click('#sync-reconcile'); await until(() => !w.document.querySelector('#reconcile-read').disabled, 'reconciliation preview');
    check('#reconcile-consent'); click('#reconcile-read');
    await until(() => w.document.querySelector('#sync-details').textContent.includes('remote document is unavailable'), 'approved recovery read');
    assert.equal(sdkCalls.filter(call => call === 'commit').length, 0, 'stale consent executed a write');
  } else if (recovery && !['history_signout', 'history_signout_replace', 'history_two_handles'].includes(input.mode)) {
    await until(() => !w.document.querySelector('#sync-reconcile').hidden, 'unknown control');
    click('#sync-reconcile'); await until(() => !w.document.querySelector('#reconcile-read').disabled, 'reconciliation preview');
    check('#reconcile-consent'); click('#reconcile-read');
    await until(() => /Reconciliation status: (acknowledged|reconciled)/.test(w.document.querySelector('#sync-details').textContent), 'reconciliation ack');
  }
  assert.equal(failures.length, 0, failures.join(','));
  process.stdout.write(JSON.stringify({ operations, reconciliationTargets, sdkCalls }));
}
run().catch(error => { process.stderr.write(error.message.slice(0, 1600)); process.exitCode = 1; }).finally(() => w.close());
