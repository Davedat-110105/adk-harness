import { readFileSync } from "node:fs";
import canonicalize from "canonicalize";
import { afterEach, describe, expect, it, vi } from "vitest";
import { executeLiteInstruction, type LiteInstruction, type SyncFirestore } from "../src/sync";

type Capture = {
  clock: string;
  config: { project_id: string; workspace_id: string; control_database_id: string; runtime_database_id: string; session_id: string; session_expires_at: string };
  [key: string]: any;
};

const capture = JSON.parse(readFileSync("tests/fixtures/host-flow-probe-fixtures.json", "utf8")) as Capture;
const context = {
  projectId: capture.config.project_id,
  workspaceId: capture.config.workspace_id,
  firebaseUid: "firebase-1",
  googleSubject: "google-1",
  sessionId: capture.config.session_id,
  taskId: "history-1",
  controlDatabaseId: capture.config.control_database_id,
  runtimeDatabaseId: capture.config.runtime_database_id,
  sessionExpiresAt: capture.config.session_expires_at,
};

afterEach(() => vi.useRealTimers());

function firestore(data: Record<string, unknown> = {}, databaseId?: string) {
  const set = vi.fn();
  const commit = vi.fn(async () => undefined);
  const db: SyncFirestore = {
    databaseId,
    writeBatch: vi.fn(() => ({ set, commit })),
    doc: vi.fn((...parts: string[]) => parts.join("/")),
    getDoc: vi.fn(async () => ({ exists: () => true, data: () => data })),
  };
  return { db, set, commit };
}

function instruction(name: string): LiteInstruction {
  return structuredClone(capture[name].instruction) as LiteInstruction;
}

describe("official Firebase Lite instruction boundary", () => {
  it.each([
    ["plan_consent", "writeBatch"],
    ["apply_consent", "writeBatch"],
    ["history_consent", "writeBatch"],
    ["manifest_consent", "getDoc"],
    ["download_consent", "getDoc"],
    ["reconcile_consent", "getDoc"],
  ])("accepts the complete host captured %s instruction", async (name, method) => {
    vi.setSystemTime(new Date(capture.clock));
    const control = firestore({}, capture.config.control_database_id);
    const runtime = firestore(capture.manifest, capture.config.runtime_database_id);
    const result = await executeLiteInstruction({ control: control.db, runtime: runtime.db }, instruction(name), context);
    expect(instruction(name).method).toBe(method);
    if (method === "writeBatch") expect(control.db.writeBatch).toHaveBeenCalledTimes(1);
    else expect(result).toBeDefined();
    vi.useRealTimers();
  });

  it("preserves model timestamp strings and converts only fixed envelope mirrors", async () => {
    vi.setSystemTime(new Date(capture.clock));
    const control = firestore({}, capture.config.control_database_id);
    await executeLiteInstruction({ control: control.db, runtime: firestore({}, capture.config.runtime_database_id).db }, instruction("history_consent"), context);
    const stored = control.set.mock.calls[0][1] as Record<string, any>;
    expect(stored.expires_at_ts).toMatchObject({ seconds: 1787947637, nanoseconds: 123456000 });
    expect(stored.events[0].details.microseconds).toBe("2026-08-28T20:02:17.123456+00:00");
    vi.useRealTimers();
  });

  it.each([
    ["descriptor", (i: any) => { delete i.descriptor; }],
    ["payload and hash", (i: any) => { delete i.payload; delete i.payload_hash; }],
    ["expiry", (i: any) => { delete i.descriptor.expires_at; }],
  ])("rejects missing %s before SDK access", async (_label, mutate) => {
    vi.setSystemTime(new Date(capture.clock));
    const control = firestore({}, capture.config.control_database_id);
    const item = instruction("history_consent");
    mutate(item);
    await expect(executeLiteInstruction({ control: control.db, runtime: firestore().db }, item, context)).rejects.toThrow();
    expect(control.db.writeBatch).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("rejects changed executable model data even when the outer payload hash is recomputed", async () => {
    vi.setSystemTime(new Date(capture.clock));
    const control = firestore({}, capture.config.control_database_id);
    const item = instruction("apply_consent");
    item.writes![0].data.content = "unapproved content";
    item.payload.writes = structuredClone(item.writes);
    const canonical = canonicalize(item.payload)!;
    const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonical));
    item.payload_hash = Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, "0")).join("");
    await expect(executeLiteInstruction({ control: control.db, runtime: firestore().db }, item, context)).rejects.toThrow();
    expect(control.db.writeBatch).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("stops before the next reconciliation read after an identity change", async () => {
    vi.setSystemTime(new Date(capture.clock));
    let current = true;
    const control = firestore(capture.manifest, capture.config.control_database_id);
    control.db.getDoc = vi.fn(async (ref: unknown) => { current = false; return { exists: () => true, data: () => capture.manifest }; });
    await expect(executeLiteInstruction({ control: control.db, runtime: firestore().db }, instruction("plan_reconcile_consent"), context, () => current)).rejects.toThrow("account changed");
    expect(control.db.getDoc).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it("accepts the real complete reconciliation instruction and keeps its raw result envelope", async () => {
    vi.setSystemTime(new Date(capture.clock));
    const item = instruction("reconcile_consent");
    const control = firestore(capture.history_consent.instruction.writes[0].data, capture.config.control_database_id);
    const observed = await executeLiteInstruction({ control: control.db, runtime: firestore({}, capture.config.runtime_database_id).db }, item, context);
    expect(observed).toEqual({ documents: [{ path: item.path, data: capture.history_consent.instruction.writes[0].data }] });
    vi.useRealTimers();
  });

  it.each([
    ["request expiry mirror", "history_consent", "request", false],
    ["approval expiry mirror", "history_consent", "approval-expiry", false],
    ["approval timestamp mirror", "history_consent", "approval-approved", false],
    ["missing request expiry mirror", "history_consent", "request", true],
  ])("rejects a rehashed %s before SDK access", async (_label, name, slot, missing) => {
    vi.setSystemTime(new Date(capture.clock));
    const item = instruction(name);
    const data = item.writes![0].data as any;
    const target = slot === "approval-expiry" || slot === "approval-approved" ? data.approval : data;
    if (missing) delete target.expires_at_ts;
    else if (slot === "approval-approved") target.approved_at_ts = { type: "firestore/timestamp/1.0", seconds: 1, nanoseconds: 0 };
    else target.expires_at_ts = { type: "firestore/timestamp/1.0", seconds: 1, nanoseconds: 0 };
    item.payload.writes = structuredClone(item.writes);
    item.payload_hash = await hash(item.payload);
    const control = firestore({}, capture.config.control_database_id);
    await expect(executeLiteInstruction({ control: control.db, runtime: firestore().db }, item, context)).rejects.toThrow();
    expect(control.db.writeBatch).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("rejects a rehashed envelope whose ISO expiry conflicts with the approved descriptor", async () => {
    vi.setSystemTime(new Date(capture.clock));
    const item = instruction("history_consent");
    const data = item.writes![0].data as any;
    data.expires_at = "2099-01-01T00:00:00.123456Z";
    data.expires_at_ts = { type: "firestore/timestamp/1.0", seconds: 4070908800, nanoseconds: 123456000 };
    item.payload.writes = structuredClone(item.writes);
    item.payload_hash = await hash(item.payload);
    const control = firestore({}, capture.config.control_database_id);
    await expect(executeLiteInstruction({ control: control.db, runtime: firestore().db }, item, context)).rejects.toThrow();
    expect(control.db.writeBatch).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it.each([
    ["null payload", (item: any) => { item.payload = null; item.payload_hash = ""; }],
    ["missing exact apply approval", (item: any) => { item.writes = item.writes!.slice(0, 2); item.payload.writes = structuredClone(item.writes); }],
    ["changed changeset mirror", (item: any) => { item.writes![0].data.changeset = { altered: true }; item.payload.writes = structuredClone(item.writes); }],
    ["rehashed exact result path", (item: any) => { item.path = item.path!.replace(/[^/]+$/, "a".repeat(64)); item.payload.path = item.path; }],
    ["configured database mismatch", (item: any) => { item.database = "other-runtime"; item.payload.database = item.database; }],
  ])("rejects %s before any SDK call", async (_label, mutate) => {
    vi.setSystemTime(new Date(capture.clock));
    const item = instruction(_label === "missing exact apply approval" || _label === "changed changeset mirror" ? "apply_consent" : "download_consent");
    mutate(item);
    if (item.payload !== null) {
      item.payload_hash = await (async () => {
        const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonicalize(item.payload)!));
        return Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, "0")).join("");
      })();
    }
    const control = firestore({}, capture.config.control_database_id);
    const runtime = firestore(capture.result_envelope, capture.config.runtime_database_id);
    await expect(executeLiteInstruction({ control: control.db, runtime: runtime.db }, item, context)).rejects.toThrow();
    expect(control.db.writeBatch).not.toHaveBeenCalled();
    expect(runtime.db.getDoc).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("rejects a substituted upload approval in the exact apply slot", async () => {
    vi.setSystemTime(new Date(capture.clock));
    const item = instruction("apply_consent");
    item.writes![2].data = structuredClone(item.writes![1].data);
    item.writes![2].path = item.writes![2].path.replace(/approvals\/[^/]+$/, `approvals/${item.writes![2].data.approval_id}`);
    item.payload.writes = structuredClone(item.writes);
    item.payload_hash = await hash(item.payload);
    const control = firestore({}, capture.config.control_database_id);
    await expect(executeLiteInstruction({ control: control.db, runtime: firestore().db }, item, context)).rejects.toThrow();
    expect(control.db.writeBatch).not.toHaveBeenCalled();
  });

  it("rejects approval content altered with a rehashed executable payload", async () => {
    vi.setSystemTime(new Date(capture.clock));
    const item = instruction("apply_consent");
    item.writes![2].data.change_hash = "a".repeat(64);
    item.payload.writes = structuredClone(item.writes);
    item.payload_hash = await hash(item.payload);
    const control = firestore({}, capture.config.control_database_id);
    await expect(executeLiteInstruction({ control: control.db, runtime: firestore().db }, item, context)).rejects.toThrow();
    expect(control.db.writeBatch).not.toHaveBeenCalled();
  });

  it("rejects an approval missing its executable session binding after outer rehash", async () => {
    vi.setSystemTime(new Date(capture.clock));
    const item = instruction("apply_consent");
    delete item.writes![2].data.session_id;
    item.payload.writes = structuredClone(item.writes);
    item.payload_hash = await hash(item.payload);
    const control = firestore({}, capture.config.control_database_id);
    await expect(executeLiteInstruction({ control: control.db, runtime: firestore().db }, item, context)).rejects.toThrow();
    expect(control.db.writeBatch).not.toHaveBeenCalled();
  });

  it("rejects an extra top-level read when the hashed payload omits reads", async () => {
    vi.setSystemTime(new Date(capture.clock));
    const item = instruction("download_consent");
    item.reads = [
      { method: "getDoc", path: item.path!, whole_document: true },
      { method: "getDoc", path: item.path!.replace(/results\/[^/]+$/, `results/${"a".repeat(64)}`), whole_document: true },
    ];
    const runtime = firestore(capture.result_envelope, capture.config.runtime_database_id);
    await expect(executeLiteInstruction({ control: firestore({}, capture.config.control_database_id).db, runtime: runtime.db }, item, context)).rejects.toThrow();
    expect(runtime.db.getDoc).not.toHaveBeenCalled();
  });

  it("rejects an unknown descriptor kind after recomputing its descriptor hash", async () => {
    vi.setSystemTime(new Date(capture.clock));
    const item = instruction("download_consent");
    item.descriptor.kind = "unrecognized_kind";
    item.descriptor_hash = await hash(item.descriptor);
    const runtime = firestore(capture.result_envelope, capture.config.runtime_database_id);
    await expect(executeLiteInstruction({ control: firestore({}, capture.config.control_database_id).db, runtime: runtime.db }, item, context)).rejects.toThrow();
    expect(runtime.db.getDoc).not.toHaveBeenCalled();
  });

  it("rejects a rehashed normal grant that adds a second physical read", async () => {
    vi.setSystemTime(new Date(capture.clock));
    const item = instruction("download_consent");
    item.reads = [
      { method: "getDoc", path: item.path!, whole_document: true },
      { method: "getDoc", path: item.path!, whole_document: true },
    ];
    item.payload.reads = structuredClone(item.reads);
    item.payload_hash = await hash(item.payload);
    const runtime = firestore(capture.result_envelope, capture.config.runtime_database_id);
    await expect(executeLiteInstruction({ control: firestore({}, capture.config.control_database_id).db, runtime: runtime.db }, item, context)).rejects.toThrow();
    expect(runtime.db.getDoc).not.toHaveBeenCalled();
  });
  it("rejects a normal result grant relabeled as reconciliation", async () => {
    vi.setSystemTime(new Date(capture.clock));
    const item = instruction("download_consent");
    item.read_scope = "reconciliation";
    item.reads = [
      { method: "getDoc", path: item.path!, whole_document: true },
      { method: "getDoc", path: item.path!, whole_document: true },
    ];
    item.payload.read_scope = "reconciliation";
    item.payload.reads = structuredClone(item.reads);
    item.payload_hash = await hash(item.payload);
    const runtime = firestore(capture.result_envelope, capture.config.runtime_database_id);
    await expect(executeLiteInstruction({ control: firestore({}, capture.config.control_database_id).db, runtime: runtime.db }, item, context)).rejects.toThrow();
    expect(runtime.db.getDoc).not.toHaveBeenCalled();
    vi.useRealTimers();
  });
});

async function hash(value: unknown): Promise<string> {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonicalize(value)!));
  return Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, "0")).join("");
}
