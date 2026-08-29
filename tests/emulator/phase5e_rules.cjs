/* Actual Firebase Lite clients against named Firestore emulator databases. */
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const NodeModule = require("node:module");
const { createRequire } = require("node:module");
const repo = path.resolve(__dirname, "../..");
const emulatorHost = process.env.FIRESTORE_EMULATOR_HOST || "";
if (!(emulatorHost.startsWith("127.0.0.1:") || emulatorHost.startsWith("localhost:"))) {
  console.error("FIRESTORE_EMULATOR_HOST must be a loopback host; refusing non-emulator execution");
  process.exit(1);
}
const requireUi = createRequire(path.join(repo, "ui/approval/package.json"));
const { initializeApp, deleteApp } = requireUi("firebase/app");
const { getFirestore, connectFirestoreEmulator, collection, query, getDocs, doc, getDoc, setDoc, deleteDoc, writeBatch, Timestamp } = requireUi("firebase/firestore/lite");
const { buildSync } = requireUi("esbuild");
const executorBundle = buildSync({
  absWorkingDir: repo,
  entryPoints: [path.join(repo, "tests/emulator/phase5e_executor_entry.ts")],
  bundle: true,
  format: "cjs",
  platform: "node",
  external: ["firebase/*", "canonicalize"],
  write: false,
}).outputFiles[0].text;
const executorModule = new NodeModule(path.join(repo, "tests/emulator/phase5e_executor_entry.ts"));
executorModule.filename = path.join(repo, "tests/emulator/phase5e_executor_entry.ts");
executorModule.paths = [path.join(repo, "ui/approval/node_modules"), ...NodeModule._nodeModulePaths(repo)];
executorModule._compile(executorBundle, executorModule.filename);
const { executeLiteInstruction } = executorModule.exports;

const fixturePath = path.join(repo, ".phase5e-fixtures.json");
const pythonCandidates = process.env.PYTHON
  ? [process.env.PYTHON]
  : process.platform === "win32"
    ? [path.join(repo, ".venv", "Scripts", "python.exe"), "python"]
    : [path.join(repo, ".venv", "bin", "python"), "python3", "python"];
let generated;
let pythonExecutable;
for (const executable of pythonCandidates) {
  generated = spawnSync(executable, [path.join(repo, "tests/emulator/generate_phase5e_fixtures.py"), fixturePath], { cwd: repo, env: { ...process.env, PYTHONPATH: path.join(repo, "src") }, encoding: "utf8" });
  if (!generated.error) { pythonExecutable = executable; break; }
}
if (!generated || generated.error || generated.status !== 0) {
  console.error((generated && generated.stderr) || "", generated && generated.error ? generated.error.message : "");
  process.exit(1);
}
const seeded = spawnSync(pythonExecutable, [path.join(repo, "tests/emulator/seed_phase5e.py"), fixturePath], { cwd: repo, env: { ...process.env, PYTHONPATH: path.join(repo, "src") }, encoding: "utf8" });
if (seeded.error || seeded.status !== 0) {
  console.error((seeded.stderr || seeded.stdout || ""), seeded.error ? seeded.error.message : "");
  process.exit(1);
}
const fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
const project = fixture.config.project_id;
const uid = "firebase-1";
const subject = "google-1";
const mockUserToken = { sub: uid, firebase: { sign_in_provider: "google.com", identities: { "google.com": [subject] } } };

function clone(value) { return JSON.parse(JSON.stringify(value)); }
function native(value) { return new Timestamp(value.seconds, value.nanoseconds); }
function sdkData(data) {
  const value = clone(data);
  for (const key of ["expires_at_ts", "approved_at_ts"]) if (value[key]) value[key] = native(value[key]);
  if (value.approval) for (const key of ["expires_at_ts", "approved_at_ts"]) if (value.approval[key]) value.approval[key] = native(value.approval[key]);
  return value;
}
function firebasePath(database, p) { return doc(database, ...p.split("/")); }
function assertNativeMirror(value, expected, label) {
  if (!value || value.seconds !== expected.seconds || value.nanoseconds !== expected.nanoseconds)
    throw new Error(`native timestamp precision changed after SDK serialization: ${label}`);
}
function assertNestedTimestamp(value, expected, label) {
  if (!value || value.type !== expected.type || value.seconds !== expected.seconds || value.nanoseconds !== expected.nanoseconds)
    throw new Error(`nested timestamp fixture changed after SDK serialization: ${label}`);
}
function productionAdapter(database, databaseId) {
  return {
    databaseId,
    writeBatch: () => writeBatch(database),
    doc: (...parts) => doc(database, ...parts),
    getDoc: (reference) => getDoc(reference),
  };
}
async function denied(operation, label) {
  try { await operation(); throw new Error(`${label}: operation unexpectedly succeeded`); }
  catch (error) { if (error.message.includes("unexpectedly succeeded")) throw error; if (error.code !== "permission-denied") throw error; }
}
async function commitInstruction(database, instruction) {
  const batch = writeBatch(database);
  for (const write of instruction.writes) batch.set(firebasePath(database, write.path), sdkData(write.data));
  await batch.commit();
}
async function readInstruction(database, instruction) {
  const result = await getDoc(firebasePath(database, instruction.path));
  if (!result.exists()) throw new Error(`missing expected document: ${instruction.path}`);
  return result.data();
}
function assertAbsent(paths) {
  const checker = path.join(repo, "tests/emulator/assert_absent_phase5e.py");
  const result = spawnSync(pythonExecutable, [checker, ...paths], { cwd: repo, env: { ...process.env, PYTHONPATH: path.join(repo, "src") }, encoding: "utf8" });
  if (result.error || result.status !== 0) throw new Error(`rejected batch left a document: ${(result.stderr || result.stdout || result.error || "unknown absence-check failure").trim()}`);
}

async function main() {
  const app = initializeApp({ apiKey: "synthetic", projectId: project }, "phase5e");
  const control = getFirestore(app, fixture.config.control_database_id);
  const runtime = getFirestore(app, fixture.config.runtime_database_id);
  connectFirestoreEmulator(control, "127.0.0.1", 19083, { mockUserToken });
  connectFirestoreEmulator(runtime, "127.0.0.1", 19083, { mockUserToken });
  try {
    await commitInstruction(control, fixture.plan);
    await commitInstruction(control, fixture.apply);
    await executeLiteInstruction(
      { control: productionAdapter(control, fixture.config.control_database_id), runtime: productionAdapter(runtime, fixture.config.runtime_database_id) },
      fixture.history,
      {
        projectId: project,
        workspaceId: fixture.config.workspace_id,
        firebaseUid: uid,
        googleSubject: subject,
        taskId: fixture.history.descriptor.task_id,
        sessionId: fixture.config.session_id,
        controlDatabaseId: fixture.config.control_database_id,
        runtimeDatabaseId: fixture.config.runtime_database_id,
        sessionExpiresAt: fixture.config.session_expires_at,
      },
    );
    console.log("PASS atomic plan/apply(two approvals)/history complete production envelopes");
    for (const instruction of [fixture.plan, fixture.apply]) {
      for (const write of instruction.writes) {
        const observed = await readInstruction(control, { path: write.path });
        if (write.data.canonical_payload && observed.canonical_payload !== write.data.canonical_payload)
          throw new Error(`canonical payload changed after SDK serialization: ${write.path}`);
        if (write.data.plan?.nested_ts)
          assertNestedTimestamp(observed.plan.nested_ts, write.data.plan.nested_ts, write.path);
        if (write.data.changeset?.changes?.[0]?.context?.nested_ts)
          assertNestedTimestamp(observed.changeset.changes[0].context.nested_ts, write.data.changeset.changes[0].context.nested_ts, write.path);
        if (write.data.expires_at_ts)
          assertNativeMirror(observed.expires_at_ts, write.data.expires_at_ts, write.path);
      }
    }
    console.log("PASS exact control get reads");
    const manifestPath = `projects/${project}/workspaces/${fixture.config.workspace_id}/users/${uid}/tasks/${fixture.manifest.task_id}/manifests/latest`;
    const resultPath = `projects/${project}/workspaces/${fixture.config.workspace_id}/users/${uid}/tasks/${fixture.manifest.task_id}/results/${fixture.result_envelope.result_id}`;
    const manifest = await getDoc(doc(runtime, ...manifestPath.split("/")));
    const result = await getDoc(doc(runtime, ...resultPath.split("/")));
    if (!manifest.exists() || !result.exists()) throw new Error("runtime owner reads were denied");
    const observedManifest = manifest.data();
    const observedResult = result.data();
    if (observedManifest.canonical_payload !== undefined)
      throw new Error("manifest unexpectedly exposed canonical payload");
    assertNativeMirror(observedManifest.expires_at_ts, fixture.manifest.expires_at_ts, "runtime manifest");
    if (observedResult.canonical_payload !== fixture.result_envelope.canonical_payload)
      throw new Error("result canonical payload changed after SDK serialization");
    assertNativeMirror(observedResult.expires_at_ts, fixture.result_envelope.expires_at_ts, "runtime result");
    assertNestedTimestamp(observedResult.payload.events[0].details.nested_ts, fixture.result_envelope.payload.events[0].details.nested_ts, "runtime result event");
    console.log("PASS owner manifest/result exact get reads");

    const tamperedChangesetCanonical = clone(fixture.negative_apply);
    tamperedChangesetCanonical.writes[0].data.changeset_canonical = "{}";
    await denied(() => commitInstruction(control, tamperedChangesetCanonical), "tampered changeset canonical");
    assertAbsent(tamperedChangesetCanonical.writes.map((write) => write.path));
    const tamperedChangesetHash = clone(fixture.negative_apply);
    tamperedChangesetHash.writes[0].data.changeset_hash = "0".repeat(64);
    await denied(() => commitInstruction(control, tamperedChangesetHash), "tampered changeset hash");
    assertAbsent(tamperedChangesetHash.writes.map((write) => write.path));
    const missingExactApproval = clone(fixture.negative_apply);
    missingExactApproval.writes = missingExactApproval.writes.slice(0, 2);
    await denied(() => commitInstruction(control, missingExactApproval), "missing exact apply approval");
    assertAbsent(missingExactApproval.writes.map((write) => write.path));
    const duplicateApprovalType = clone(fixture.negative_apply);
    duplicateApprovalType.writes[2].data.approval_type = "upload_run";
    duplicateApprovalType.writes[2].data.bound_digest_kind = "task_request";
    duplicateApprovalType.writes[2].data.change_hash = duplicateApprovalType.writes[0].data.request_hash;
    await denied(() => commitInstruction(control, duplicateApprovalType), "duplicate apply approval type");
    assertAbsent(duplicateApprovalType.writes.map((write) => write.path));
    console.log("PASS apply ChangeSet hash, required exact approval, and duplicate type negatives");

    const futureHistoryApproval = clone(fixture.negative_history);
    futureHistoryApproval.writes[0].data.approval.approved_at_ts = {
      type: "firestore/timestamp/1.0", seconds: 4102444800, nanoseconds: 0,
    };
    await denied(() => commitInstruction(control, futureHistoryApproval), "future history approval timestamp");
    assertAbsent(futureHistoryApproval.writes.map((write) => write.path));
    const alteredHistoryScope = clone(fixture.negative_history);
    alteredHistoryScope.writes[0].data.approval.action_scope.event_ids = ["wrong-event"];
    await denied(() => commitInstruction(control, alteredHistoryScope), "history approval event scope");
    assertAbsent(alteredHistoryScope.writes.map((write) => write.path));
    const alteredHistoryExpiryIso = clone(fixture.negative_history);
    alteredHistoryExpiryIso.writes[0].data.approval.expires_at = "2099-01-01T00:00:00+00:00";
    await denied(() => commitInstruction(control, alteredHistoryExpiryIso), "history approval ISO expiry");
    assertAbsent(alteredHistoryExpiryIso.writes.map((write) => write.path));
    console.log("PASS history native approval, ISO expiry, and event scope negatives");

    const missingApproval = clone(fixture.negative_plans[0]);
    missingApproval.writes = [missingApproval.writes[0]];
    await denied(() => commitInstruction(control, missingApproval), "missing approval atomic batch");
    assertAbsent([missingApproval.writes[0].path]);
    const alteredApproval = clone(fixture.negative_plans[1]);
    alteredApproval.writes[1].data.action_scope = { altered: true };
    await denied(() => commitInstruction(control, alteredApproval), "altered approval");
    assertAbsent(alteredApproval.writes.map((write) => write.path));
    const tamperedRequest = clone(fixture.negative_plans[2]);
    tamperedRequest.writes[0].data.canonical_payload = "{}";
    await denied(() => commitInstruction(control, tamperedRequest), "tampered request canonical payload");
    assertAbsent(tamperedRequest.writes.map((write) => write.path));
    const approvalExpiryMismatch = clone(fixture.negative_plans[3]);
    const approval = approvalExpiryMismatch.writes[1].data;
    approval.expires_at_ts.seconds += 3600;
    await denied(() => commitInstruction(control, approvalExpiryMismatch), "approval expiry mismatch");
    assertAbsent(approvalExpiryMismatch.writes.map((write) => write.path));
    const sessionMismatch = clone(fixture.negative_plans[0]);
    sessionMismatch.writes[1].data.session_id = "session-mismatch";
    await denied(() => commitInstruction(control, sessionMismatch), "approval session mismatch");
    assertAbsent(sessionMismatch.writes.map((write) => write.path));
    const projectMismatch = clone(fixture.negative_plans[2]);
    projectMismatch.writes[1].data.project_id = "demo-other-project";
    await denied(() => commitInstruction(control, projectMismatch), "approval project mismatch");
    assertAbsent(projectMismatch.writes.map((write) => write.path));
    const workspaceMismatch = clone(fixture.negative_plans[3]);
    workspaceMismatch.writes[1].data.workspace_id = "workspace-other";
    await denied(() => commitInstruction(control, workspaceMismatch), "approval workspace mismatch");
    assertAbsent(workspaceMismatch.writes.map((write) => write.path));
    const uidMismatch = clone(fixture.negative_plans[1]);
    uidMismatch.writes[1].data.firebase_uid = "firebase-other";
    await denied(() => commitInstruction(control, uidMismatch), "approval Firebase UID mismatch");
    assertAbsent(uidMismatch.writes.map((write) => write.path));
    const oversizedRequest = clone(fixture.negative_plans[1]);
    oversizedRequest.writes[0].data.content = "x".repeat(100001);
    await denied(() => commitInstruction(control, oversizedRequest), "oversized request metadata");
    assertAbsent(oversizedRequest.writes.map((write) => write.path));
    const expired = clone(fixture.negative_plans[0]);
    const past = { type: "firestore/timestamp/1.0", seconds: 1, nanoseconds: 0 };
    expired.writes.forEach((write) => { write.data.expires_at_ts = past; });
    await denied(() => commitInstruction(control, expired), "expired request");
    assertAbsent(expired.writes.map((write) => write.path));
    const wrongUserApp = initializeApp({ apiKey: "synthetic", projectId: project }, "wrong-user");
    const wrongControl = getFirestore(wrongUserApp, fixture.config.control_database_id);
    connectFirestoreEmulator(wrongControl, "127.0.0.1", 19083, { mockUserToken: { sub: "other", firebase: { sign_in_provider: "google.com", identities: { "google.com": ["other"] } } } });
    await denied(() => commitInstruction(wrongControl, fixture.negative_plans[3]), "wrong Google sub/Firebase UID");
    assertAbsent(fixture.negative_plans[3].writes.map((write) => write.path));
    await deleteApp(wrongUserApp);
    console.log("PASS missing/tampered/expired/mismatched approval and wrong identity negatives");

    const orphan = clone(fixture.negative_plans[0].writes[1]);
    await denied(() => commitInstruction(control, { writes: [orphan] }), "orphan approval");
    assertAbsent([orphan.path]);
    const runtimeEvent = `projects/${project}/workspaces/${fixture.config.workspace_id}/users/${uid}/tasks/${fixture.manifest.task_id}/events/event-1`;
    await denied(() => getDoc(doc(runtime, ...runtimeEvent.split("/"))), "raw event read");
    console.log("PASS orphan approval and raw event denial");

    const positiveRequestPath = fixture.plan.writes[0].path;
    await denied(() => setDoc(firebasePath(control, positiveRequestPath), sdkData(fixture.plan.writes[0].data)), "control request update");
    await denied(() => deleteDoc(firebasePath(control, positiveRequestPath)), "control request delete");
    const positiveApprovalPath = fixture.plan.writes[1].path;
    await denied(() => setDoc(firebasePath(control, positiveApprovalPath), sdkData(fixture.plan.writes[1].data)), "control approval update");
    await denied(() => deleteDoc(firebasePath(control, positiveApprovalPath)), "control approval delete");
    await denied(() => getDocs(query(collection(control, ...positiveRequestPath.split("/"), "approvals"))), "control approval list");
    console.log("PASS control create-only and list-denial surface");

    const expiredTask = `projects/${project}/workspaces/${fixture.config.workspace_id}/users/${uid}/tasks/task-expired/manifests/latest`;
    await denied(() => getDoc(doc(runtime, ...expiredTask.split("/"))), "expired manifest");
    const malformedScopeTask = `projects/${project}/workspaces/${fixture.config.workspace_id}/users/${uid}/tasks/task-malformed-scope/manifests/latest`;
    await denied(() => getDoc(doc(runtime, ...malformedScopeTask.split("/"))), "malformed manifest scope");
    const oversizedScopeTask = `projects/${project}/workspaces/${fixture.config.workspace_id}/users/${uid}/tasks/task-oversized-scope/manifests/latest`;
    await denied(() => getDoc(doc(runtime, ...oversizedScopeTask.split("/"))), "oversized manifest scope");
    const scope20Task = `projects/${project}/workspaces/${fixture.config.workspace_id}/users/${uid}/tasks/task-scope-20/manifests/latest`;
    const scope20 = await getDoc(doc(runtime, ...scope20Task.split("/")));
    if (!scope20.exists() || scope20.data().scope.length !== 20)
      throw new Error("20-entry bounded runtime scope was denied or truncated");
    const malformedPayloadTask = `projects/${project}/workspaces/${fixture.config.workspace_id}/users/${uid}/tasks/task-malformed-payload/results/${fixture.result_envelope.result_id}`;
    await denied(() => getDoc(doc(runtime, ...malformedPayloadTask.split("/"))), "malformed result payload");
    const malformedKindTask = `projects/${project}/workspaces/${fixture.config.workspace_id}/users/${uid}/tasks/task-malformed-kind/results/${fixture.result_envelope.result_id}`;
    await denied(() => getDoc(doc(runtime, ...malformedKindTask.split("/"))), "malformed result kind payload");
    const malformedResult = `projects/${project}/workspaces/${fixture.config.workspace_id}/users/${uid}/tasks/${fixture.manifest.task_id}/results/${"f".repeat(64)}`;
    await denied(() => getDoc(doc(runtime, ...malformedResult.split("/"))), "digest mismatch result");
    const unknown = getFirestore(app, "unknown");
    connectFirestoreEmulator(unknown, "127.0.0.1", 19083, { mockUserToken });
    await denied(() => getDoc(doc(unknown, "projects", project, "workspaces", "workspace-1", "members", uid)), "unknown database");
    const defaultDatabase = getFirestore(app);
    connectFirestoreEmulator(defaultDatabase, "127.0.0.1", 19083, { mockUserToken });
    await denied(() => getDoc(doc(defaultDatabase, "projects", project, "workspaces", "workspace-1", "members", uid)), "default database");
    const expiredMemberApp = initializeApp({ apiKey: "synthetic", projectId: project }, "expired-member");
    const expiredMemberControl = getFirestore(expiredMemberApp, fixture.config.control_database_id);
    connectFirestoreEmulator(expiredMemberControl, "127.0.0.1", 19083, { mockUserToken: { sub: "firebase-expired", firebase: { sign_in_provider: "google.com", identities: { "google.com": ["google-expired"] } } } });
    await denied(() => getDoc(doc(expiredMemberControl, "projects", project, "workspaces", fixture.config.workspace_id, "members", "firebase-expired")), "expired membership");
    await deleteApp(expiredMemberApp);
    const namespaceMemberApp = initializeApp({ apiKey: "synthetic", projectId: project }, "namespace-member");
    const namespaceMemberControl = getFirestore(namespaceMemberApp, fixture.config.control_database_id);
    connectFirestoreEmulator(namespaceMemberControl, "127.0.0.1", 19083, { mockUserToken: { sub: "firebase-namespace", firebase: { sign_in_provider: "google.com", identities: { "google.com": ["google-namespace"] } } } });
    await denied(() => getDoc(doc(namespaceMemberControl, "projects", project, "workspaces", fixture.config.workspace_id, "members", "firebase-namespace")), "membership namespace mismatch");
    await deleteApp(namespaceMemberApp);
    console.log("PASS expired/malformed runtime metadata and unknown/default database negatives");

    await denied(() => setDoc(doc(runtime, ...resultPath.split("/")), sdkData(fixture.result_envelope)), "runtime write");
    await denied(() => deleteDoc(doc(runtime, ...resultPath.split("/"))), "runtime delete");
    console.log("PASS zero client runtime-write surface");
  } finally { await deleteApp(app); fs.rmSync(fixturePath, { force: true }); }
}
main().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
