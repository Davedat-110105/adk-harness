import canonicalize from "canonicalize";
import { Timestamp } from "firebase/firestore/lite";
export type SyncIdentity = {
    googleSubject: string;
    firebaseUid: string;
    projectId: string;
    workspaceId: string;
    taskId: string;
    sessionId: string;
};
export type SyncFirestore = {
    databaseId?: string;
    writeBatch: () => {
        set: (ref: unknown, value: unknown) => void;
        commit: () => Promise<void>;
    };
    doc: (...parts: string[]) => unknown;
    getDoc: (ref: unknown) => Promise<{
        exists: () => boolean;
        data: () => Record<string, unknown>;
    }>;
};
export type LiteInstruction = {
    version: 1;
    sdk: "firebase/firestore/lite";
    operation_id: string;
    namespace: "control" | "runtime";
    descriptor_hash: string;
    project_id?: string;
    workspace_id?: string;
    session_id?: string;
    firebase_uid?: string;
    owner_google_subject?: string;
    database: string;
    descriptor: Record<string, unknown>;
    payload: Record<string, unknown>;
    payload_hash: string;
    read_scope?: string;
    method: "writeBatch" | "getDoc";
    path?: string;
    reads?: Array<{
        method: "getDoc";
        path: string;
        whole_document: true;
    }>;
    fields?: string[];
    writes?: Array<{
        path: string;
        mode: "create";
        data: Record<string, unknown>;
    }>;
    bounds: {
        max_documents: number;
        max_bytes: number;
    };
};
export type InstructionContext = Pick<SyncIdentity, "projectId" | "workspaceId" | "firebaseUid" | "googleSubject" | "sessionId" | "taskId"> & {
    controlDatabaseId?: string;
    runtimeDatabaseId?: string;
    sessionExpiresAt?: string;
    reconciliationTargetKind?: string;
};
export type UploadDescriptor = {
    kind: "history_upload";
    projectId: string;
    workspaceId: string;
    taskId: string;
    googleSubject: string;
    firebaseUid: string;
    eventIds: string[];
    payloadHash: string;
    sessionId: string;
    records?: unknown[];
    approval?: {
        descriptorHash: string;
        payloadHash: string;
        expiresAt: string;
        eventIds: string[];
    };
};
export type TaskDescriptor = {
    kind: "task_request";
    requestId: string;
    approvalId: string;
    payload: Record<string, unknown>;
    canonicalPayload: string;
    requestHash: string;
    approval: Record<string, unknown>;
    projectId: string;
    workspaceId: string;
    taskId: string;
    googleSubject: string;
    firebaseUid: string;
    sessionId: string;
};
export type ManifestReadDescriptor = {
    kind: "bounded_manifest_read";
    projectId: string;
    workspaceId: string;
    taskId: string;
    googleSubject: string;
    firebaseUid: string;
    fields: string[];
    sessionId: string;
    descriptorHash: string;
};
export type StagedManifest = Record<string, unknown> & {
    result_id: string;
    result_hash: string;
    scope: string[];
    descriptorHash: string;
};
export type SyncAck = {
    outcome: "acknowledged" | "unknown";
    owner: string;
    ackId?: string;
};
function sha256Bytes(value: string): Promise<string> {
    return crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)).then((bytes) => Array.from(new Uint8Array(bytes), (byte) => byte.toString(16).padStart(2, "0")).join(""));
}
async function digest(value: unknown): Promise<string> {
    const text = canonicalize(value);
    if (!text)
        throw new Error("record is not canonicalizable");
    return sha256Bytes(text);
}
function safeId(value: string, name: string): string {
    if (!value || value === "." || value === ".." || value.includes("/"))
        throw new Error(`${name} is invalid`);
    return value;
}
function splitPath(path: string): string[] {
    if (!path || path.startsWith("/") || path.endsWith("/") || path.split("/").some((part) => !part))
        throw new Error("instruction path is invalid");
    return path.split("/").map((part) => safeId(part, "path component"));
}
function validateBoundPath(parts: string[], expected: InstructionContext, mode: "read" | "write", namespace: "control" | "runtime"): void {
    if (parts.length % 2 !== 0 || parts[0] !== "projects" || parts[1] !== expected.projectId || parts[2] !== "workspaces" || parts[3] !== expected.workspaceId)
        throw new Error("instruction path binding is invalid");
    if (namespace === "runtime") {
        if (parts.length !== 10 || parts[4] !== "users" || parts[5] !== expected.firebaseUid || parts[6] !== "tasks" || parts[7] !== expected.taskId || parts[8] !== "manifests" && parts[8] !== "results" && parts[8] !== "events")
            throw new Error("instruction path binding is invalid");
        if (mode !== "read" || (parts[8] === "manifests" && parts[9] !== "latest") || (parts[8] !== "manifests" && !/^[a-f0-9]{64}$/.test(parts[9])))
            throw new Error("instruction path binding is invalid");
        return;
    }
    if (parts[4] !== "members" || parts[5] !== expected.firebaseUid || (parts[6] !== "requests" && parts[6] !== "exports"))
        throw new Error("instruction path binding is invalid");
    if (parts[6] === "exports" && parts.length !== 8)
        throw new Error("instruction path binding is invalid");
    if (parts[6] === "requests" && (parts.length !== 8 && parts.length !== 10 || parts.length === 10 && (parts[8] !== "approvals" || !parts[9])))
        throw new Error("instruction path binding is invalid");
}
const MIRROR_KEYS = new Set(["expires_at_ts", "approved_at_ts", "created_at_ts", "committed_at_ts"]);
function cloneModel(value: unknown): unknown {
    if (Array.isArray(value))
        return value.map(cloneModel);
    if (!value || typeof value !== "object")
        return value;
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, cloneModel(item)]));
}
function nativeEnvelope(value: unknown): unknown {
    if (Array.isArray(value))
        return value.map(nativeEnvelope);
    if (!value || typeof value !== "object")
        return value;
    const result: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value)) {
        if (MIRROR_KEYS.has(key) && item && typeof item === "object") {
            const mirror = item as Record<string, unknown>;
            if (mirror.type === "firestore/timestamp/1.0" && Number.isInteger(mirror.seconds) && Number.isInteger(mirror.nanoseconds)) {
                result[key] = new Timestamp(mirror.seconds as number, mirror.nanoseconds as number);
                continue;
            }
        }
        result[key] = key === "approval" ? nativeEnvelope(item) : cloneModel(item);
    }
    return result;
}
function portableEnvelope(value: unknown): unknown {
    if (Array.isArray(value))
        return value.map(portableEnvelope);
    if (!value || typeof value !== "object")
        return value;
    if (value instanceof Timestamp) {
        const mirror = value as {
            seconds: number;
            nanoseconds: number;
        };
        return { type: "firestore/timestamp/1.0", seconds: mirror.seconds, nanoseconds: mirror.nanoseconds };
    }
    const result: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value))
        result[key] = portableEnvelope(item);
    return result;
}
function timestampMirror(value: unknown, iso: unknown, label: string): void {
    if (typeof iso !== "string")
        throw new Error(`${label} timestamp is missing`);
    let expected: Timestamp;
    try {
        expected = timestampFromIso(iso);
    }
    catch {
        throw new Error(`${label} timestamp is malformed`);
    }
    if (!value || typeof value !== "object" || Array.isArray(value))
        throw new Error(`${label} timestamp mirror is malformed`);
    const mirror = value as Record<string, unknown>;
    if (mirror.type !== "firestore/timestamp/1.0" || !Number.isInteger(mirror.seconds) || !Number.isInteger(mirror.nanoseconds) || Object.keys(mirror).length !== 3 || mirror.seconds !== expected.seconds || mirror.nanoseconds !== expected.nanoseconds)
        throw new Error(`${label} timestamp mirror mismatch`);
}
function fixedTimestampMirrors(value: Record<string, unknown>, expectedExpiry?: string, label = "instruction"): void {
    if (expectedExpiry !== undefined && value.expires_at !== undefined && value.expires_at !== expectedExpiry)
        throw new Error(`${label} expiry is not approved`);
    const expiry = expectedExpiry ?? (typeof value.expires_at === "string" ? value.expires_at : undefined);
    if (value.expires_at_ts !== undefined || expectedExpiry !== undefined)
        timestampMirror(value.expires_at_ts, expiry, `${label} expiry`);
    if (value.approved_at !== undefined || value.approved_at_ts !== undefined)
        timestampMirror(value.approved_at_ts, value.approved_at, `${label} approval`);
}
function instructionContextValue(instruction: LiteInstruction, key: keyof InstructionContext): string | undefined {
    const directKey = ({ projectId: "project_id", workspaceId: "workspace_id", firebaseUid: "firebase_uid", googleSubject: "owner_google_subject", sessionId: "session_id", taskId: "task_id" } as Partial<Record<keyof InstructionContext, string>>)[key];
    if (!directKey)
        return undefined;
    const direct = instruction[directKey as keyof LiteInstruction];
    if (typeof direct === "string")
        return direct;
    const descriptor = instruction.descriptor;
    const descriptorKey = ({ projectId: "project_id", workspaceId: "workspace_id", firebaseUid: "firebase_uid", googleSubject: "google_subject", sessionId: "session_id", taskId: "task_id" } as Partial<Record<keyof InstructionContext, string>>)[key];
    if (!descriptorKey)
        return undefined;
    const value = descriptor?.[descriptorKey] ?? (key === "googleSubject" ? descriptor?.google_sub : undefined);
    return typeof value === "string" ? value : undefined;
}
async function validateInstruction(instruction: LiteInstruction, expected: InstructionContext): Promise<void> {
    if (instruction.version !== 1 || instruction.sdk !== "firebase/firestore/lite" || !instruction.bounds || instruction.bounds.max_documents !== 500 || instruction.bounds.max_bytes !== 1000000)
        throw new Error("instruction contract is invalid");
    if (!/^[a-f0-9]{64}$/.test(instruction.descriptor_hash))
        throw new Error("instruction descriptor hash is invalid");
    if (instruction.namespace !== "control" && instruction.namespace !== "runtime")
        throw new Error("instruction namespace is invalid");
    if (typeof instruction.database !== "string" || !instruction.database)
        throw new Error("instruction database is invalid");
    const expectedDatabaseId = instruction.namespace === "control" ? expected.controlDatabaseId : expected.runtimeDatabaseId;
    if (!expectedDatabaseId || instruction.database !== expectedDatabaseId)
        throw new Error("instruction database is invalid");
    if (instruction.descriptor) {
        const descriptorHash = await digest(instruction.descriptor);
        if (descriptorHash !== instruction.descriptor_hash)
            throw new Error("instruction descriptor hash is invalid");
        for (const key of ["project_id", "workspace_id", "firebase_uid", "session_id"] as const) {
            const descriptorValue = instruction.descriptor[key];
            const instructionValue = instruction[key];
            if (descriptorValue !== undefined && instructionValue !== undefined && descriptorValue !== instructionValue)
                throw new Error("instruction semantic binding is invalid");
        }
        const expiresAt = instruction.descriptor.expires_at;
        if (typeof expiresAt === "string") {
            const expiry = Date.parse(expiresAt);
            const sessionExpiry = expected.sessionExpiresAt ? Date.parse(expected.sessionExpiresAt) : Number.POSITIVE_INFINITY;
            if (!Number.isFinite(expiry) || expiry <= Date.now() || expiry > sessionExpiry)
                throw new Error("instruction grant has expired");
        }
        else {
            throw new Error("instruction grant expiry is missing");
        }
        if (typeof instruction.descriptor.kind !== "string" || !instruction.descriptor.kind)
            throw new Error("instruction kind is missing");
        const allowed = instruction.method === "writeBatch" && instruction.namespace === "control"
            ? new Set(["task_request", "history_upload"])
            : instruction.method === "getDoc" && instruction.namespace === "runtime"
                ? new Set(["bounded_manifest_read", "exact_result_download", "reconciliation_read"])
                : instruction.method === "getDoc" && (instruction.namespace === "control" || instruction.namespace === "runtime")
                    ? new Set(["reconciliation_read"])
                    : new Set<string>();
        if (!allowed.has(instruction.descriptor.kind))
            throw new Error("instruction kind and method are invalid");
    }
    else {
        throw new Error("instruction descriptor is missing");
    }
    if (!instruction.payload || typeof instruction.payload !== "object" || Array.isArray(instruction.payload))
        throw new Error("instruction executable payload is invalid");
    {
        const payload = instruction.payload;
        if (payload.method !== instruction.method || payload.database !== instruction.database)
            throw new Error("instruction executable payload is invalid");
        if (instruction.method === "writeBatch" && (!Array.isArray(payload.writes) || !Array.isArray(instruction.writes) || canonicalize(payload.writes) !== canonicalize(instruction.writes)))
            throw new Error("instruction executable payload is invalid");
        if (instruction.method === "getDoc" && (typeof payload.path !== "string" || payload.path !== instruction.path || canonicalize(payload.reads ?? null) !== canonicalize(instruction.reads ?? null) || payload.read_scope !== instruction.read_scope))
            throw new Error("instruction executable payload is invalid");
    }
    if (typeof instruction.payload_hash !== "string" || !instruction.payload_hash || await digest(instruction.payload) !== instruction.payload_hash)
        throw new Error("instruction payload hash is invalid");
    const descriptor = instruction.descriptor;
    const validateApprovalModel = async (data: Record<string, unknown>, requiredType?: string, expectedChangeHash?: string, requireSession = false): Promise<void> => {
        if (requiredType !== undefined && data.approval_type !== requiredType)
            throw new Error("instruction approval type is invalid");
        const canonicalPayload = data.canonical_payload;
        if (typeof canonicalPayload !== "string" || typeof data.approval_hash !== "string")
            throw new Error("instruction approval model is invalid");
        let approval: unknown;
        try { approval = JSON.parse(canonicalPayload); } catch { throw new Error("instruction approval model is invalid"); }
        if (!approval || typeof approval !== "object" || Array.isArray(approval) || canonicalize(approval) !== canonicalPayload || await sha256Bytes(canonicalPayload) !== data.approval_hash)
            throw new Error("instruction approval hash is invalid");
        const model = approval as Record<string, unknown>;
        const requiredKeys = ["schema_version", "approval_id", "task_id", "project_id", "workspace_id", "change_hash", "approver_id", "action_scope", "resource_versions", "policy_version", "trace_id", "approved_at", "expires_at"];
        const reconstructed = Object.fromEntries(requiredKeys.map((key) => [key, data[key]]));
        if (requiredKeys.some((key) => data[key] === undefined) || canonicalize(reconstructed) !== canonicalPayload)
            throw new Error("instruction approval model does not match executable data");
        if (expectedChangeHash !== undefined && model.change_hash !== expectedChangeHash)
            throw new Error("instruction approval digest is invalid");
        const descriptorTaskId = typeof instruction.descriptor.task_id === "string" ? instruction.descriptor.task_id : typeof data.task_id === "string" ? data.task_id : expected.taskId;
        if (model.project_id !== expected.projectId || model.workspace_id !== expected.workspaceId || model.task_id !== descriptorTaskId || model.approver_id !== expected.googleSubject || model.expires_at !== instruction.descriptor.expires_at)
            throw new Error("instruction approval binding is invalid");
        for (const key of ["action_scope", "resource_versions", "policy_version"])
            if (instruction.descriptor[key] !== undefined && canonicalize(model[key]) !== canonicalize(instruction.descriptor[key]))
                throw new Error("instruction approval binding is invalid");
        if (data.project_id !== expected.projectId || data.workspace_id !== expected.workspaceId || data.task_id !== descriptorTaskId || (requireSession && data.session_id !== expected.sessionId) || (!requireSession && data.session_id !== undefined && data.session_id !== expected.sessionId) || data.approver_google_sub !== undefined && data.approver_google_sub !== expected.googleSubject || data.approver_firebase_uid !== undefined && data.approver_firebase_uid !== expected.firebaseUid)
            throw new Error("instruction approval binding is invalid");
    };
    for (const write of instruction.writes ?? []) {
        const data = write.data;
        fixedTimestampMirrors(data, descriptor.expires_at as string, "instruction write");
        if (data.approval && typeof data.approval === "object" && !Array.isArray(data.approval))
            fixedTimestampMirrors(data.approval as Record<string, unknown>, undefined, "instruction nested approval");
        const canonicalPayload = data.canonical_payload;
        if (typeof canonicalPayload === "string" && typeof data.request_hash === "string") {
            let parsed: unknown;
            try {
                parsed = JSON.parse(canonicalPayload);
            }
            catch {
                throw new Error("instruction canonical model is invalid");
            }
            if (canonicalize(parsed) !== canonicalPayload || await sha256Bytes(canonicalPayload) !== data.request_hash)
                throw new Error("instruction canonical model hash is invalid");
            if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
                const requestKeys = ["schema_version", "task_id", "project_id", "workspace_id", "user_id", "content", "intent", "plan", "download_scopes", "apply_scopes", "scope", "resource_versions", "policy_version", "trace_id", "created_at"];
                const reconstructed = Object.fromEntries(requestKeys.filter((key) => data[key] !== undefined).map((key) => [key, data[key]]));
                if (canonicalize(reconstructed) !== canonicalPayload)
                    throw new Error("instruction canonical model does not match executable data");
            }
        }
        if (typeof data.changeset_canonical === "string" && typeof data.changeset_hash === "string") {
            let changeset: unknown;
            try {
                changeset = JSON.parse(data.changeset_canonical);
            }
            catch {
                throw new Error("instruction canonical model is invalid");
            }
            if (canonicalize(changeset) !== data.changeset_canonical || await sha256Bytes(data.changeset_canonical) !== data.changeset_hash)
                throw new Error("instruction canonical model hash is invalid");
            if (data.changeset !== undefined && canonicalize(data.changeset) !== data.changeset_canonical)
                throw new Error("instruction changeset mirror is invalid");
        }
        if (typeof canonicalPayload === "string" && typeof data.payload_hash === "string") {
            let payload: unknown;
            try {
                payload = JSON.parse(canonicalPayload);
            }
            catch {
                throw new Error("instruction canonical model is invalid");
            }
            if (canonicalize(payload) !== canonicalPayload || await sha256Bytes(canonicalPayload) !== data.payload_hash)
                throw new Error("instruction canonical model hash is invalid");
        }
        if (typeof data.approval_type === "string")
            await validateApprovalModel(data, data.approval_type, data.approval_type === "exact_apply" ? descriptor?.bound_digest as string : descriptor?.request_hash as string, true);
    }
    {
        const fields: Array<[
            keyof InstructionContext,
            string
        ]> = [["projectId", "project"], ["workspaceId", "workspace"], ["firebaseUid", "firebase UID"], ["googleSubject", "owner"], ["sessionId", "session"]];
        for (const [key, label] of fields) {
            if (instructionContextValue(instruction, key) !== expected[key])
                throw new Error(`instruction ${label} binding is invalid`);
        }
    }
    if (instruction.method === "writeBatch") {
        const writes = instruction.writes ?? [];
        const paths = writes.map((write) => write.path);
        if (new Set(paths).size !== paths.length)
            throw new Error("instruction writes are not unique");
        const requests = writes.filter((write) => typeof write.data.request_hash === "string");
        const approvals = writes.filter((write) => typeof write.data.approval_type === "string");
        if (descriptor.kind === "task_request") {
            const required = descriptor.approval_type === "exact_apply" ? ["upload_run", "exact_apply"] : ["upload_run"];
            const request = requests[0];
            const requestParts = request ? splitPath(request.path) : [];
            const requestId = typeof descriptor.request_id === "string" ? descriptor.request_id : undefined;
            const requiredIds = request?.data.required_approvals;
            const approvalIds = approvals.map((write) => write.data.approval_id);
            const expectedRequestPath = requestId ? ["projects", expected.projectId, "workspaces", expected.workspaceId, "members", expected.firebaseUid, "requests", requestId].join("/") : "";
            if (writes.length !== 1 + required.length || requests.length !== 1 || !request || request.path !== expectedRequestPath || requestParts.length !== 8 || request.data.request_hash !== descriptor.request_hash || approvals.length !== required.length || !Array.isArray(requiredIds) || requiredIds.length !== required.length || new Set(approvalIds).size !== approvalIds.length || canonicalize([...requiredIds].sort()) !== canonicalize([...approvalIds].sort()) || required.some((type) => approvals.filter((write) => write.data.approval_type === type).length !== 1))
                throw new Error("instruction approvals are incomplete");
            for (const approvalWrite of approvals) {
                const approvalId = approvalWrite.data.approval_id;
                if (typeof approvalId !== "string" || approvalWrite.path !== `${expectedRequestPath}/approvals/${approvalId}`)
                    throw new Error("instruction approval path is invalid");
                const expectedDigestKind = approvalWrite.data.approval_type === "exact_apply" ? descriptor.bound_digest_kind : "task_request";
                if (approvalWrite.data.request_id !== request.data.request_id || approvalWrite.data.firebase_uid !== expected.firebaseUid || approvalWrite.data.google_sub !== expected.googleSubject || approvalWrite.data.destination !== descriptor.destination || approvalWrite.data.bound_digest_kind !== expectedDigestKind)
                    throw new Error("instruction approval binding is invalid");
            }
        }
        if (descriptor.kind === "history_upload") {
            const exportWrite = writes[0];
            const exportParts = exportWrite ? splitPath(exportWrite.path) : [];
            const approval = exportWrite?.data.approval;
            if (writes.length !== 1 || exportParts.length !== 8 || exportParts[6] !== "exports" || !approval || typeof approval !== "object")
                throw new Error("instruction history export is incomplete");
            const approvalModel = approval as Record<string, unknown>;
            if (approvalModel.approval_id !== descriptor.approval_id || approvalModel.change_hash !== descriptor.payload_hash || approvalModel.project_id !== expected.projectId || approvalModel.workspace_id !== expected.workspaceId || approvalModel.task_id !== expected.taskId || approvalModel.expires_at !== descriptor.expires_at || exportWrite.data.firebase_uid !== expected.firebaseUid || exportWrite.data.session_id !== expected.sessionId || exportWrite.data.owner_google_subject !== expected.googleSubject)
                throw new Error("instruction history approval binding is invalid");
            if (!canonicalize(approvalModel.action_scope) || !canonicalize(approvalModel.action_scope)?.includes("event_ids") || canonicalize((approvalModel.action_scope as Record<string, unknown>).event_ids) !== canonicalize(descriptor.event_ids))
                throw new Error("instruction history approval scope is invalid");
            await validateApprovalModel({ ...approvalModel, approval_hash: exportWrite.data.approval_hash });
        }
    }
    if (instruction.method === "getDoc" && instruction.path) {
        const expectedScope: Record<string, string> = { bounded_manifest_read: "manifest", exact_result_download: "exact_result", reconciliation_read: "reconciliation" };
        if (instruction.read_scope !== expectedScope[typeof descriptor.kind === "string" ? descriptor.kind : ""])
            throw new Error("instruction read scope is invalid");
        const readParts = splitPath(instruction.path);
        if (typeof descriptor.path === "string" && descriptor.path !== instruction.path)
            throw new Error("instruction read path is not approved");
        const resultId = typeof descriptor.result_id === "string" ? descriptor.result_id : typeof descriptor.result_hash === "string" ? descriptor.result_hash : undefined;
        if (resultId && readParts.includes("results") && readParts[readParts.length - 1] !== resultId)
            throw new Error("instruction result path is not approved");
        if (descriptor.kind === "reconciliation_read") {
            const approvedPaths = descriptor.paths;
            if (!Array.isArray(approvedPaths) || approvedPaths.length === 0 || typeof descriptor.target_operation_id !== "string" || typeof descriptor.target_descriptor_hash !== "string" || descriptor.database !== instruction.database || canonicalize(approvedPaths) !== canonicalize(instruction.reads?.map((read) => read.path) ?? [instruction.path]))
                throw new Error("instruction reconciliation paths are not approved");
        }
    }
}
/** Execute exactly one host-issued operation through the official Lite client. */
export async function executeLiteInstruction(databases: {
    control: SyncFirestore;
    runtime: SyncFirestore;
}, instruction: LiteInstruction, expected: InstructionContext, isCurrent: () => boolean = () => true): Promise<Record<string, unknown> | undefined> {
    await validateInstruction(instruction, expected);
    if (!isCurrent())
        throw new Error("Firebase account changed during workflow operation");
    const db = databases[instruction.namespace];
    if (!db)
        throw new Error("instruction namespace is invalid");
    const expectedDatabaseId = instruction.namespace === "control" ? expected.controlDatabaseId : expected.runtimeDatabaseId;
    if (!expectedDatabaseId || db.databaseId !== expectedDatabaseId || instruction.database !== expectedDatabaseId)
        throw new Error("instruction database is invalid");
    if (instruction.method === "writeBatch") {
        if (!instruction.writes || instruction.writes.length === 0 || instruction.writes.length > instruction.bounds.max_documents)
            throw new Error("instruction batch is outside its bound");
        for (const write of instruction.writes) {
            if (write.mode !== "create")
                throw new Error("only create writes are allowed");
            const parts = splitPath(write.path);
            validateBoundPath(parts, expected, "write", instruction.namespace);
        }
        const bytes = new TextEncoder().encode(JSON.stringify(instruction.writes.map((write) => ({ ...write, data: nativeEnvelope(write.data) })))).byteLength;
        if (bytes > instruction.bounds.max_bytes)
            throw new Error("instruction batch is outside its byte bound");
        if (!isCurrent())
            throw new Error("Firebase account changed during workflow operation");
        const batch = db.writeBatch();
        for (const write of instruction.writes) {
            batch.set(db.doc(...splitPath(write.path)), nativeEnvelope(write.data));
        }
        await batch.commit();
        return undefined;
    }
    if (instruction.method !== "getDoc" || !instruction.path)
        throw new Error("instruction read is invalid");
    const parts = splitPath(instruction.path);
    validateBoundPath(parts, expected, "read", instruction.namespace);
    const reads = instruction.reads ?? [{ method: "getDoc" as const, path: instruction.path, whole_document: true as const }];
    if (reads.length === 0 || reads.length > instruction.bounds.max_documents || reads[0].path !== instruction.path || reads.some((read) => read.method !== "getDoc" || read.whole_document !== true))
        throw new Error("instruction reads are invalid");
    if (instruction.read_scope !== "reconciliation" && reads.length !== 1)
        throw new Error("instruction reads are invalid");
    const documents: Array<{
        path: string;
        data: Record<string, unknown>;
    }> = [];
    for (const read of reads) {
        const readParts = splitPath(read.path);
        validateBoundPath(readParts, expected, "read", instruction.namespace);
        if (!isCurrent())
            throw new Error("Firebase account changed during workflow operation");
        const snapshot = await db.getDoc(db.doc(...readParts));
        if (!isCurrent())
            throw new Error("Firebase account changed during workflow operation");
        if (!snapshot.exists())
            throw new Error("remote document is unavailable");
        documents.push({ path: read.path, data: portableEnvelope(snapshot.data()) as Record<string, unknown> });
    }
    if (instruction.read_scope === "reconciliation") {
        const exactResult = expected.reconciliationTargetKind === "exact_result_download" || reads.some((read) => read.path.split("/").includes("results"));
        return exactResult ? documents[0].data : { documents };
    }
    return documents[0].data;
}
export function timestampFromIso(iso: string): Timestamp {
    const match = /^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?(Z|[+-]\d\d:\d\d)$/.exec(iso);
    if (!match)
        throw new Error("timestamp must be an ISO-8601 instant");
    const milliseconds = Date.parse(`${match[1]}${match[3]}`);
    const seconds = Math.floor(milliseconds / 1000);
    const nanos = Number((match[2] ?? "").padEnd(9, "0"));
    return new Timestamp(seconds, nanos);
}
