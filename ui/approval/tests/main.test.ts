import { readFileSync } from "node:fs";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const signInWithPopup = vi.fn();
const signOut = vi.fn().mockResolvedValue(undefined);
const onAuthStateChanged = vi.fn();
const getAuth = vi.fn(() => ({ currentUser: null as any }));
const firestoreMocks = vi.hoisted(() => {
  const set = vi.fn();
  const commit = vi.fn().mockResolvedValue(undefined);
  const db = { writeBatch: vi.fn(() => ({ set, commit })) };
  return { db, set, commit, getFirestore: vi.fn(() => db), doc: vi.fn((...parts: string[]) => parts.join("/")), getDoc: vi.fn() };
});
const capture = JSON.parse(readFileSync("tests/fixtures/host-flow-probe-fixtures.json", "utf8")) as any;

vi.mock("firebase/app", () => ({ initializeApp: vi.fn(() => ({})) }));
vi.mock("firebase/auth", () => ({
  getAuth,
  GoogleAuthProvider: vi.fn(),
  inMemoryPersistence: {},
  setPersistence: vi.fn().mockResolvedValue(undefined),
  signInWithPopup,
  signOut,
  onAuthStateChanged,
}));
vi.mock("firebase/firestore/lite", () => ({
  getFirestore: firestoreMocks.getFirestore,
  doc: firestoreMocks.doc,
  getDoc: firestoreMocks.getDoc,
  writeBatch: () => firestoreMocks.db.writeBatch(),
  Timestamp: class Timestamp { constructor(public seconds: number, public nanoseconds: number) {} },
}));

function dom(): void {
  document.body.innerHTML = readFileSync("index.html", "utf8");
  window.location.hash = "#capability=test-capability";
}

async function load(): Promise<void> {
  vi.resetModules();
  await import("../src/main.ts");
  await new Promise((resolve) => setTimeout(resolve, 0));
}

beforeEach(() => {
  dom();
  signInWithPopup.mockReset();
  signOut.mockClear();
  getAuth.mockReturnValue({ currentUser: null });
  firestoreMocks.getFirestore.mockClear();
  firestoreMocks.doc.mockClear();
  firestoreMocks.getDoc.mockReset();
  firestoreMocks.set.mockClear();
  firestoreMocks.commit.mockClear();
  firestoreMocks.db.writeBatch.mockClear();
});
afterEach(() => vi.useRealTimers());

test("binds Firebase identity and renders exact cloud grant details before consent", async () => {
  const user = { uid: "firebase-uid", getIdToken: vi.fn().mockResolvedValue("firebase-token") };
  getAuth.mockReturnValue({ currentUser: user });
  signInWithPopup.mockResolvedValue({ user });
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({
      googleSubject: "google-sub",
      firebaseConfig: { apiKey: "key", authDomain: "example.firebaseapp.com", projectId: "example" },
      setupOnly: false,
      cloudGrant: { challenge: "challenge", purpose: "workspace", destination: "projects/p/secrets/s", scopes: ["openid", "scope"], expiresAt: "future" },
    })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ firebaseUid: "firebase-uid", googleSubject: "google-sub" })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ status: "cloud grant stored" })));
  vi.stubGlobal("fetch", fetchMock);
  await load();
  await document.querySelector<HTMLButtonElement>("#login")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(document.querySelector("#state")!.textContent).toContain("Firebase UID is bound");
  expect(document.querySelector("#cloud-grant-details")!.textContent).toContain("projects/p/secrets/s");
  expect(document.querySelector("#cloud-grant-details")!.textContent).toContain("openid, scope");
  const checkbox = document.querySelector<HTMLInputElement>("#cloud-consent")!;
  checkbox.checked = true;
  await document.querySelector<HTMLButtonElement>("#cloud-consent-submit")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  const body = JSON.parse(fetchMock.mock.calls[2][1].body as string);
  expect(body).toMatchObject({ challenge: "challenge", consent: true, destination: "projects/p/secrets/s" });
});

test("rejects Firebase subject mismatch and signs out", async () => {
  const user = { uid: "firebase-uid", getIdToken: vi.fn().mockResolvedValue("firebase-token") };
  getAuth.mockReturnValue({ currentUser: user });
  signInWithPopup.mockResolvedValue({ user });
  vi.stubGlobal("fetch", vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ googleSubject: "google-sub", firebaseConfig: { apiKey: "key", authDomain: "example.firebaseapp.com", projectId: "example" }, setupOnly: false, cloudGrant: { challenge: "challenge", purpose: "workspace", destination: "projects/p/secrets/s", scopes: ["openid"], expiresAt: "future" } })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ firebaseUid: "firebase-uid", googleSubject: "wrong-sub" }))));
  await load();
  await document.querySelector<HTMLButtonElement>("#login")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(document.querySelector("#state")!.textContent).toContain("does not match");
  expect(signOut).toHaveBeenCalled();
});

test("renders setup only mode and posts a local confirmation without Firebase", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ googleSubject: "google-sub", firebaseConfig: null, setupOnly: true })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ status: "local setup confirmation received" })));
  vi.stubGlobal("fetch", fetchMock);
  await load();
  expect(document.querySelector<HTMLElement>("#setup-only")!.hidden).toBe(false);
  expect(document.querySelector<HTMLElement>("#setup-subject")!.textContent).toContain("google-sub");
  expect(document.querySelector<HTMLButtonElement>("#login")!.hidden).toBe(true);
  await document.querySelector<HTMLButtonElement>("#setup-confirm")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(fetchMock.mock.calls[1][0]).toBe("/api/setup-confirmation");
  expect(document.querySelector("#state")!.textContent).toContain("task actions remain disabled");
});

test("signs out the in memory Firebase session", async () => {
  const user = { uid: "firebase-uid", getIdToken: vi.fn().mockResolvedValue("firebase-token") };
  getAuth.mockReturnValue({ currentUser: user });
  signInWithPopup.mockResolvedValue({ user });
  vi.stubGlobal("fetch", vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ googleSubject: "google-sub", firebaseConfig: { apiKey: "key", authDomain: "example.firebaseapp.com", projectId: "example" }, setupOnly: false, cloudGrant: { challenge: "challenge", purpose: "workspace", destination: "projects/p/secrets/s", scopes: ["openid", "scope"], expiresAt: "future" } })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ firebaseUid: "firebase-uid", googleSubject: "google-sub" }))));
  await load();
  await document.querySelector<HTMLButtonElement>("#login")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(document.querySelector<HTMLElement>("#cloud-grant")!.hidden).toBe(false);
  expect(document.querySelector("#cloud-grant-details")!.textContent).toContain("projects/p/secrets/s");
  document.querySelector<HTMLInputElement>("#cloud-consent")!.checked = true;
  await document.querySelector<HTMLButtonElement>("#logout")!.click();
  expect(signOut).toHaveBeenCalled();
  expect(document.querySelector<HTMLElement>("#cloud-grant")!.hidden).toBe(true);
  expect(document.querySelector("#cloud-grant-details")!.textContent).toBe("");
  expect(document.querySelector<HTMLInputElement>("#cloud-consent")!.checked).toBe(false);
  expect(document.querySelector("#state")!.textContent).toContain("Signed out");
});

test("runs mounted history preview, exact consent, Lite write, and host acknowledgement", async () => {
  vi.setSystemTime(new Date(capture.clock));
  const user = { uid: "firebase-1", getIdToken: vi.fn().mockResolvedValue("firebase-token") };
  getAuth.mockReturnValue({ currentUser: user });
  signInWithPopup.mockResolvedValue({ user });
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ googleSubject: "google-1", firebaseConfig: { apiKey: "key", authDomain: "example.firebaseapp.com", projectId: "example" }, workflowConfig: capture.config, setupOnly: false, pendingHistory: capture.history_preview.records })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ firebaseUid: "firebase-1", googleSubject: "google-1" })))
    .mockResolvedValueOnce(new Response(JSON.stringify(capture.history_preview)))
    .mockResolvedValueOnce(new Response(JSON.stringify(capture.history_consent)))
    .mockResolvedValueOnce(new Response(JSON.stringify({ status: "acknowledged", operation_id: capture.history_consent.operation_id, descriptor_hash: capture.history_consent.descriptor_hash })));
  vi.stubGlobal("fetch", fetchMock);
  await load();
  await document.querySelector<HTMLButtonElement>("#login")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await document.querySelector<HTMLButtonElement>("#sync-preview")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  document.querySelector<HTMLInputElement>("#sync-consent")!.checked = true;
  await document.querySelector<HTMLButtonElement>("#sync-upload")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(fetchMock).toHaveBeenCalledTimes(5);
  expect(firestoreMocks.db.writeBatch).toHaveBeenCalledTimes(1);
  expect(firestoreMocks.doc).toHaveBeenCalledWith(firestoreMocks.db, "projects", "demo-adk-wire", "workspaces", "workspace-1", "members", "firebase-1", "exports", expect.any(String));
  expect(document.querySelector("#sync-details")!.textContent).toContain("recorded");
});

test("keeps ordinary login available while missing trusted workflow config disables workflow controls", async () => {
  const user = { uid: "firebase-uid", getIdToken: vi.fn().mockResolvedValue("firebase-token") };
  getAuth.mockReturnValue({ currentUser: user });
  signInWithPopup.mockResolvedValue({ user });
  vi.stubGlobal("fetch", vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ googleSubject: "google-sub", firebaseConfig: { apiKey: "key", authDomain: "example.firebaseapp.com", projectId: "example" }, setupOnly: false })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ firebaseUid: "firebase-uid", googleSubject: "google-sub" }))));
  await load();
  await document.querySelector<HTMLButtonElement>("#login")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(document.querySelector<HTMLElement>("#manual-sync")!.hidden).toBe(true);
  expect(document.querySelector<HTMLButtonElement>("#logout")!.hidden).toBe(false);
});

test("loads owner scoped recovery handles only when the host advertises recovery", async () => {
  const user = { uid: "firebase-1", getIdToken: vi.fn().mockResolvedValue("firebase-token") };
  getAuth.mockReturnValue({ currentUser: user });
  signInWithPopup.mockResolvedValue({ user });
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ googleSubject: "google-1", firebaseConfig: { apiKey: "key", authDomain: "example.firebaseapp.com", projectId: "example" }, workflowConfig: capture.config, workflowRecovery: true, setupOnly: false })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ firebaseUid: "firebase-1", googleSubject: "google-1" })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ operations: [{ operation_id: "unknown-1", descriptor_hash: "d".repeat(64), kind: "history_upload", state: "unknown" }] })));
  vi.stubGlobal("fetch", fetchMock);
  await load();
  await document.querySelector<HTMLButtonElement>("#login")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(fetchMock.mock.calls[2][0]).toBe("/api/workflow/recovery");
  expect(document.querySelector<HTMLButtonElement>("#sync-reconcile")!.hidden).toBe(false);
});

test("refuses a competing same-owner preview while one is active", async () => {
  const user = { uid: "firebase-1", getIdToken: vi.fn().mockResolvedValue("firebase-token") };
  getAuth.mockReturnValue({ currentUser: user });
  signInWithPopup.mockResolvedValue({ user });
  let resolveFirst!: (response: Response) => void;
  let resolveSecond!: (response: Response) => void;
  const first = new Promise<Response>((resolve) => { resolveFirst = resolve; });
  const second = new Promise<Response>((resolve) => { resolveSecond = resolve; });
  let previews = 0;
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ googleSubject: "google-1", firebaseConfig: { apiKey: "key", authDomain: "example.firebaseapp.com", projectId: "example" }, workflowConfig: capture.config, setupOnly: false, pendingHistory: capture.history_preview.records })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ firebaseUid: "firebase-1", googleSubject: "google-1" })))
    .mockImplementationOnce(() => { previews += 1; return first; })
    .mockImplementationOnce(() => { previews += 1; return second; });
  vi.stubGlobal("fetch", fetchMock);
  await load();
  await document.querySelector<HTMLButtonElement>("#login")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  document.querySelector<HTMLButtonElement>("#sync-preview")!.click();
  document.querySelector<HTMLButtonElement>("#sync-preview")!.click();
  resolveFirst(new Response(JSON.stringify({ ...capture.history_preview, operation_id: "old-preview" })));
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(previews).toBe(1);
  expect(document.querySelector("#sync-details")!.textContent).toContain("old-preview");
});

test("requires both upload and exact apply consents before applying a changeset", async () => {
  const user = { uid: "firebase-uid", getIdToken: vi.fn().mockResolvedValue("firebase-token") };
  getAuth.mockReturnValue({ currentUser: user });
  signInWithPopup.mockResolvedValue({ user });
  const task = { payload: { task_id: "apply-1", project_id: "example", workspace_id: "w", user_id: "google-sub", intent: "apply" }, changeset: { change_id: "change-1" } };
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ googleSubject: "google-sub", firebaseConfig: { apiKey: "key", authDomain: "example.firebaseapp.com", projectId: "example", controlDatabaseId: "control", runtimeDatabaseId: "runtime" }, workflowConfig: { project_id: "example", workspace_id: "w", control_database_id: "control", runtime_database_id: "runtime", session_id: "session", session_expires_at: "2099-01-01T00:00:00Z" }, setupOnly: false, pendingTask: task })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ firebaseUid: "firebase-uid", googleSubject: "google-sub" })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ operation_id: "preview", descriptor_hash: "a".repeat(64), request_hash: "b".repeat(64), bound_digest: "c".repeat(64), changeset: task.changeset })));
  vi.stubGlobal("fetch", fetchMock);
  await load();
  await document.querySelector<HTMLButtonElement>("#login")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await document.querySelector<HTMLButtonElement>("#task-preview")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  document.querySelector<HTMLInputElement>("#task-consent")!.checked = true;
  await document.querySelector<HTMLButtonElement>("#task-record")!.click();
  expect(fetchMock).toHaveBeenCalledTimes(3);
  expect(document.querySelector("#sync-details")!.textContent).toContain("Both upload/run and exact apply approvals");
  document.querySelector<HTMLInputElement>("#apply-consent")!.checked = true;
  expect(document.querySelector<HTMLButtonElement>("#task-record")!.disabled).toBe(false);
});

test("runs a complete task plan and exact apply flow with both approvals", async () => {
  vi.setSystemTime(new Date(capture.clock));
  const user = { uid: "firebase-1", getIdToken: vi.fn().mockResolvedValue("firebase-token") };
  getAuth.mockReturnValue({ currentUser: user });
  signInWithPopup.mockResolvedValue({ user });
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ googleSubject: "google-1", firebaseConfig: { apiKey: "key", authDomain: "example.firebaseapp.com", projectId: "example" }, workflowConfig: capture.config, setupOnly: false, pendingTask: { payload: capture.apply_preview.request, changeset: capture.apply_preview.changeset } })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ firebaseUid: "firebase-1", googleSubject: "google-1" })))
    .mockResolvedValueOnce(new Response(JSON.stringify(capture.apply_preview)))
    .mockResolvedValueOnce(new Response(JSON.stringify(capture.apply_consent)))
    .mockResolvedValueOnce(new Response(JSON.stringify({ status: "acknowledged", operation_id: capture.apply_consent.operation_id, descriptor_hash: capture.apply_consent.descriptor_hash })));
  vi.stubGlobal("fetch", fetchMock);
  await load();
  await document.querySelector<HTMLButtonElement>("#login")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await document.querySelector<HTMLButtonElement>("#task-preview")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  document.querySelector<HTMLInputElement>("#task-consent")!.checked = true;
  document.querySelector<HTMLInputElement>("#apply-consent")!.checked = true;
  await document.querySelector<HTMLButtonElement>("#task-record")!.click();
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(firestoreMocks.db.writeBatch).toHaveBeenCalledTimes(1);
  expect(fetchMock.mock.calls[2][1].body).toContain("projectId");
  expect(document.querySelector("#sync-details")!.textContent).toContain("atomically");
});

test("mounts metadata consent, separate exact result preview/import, and reconciliation", async () => {
  vi.setSystemTime(new Date(capture.clock));
  const user = { uid: "firebase-1", getIdToken: vi.fn().mockResolvedValue("firebase-token") };
  getAuth.mockReturnValue({ currentUser: user });
  signInWithPopup.mockResolvedValue({ user });
  firestoreMocks.getDoc.mockImplementation(async (ref: unknown) => ({ exists: () => true, data: () => String(ref).includes("/results/") ? capture.result_envelope : capture.manifest }));
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ googleSubject: "google-1", firebaseConfig: { apiKey: "key", authDomain: "example.firebaseapp.com", projectId: "example" }, workflowConfig: capture.config, setupOnly: false, pendingHistory: capture.history_preview.records })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ firebaseUid: "firebase-1", googleSubject: "google-1" })))
    .mockResolvedValueOnce(new Response(JSON.stringify(capture.manifest_preview)))
    .mockResolvedValueOnce(new Response(JSON.stringify(capture.manifest_consent)))
    .mockResolvedValueOnce(new Response(JSON.stringify({ status: "acknowledged" })))
    .mockResolvedValueOnce(new Response(JSON.stringify(capture.download_preview)))
    .mockResolvedValueOnce(new Response(JSON.stringify(capture.download_consent)))
    .mockResolvedValueOnce(new Response(JSON.stringify({ status: "acknowledged" })));
  vi.stubGlobal("fetch", fetchMock);
  await load();
  await document.querySelector<HTMLButtonElement>("#login")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await document.querySelector<HTMLButtonElement>("#manifest-preview")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  document.querySelector<HTMLInputElement>("#manifest-consent")!.checked = true;
  await document.querySelector<HTMLButtonElement>("#manifest-read")!.click();
  await new Promise((resolve) => setTimeout(resolve, 20));
  await document.querySelector<HTMLButtonElement>("#result-read")!.click();
  await new Promise((resolve) => setTimeout(resolve, 20));
  document.querySelector<HTMLInputElement>("#result-consent")!.checked = true;
  await document.querySelector<HTMLButtonElement>("#result-download")!.click();
  await new Promise((resolve) => setTimeout(resolve, 30));
  expect(fetchMock.mock.calls.filter((call) => call[0] === "/api/workflow/preview")).toHaveLength(2);
  expect(document.querySelector("#download-details")!.textContent).toContain("Exact result downloaded");
});

test("restores visible login controls after signout for a later login", async () => {
  const user = { uid: "firebase-uid", getIdToken: vi.fn().mockResolvedValue("firebase-token") };
  getAuth.mockReturnValue({ currentUser: user });
  signInWithPopup.mockResolvedValue({ user });
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ googleSubject: "google-sub", firebaseConfig: { apiKey: "key", authDomain: "example.firebaseapp.com", projectId: "example" }, setupOnly: false, cloudGrant: { challenge: "challenge", purpose: "workspace", destination: "projects/p/secrets/s", scopes: ["openid"], expiresAt: "future" } })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ firebaseUid: "firebase-uid", googleSubject: "google-sub" })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ firebaseUid: "firebase-uid", googleSubject: "google-sub" })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ status: "stored" })));
  vi.stubGlobal("fetch", fetchMock);
  await load();
  await document.querySelector<HTMLButtonElement>("#login")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await document.querySelector<HTMLButtonElement>("#logout")!.click();
  expect(document.querySelector<HTMLButtonElement>("#login")!.hidden).toBe(false);
  expect(document.querySelector<HTMLButtonElement>("#login")!.disabled).toBe(false);
  await document.querySelector<HTMLButtonElement>("#login")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(document.querySelector<HTMLButtonElement>("#cloud-consent-submit")!.disabled).toBe(false);
  document.querySelector<HTMLInputElement>("#cloud-consent")!.checked = true;
  await document.querySelector<HTMLButtonElement>("#cloud-consent-submit")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(fetchMock.mock.calls.filter((call) => call[0] === "/api/cloud-grant-consent")).toHaveLength(1);
});

test("reconciles an acknowledged unknown write through a fresh complete preview", async () => {
  vi.setSystemTime(new Date(capture.clock));
  const user = { uid: "firebase-1", getIdToken: vi.fn().mockResolvedValue("firebase-token") };
  getAuth.mockReturnValue({ currentUser: user });
  signInWithPopup.mockResolvedValue({ user });
  firestoreMocks.getDoc.mockResolvedValue({ exists: () => true, data: () => capture.history_consent.instruction.writes[0].data });
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ googleSubject: "google-1", firebaseConfig: { apiKey: "key", authDomain: "example.firebaseapp.com", projectId: "example" }, workflowConfig: capture.config, setupOnly: false, pendingHistory: capture.history_preview.records })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ firebaseUid: "firebase-1", googleSubject: "google-1" })))
    .mockResolvedValueOnce(new Response(JSON.stringify(capture.history_preview)))
    .mockResolvedValueOnce(new Response(JSON.stringify(capture.history_consent)))
    .mockResolvedValueOnce(new Response(JSON.stringify({ status: "unknown", operation_id: capture.history_consent.operation_id, descriptor_hash: capture.history_consent.descriptor_hash })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ status: "unknown", operation_id: capture.history_consent.operation_id, descriptor_hash: capture.history_consent.descriptor_hash })))
    .mockResolvedValueOnce(new Response(JSON.stringify(capture.reconcile_preview)))
    .mockResolvedValueOnce(new Response(JSON.stringify(capture.reconcile_consent)))
    .mockResolvedValueOnce(new Response(JSON.stringify({ status: "reconciled" })));
  vi.stubGlobal("fetch", fetchMock);
  await load();
  await document.querySelector<HTMLButtonElement>("#login")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await document.querySelector<HTMLButtonElement>("#sync-preview")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  document.querySelector<HTMLInputElement>("#sync-consent")!.checked = true;
  await document.querySelector<HTMLButtonElement>("#sync-upload")!.click();
  await new Promise((resolve) => setTimeout(resolve, 25));
  await document.querySelector<HTMLButtonElement>("#sync-reconcile")!.click();
  await new Promise((resolve) => setTimeout(resolve, 10));
  document.querySelector<HTMLInputElement>("#reconcile-consent")!.checked = true;
  await document.querySelector<HTMLButtonElement>("#reconcile-read")!.click();
  await new Promise((resolve) => setTimeout(resolve, 30));
  expect(fetchMock.mock.calls.filter((call) => call[0] === "/api/workflow/reconcile")).toHaveLength(1);
  const unknownAcks = fetchMock.mock.calls.filter((call) => call[0] === "/api/workflow/ack").map((call) => JSON.parse(call[1].body as string));
  expect(unknownAcks.some((body) => body.status === "unknown")).toBe(true);
  expect(document.querySelector("#sync-details")!.textContent).toContain("reconciled");
});

test("refuses a ninth retained consent without evicting the first eight", async () => {
  vi.setSystemTime(new Date(capture.clock));
  const user = { uid: "firebase-1", getIdToken: vi.fn().mockResolvedValue("firebase-token") };
  getAuth.mockReturnValue({ currentUser: user });
  signInWithPopup.mockResolvedValue({ user });
  let previewCount = 0;
  let consentCount = 0;
  firestoreMocks.getDoc.mockResolvedValue({ exists: () => true, data: () => capture.history_consent.instruction.writes[0].data });
  const fetchMock = vi.fn().mockImplementation(async (url: string, options?: RequestInit) => {
    if (url === "/api/session")
      return new Response(JSON.stringify({ googleSubject: "google-1", firebaseConfig: { apiKey: "key", authDomain: "example.firebaseapp.com", projectId: "example" }, workflowConfig: capture.config, setupOnly: false, pendingHistory: capture.history_preview.records }));
    if (url === "/api/firebase-binding")
      return new Response(JSON.stringify({ firebaseUid: "firebase-1", googleSubject: "google-1" }));
    if (url === "/api/workflow/preview") {
      previewCount += 1;
      if (options?.body && JSON.parse(String(options.body)).kind === "reconciliation")
        return new Response(JSON.stringify(capture.reconcile_preview));
      return new Response(JSON.stringify({ ...capture.history_preview, operation_id: `preview-${previewCount}`, descriptor_hash: `${String(previewCount).padStart(2, "0")}${"a".repeat(62)}` }));
    }
    if (url === "/api/workflow/consent") {
      consentCount += 1;
      const body = JSON.parse(String(options?.body ?? "{}"));
      if (body.operationId === capture.reconcile_preview.operation_id)
        return new Response(JSON.stringify(capture.reconcile_consent));
      if (consentCount === 1)
        return new Response(JSON.stringify({ ...capture.history_consent, instruction: undefined }));
      throw new Error("synthetic lost consent response");
    }
    if (url === "/api/workflow/ack")
      return new Response(JSON.stringify({ status: "unknown", operation_id: capture.history_consent.operation_id, descriptor_hash: capture.history_consent.descriptor_hash }));
    if (url === "/api/workflow/reconcile")
      return new Response(JSON.stringify({ status: "reconciled" }));
    throw new Error(`unexpected request ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  await load();
  await document.querySelector<HTMLButtonElement>("#login")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  for (let index = 0; index < 8; index += 1) {
    await document.querySelector<HTMLButtonElement>("#sync-preview")!.click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    const consent = document.querySelector<HTMLInputElement>("#sync-consent")!;
    consent.checked = true;
    await document.querySelector<HTMLButtonElement>("#sync-upload")!.click();
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  expect(consentCount).toBe(8);
  await document.querySelector<HTMLButtonElement>("#sync-preview")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  document.querySelector<HTMLInputElement>("#sync-consent")!.checked = true;
  await document.querySelector<HTMLButtonElement>("#sync-upload")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(consentCount).toBe(8);
  expect(document.querySelector("#sync-details")!.textContent).toContain("capacity is full");
  await document.querySelector<HTMLButtonElement>("#sync-reconcile")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  document.querySelector<HTMLInputElement>("#reconcile-consent")!.checked = true;
  await document.querySelector<HTMLButtonElement>("#reconcile-read")!.click();
  await new Promise((resolve) => setTimeout(resolve, 25));
  expect(consentCount).toBe(9);
  expect(fetchMock.mock.calls.filter((call) => call[0] === "/api/workflow/reconcile")).toHaveLength(1);
});

test("failed reconciliation read clears the child preview and retains the original target", async () => {
  vi.setSystemTime(new Date(capture.clock));
  const user = { uid: "firebase-1", getIdToken: vi.fn().mockResolvedValue("firebase-token") };
  getAuth.mockReturnValue({ currentUser: user });
  signInWithPopup.mockResolvedValue({ user });
  firestoreMocks.getDoc.mockRejectedValue(new Error("synthetic reconciliation read failure"));
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ googleSubject: "google-1", firebaseConfig: { apiKey: "key", authDomain: "example.firebaseapp.com", projectId: "example" }, workflowConfig: capture.config, setupOnly: false, pendingHistory: capture.history_preview.records })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ firebaseUid: "firebase-1", googleSubject: "google-1" })))
    .mockResolvedValueOnce(new Response(JSON.stringify(capture.history_preview)))
    .mockResolvedValueOnce(new Response(JSON.stringify(capture.history_consent)))
    .mockResolvedValueOnce(new Response(JSON.stringify({ status: "unknown", operation_id: capture.history_consent.operation_id, descriptor_hash: capture.history_consent.descriptor_hash })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ status: "unknown", operation_id: capture.history_consent.operation_id, descriptor_hash: capture.history_consent.descriptor_hash })))
    .mockResolvedValueOnce(new Response(JSON.stringify(capture.reconcile_preview)))
    .mockResolvedValueOnce(new Response(JSON.stringify(capture.reconcile_consent)));
  vi.stubGlobal("fetch", fetchMock);
  await load();
  await document.querySelector<HTMLButtonElement>("#login")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await document.querySelector<HTMLButtonElement>("#sync-preview")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  document.querySelector<HTMLInputElement>("#sync-consent")!.checked = true;
  await document.querySelector<HTMLButtonElement>("#sync-upload")!.click();
  await new Promise((resolve) => setTimeout(resolve, 30));
  await document.querySelector<HTMLButtonElement>("#sync-reconcile")!.click();
  await new Promise((resolve) => setTimeout(resolve, 10));
  document.querySelector<HTMLInputElement>("#reconcile-consent")!.checked = true;
  await document.querySelector<HTMLButtonElement>("#reconcile-read")!.click();
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(document.querySelector<HTMLInputElement>("#reconcile-consent")!.checked).toBe(false);
  expect(document.querySelector<HTMLButtonElement>("#reconcile-read")!.disabled).toBe(true);
  expect(document.querySelector<HTMLButtonElement>("#sync-reconcile")!.hidden).toBe(false);
  const consentCalls = fetchMock.mock.calls.filter((call) => call[0] === "/api/workflow/consent").length;
  await document.querySelector<HTMLButtonElement>("#reconcile-read")!.click();
  expect(fetchMock.mock.calls.filter((call) => call[0] === "/api/workflow/consent").length).toBe(consentCalls);
  expect(document.querySelector("#sync-details")!.textContent).toContain("synthetic reconciliation read failure");
});
