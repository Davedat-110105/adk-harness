import { initializeApp } from "firebase/app";
import { getAuth, GoogleAuthProvider, inMemoryPersistence, onAuthStateChanged, setPersistence, signInWithPopup, signOut } from "firebase/auth";
import { doc, getDoc, getFirestore, writeBatch } from "firebase/firestore/lite";
import canonicalize from "canonicalize";
import { executeLiteInstruction, type InstructionContext, type LiteInstruction, type SyncFirestore } from "./sync";
export type FirebaseConfig = Record<string, string>;
type User = {
    uid: string;
    getIdToken: () => Promise<string>;
};
type Binding = {
    firebaseUid: string;
    googleSubject: string;
};
type CloudGrant = {
    challenge: string;
    purpose: string;
    destination: string;
    scopes: string[];
    expiresAt: string;
};
type WorkflowConfig = {
    project_id: string;
    workspace_id: string;
    control_database_id: string;
    runtime_database_id: string;
    session_id: string;
    session_expires_at: string;
};
type SessionBootstrap = {
    googleSubject: string;
    firebaseConfig?: FirebaseConfig | null;
    setupOnly: boolean;
    cloudGrant?: CloudGrant;
    workflowConfig?: WorkflowConfig;
    workflowRecovery?: boolean;
    pendingHistory?: Record<string, unknown>[];
    pendingTask?: {
        payload: Record<string, unknown>;
        changeset?: Record<string, unknown>;
    };
};
type BridgeHooks = {
    onDispatch?: () => void;
    onResponse?: (value: Record<string, unknown>) => void | Promise<void>;
};
type RecoveryState = "issued" | "released" | "confirmed";
type RecoveryHandle = { ownerGoogleSubject: string; firebaseUid: string; sessionId: string; operationId: string; descriptorHash: string; kind: string; state: RecoveryState };
type ConsentChallenge = { ownerGoogleSubject: string; firebaseUid: string; projectId: string; workspaceId: string; sessionId: string; previewId: string; operationId: string; kind: string; state: RecoveryState };
const q = <T extends Element>(selector: string) => document.querySelector<T>(selector);
const appElement = q<HTMLElement>("#app");
const stateElement = q<HTMLElement>("#state");
const loginButton = q<HTMLButtonElement>("#login");
const logoutButton = q<HTMLButtonElement>("#logout");
const setupOnly = q<HTMLElement>("#setup-only");
const setupSubject = q<HTMLElement>("#setup-subject");
const setupConfirm = q<HTMLButtonElement>("#setup-confirm");
const cloudGrant = q<HTMLElement>("#cloud-grant");
const cloudGrantDetails = q<HTMLElement>("#cloud-grant-details");
const consentLabel = q<HTMLElement>("#cloud-consent-label");
const consentCheckbox = q<HTMLInputElement>("#cloud-consent");
const consentButton = q<HTMLButtonElement>("#cloud-consent-submit");
const syncSection = q<HTMLElement>("#manual-sync");
const syncPreview = q<HTMLButtonElement>("#sync-preview");
const syncUpload = q<HTMLButtonElement>("#sync-upload");
const syncConsent = q<HTMLInputElement>("#sync-consent");
const syncDetails = q<HTMLElement>("#sync-details");
const taskPreview = q<HTMLButtonElement>("#task-preview");
const taskRecord = q<HTMLButtonElement>("#task-record");
const taskConsent = q<HTMLInputElement>("#task-consent");
const applyConsent = q<HTMLInputElement>("#apply-consent");
const manifestPreview = q<HTMLButtonElement>("#manifest-preview");
const manifestRead = q<HTMLButtonElement>("#manifest-read");
const manifestConsent = q<HTMLInputElement>("#manifest-consent");
const resultRead = q<HTMLButtonElement>("#result-read");
const resultDownload = q<HTMLButtonElement>("#result-download");
const resultConsent = q<HTMLInputElement>("#result-consent");
const downloadDetails = q<HTMLElement>("#download-details");
const reconcilePreviewButton = q<HTMLButtonElement>("#sync-reconcile");
const reconcileConsent = q<HTMLInputElement>("#reconcile-consent");
const reconcileRead = q<HTMLButtonElement>("#reconcile-read");
function capability(): string {
    const value = new URLSearchParams(window.location.hash.slice(1)).get("capability");
    if (!value)
        throw new Error("trusted browser capability is missing");
    return value;
}
function localSubject(): string {
    const value = appElement?.dataset.localGoogleSub?.trim();
    if (!value)
        throw new Error("verified local Google subject is missing");
    return value;
}
async function sessionBootstrap(): Promise<SessionBootstrap> {
    const response = await fetch("/api/session", { headers: { "X-Session-Capability": capability() } });
    if (!response.ok)
        throw new Error("Trusted local approval session is unavailable");
    const value = await response.json() as SessionBootstrap;
    if (!value.googleSubject)
        throw new Error("verified local Google subject is missing");
    if (value.firebaseConfig && (!value.firebaseConfig.apiKey || !value.firebaseConfig.authDomain || !value.firebaseConfig.projectId))
        throw new Error("Firebase setup configuration is invalid");
    return value;
}
async function bindFirebaseIdentity(user: User, isCurrent: () => boolean = () => true): Promise<Binding> {
    const token = await user.getIdToken();
    if (!isCurrent())
        throw new Error("Firebase account changed during sign-in");
    const response = await fetch("/api/firebase-binding", { method: "POST", headers: { "Content-Type": "application/json", "X-Session-Capability": capability() }, body: JSON.stringify({ firebaseIdToken: token }) });
    if (!response.ok)
        throw new Error("Firebase identity binding was rejected");
    const binding = await response.json() as Binding;
    if (!isCurrent())
        throw new Error("Firebase account changed during sign-in");
    if (binding.firebaseUid !== user.uid || binding.googleSubject !== localSubject())
        throw new Error("Firebase identity does not match the verified local Google account");
    return binding;
}
function validWorkflowConfig(value: unknown): value is WorkflowConfig {
    if (!value || typeof value !== "object")
        return false;
    return ["project_id", "workspace_id", "control_database_id", "runtime_database_id", "session_id", "session_expires_at"].every((key) => typeof (value as Record<string, unknown>)[key] === "string" && Boolean((value as Record<string, unknown>)[key]));
}
function detailsText(value: unknown): string {
    return JSON.stringify(value, null, 2);
}
async function bindInstructionToPreview(instruction: LiteInstruction, preview: Record<string, unknown>): Promise<void> {
    const descriptor = instruction.descriptor;
    if (!descriptor)
        throw new Error("workflow instruction descriptor is missing");
    const canonicalSame = (left: unknown, right: unknown) => canonicalize(left) === canonicalize(right);
    const descriptorKind = descriptor.kind;
    const kindsMatch = preview.kind === "reconciliation" ? descriptorKind === "reconciliation_read" : descriptorKind === preview.kind;
    if (typeof descriptorKind !== "string" || (typeof preview.kind === "string" && !kindsMatch))
        throw new Error("workflow instruction kind is not the approved preview");
    for (const key of ["project_id", "workspace_id", "firebase_uid", "session_id", "task_id", "owner_google_subject", "google_subject", "approval_type", "bound_digest_kind", "database", "destination", "policy_version", "resource_versions", "scope", "apply_scopes", "download_scopes", "fields", "result_id", "result_hash"])
        if (preview[key] !== undefined && descriptor[key] !== undefined && !canonicalSame(preview[key], descriptor[key]))
            throw new Error("workflow instruction does not match its preview");
    if (preview.payload_hash !== undefined && descriptor.payload_hash !== preview.payload_hash)
        throw new Error("history payload is not the approved preview");
    if (preview.request_hash !== undefined && descriptor.request_hash !== preview.request_hash)
        throw new Error("task request is not the approved preview");
    if (preview.bound_digest !== undefined && descriptor.bound_digest !== preview.bound_digest)
        throw new Error("task change set is not the approved preview");
    if (preview.result_id !== undefined && descriptor.result_id !== preview.result_id)
        throw new Error("result ID is not the approved preview");
    if (preview.result_hash !== undefined && descriptor.result_hash !== preview.result_hash)
        throw new Error("result hash is not the approved preview");
    if (preview.scope !== undefined && descriptor.scope !== undefined && !canonicalSame(preview.scope, descriptor.scope))
        throw new Error("result scope is not the approved preview");
    if (preview.fields !== undefined && descriptor.fields !== undefined && !canonicalSame(preview.fields, descriptor.fields))
        throw new Error("manifest fields are not the approved preview");
    for (const key of ["target_operation_id", "target_descriptor_hash", "database"])
        if (preview[key] !== undefined && descriptor[key] !== undefined && preview[key] !== descriptor[key])
            throw new Error("reconciliation target is not the approved preview");
    if (preview.paths !== undefined && (!Array.isArray(descriptor.paths) || !canonicalSame(preview.paths, descriptor.paths)))
        throw new Error("reconciliation paths are not the approved preview");
    if (descriptor.kind === "reconciliation_read" && (!Array.isArray(descriptor.paths) || !canonicalSame(descriptor.paths, instruction.reads?.map((read) => read.path) ?? [instruction.path])))
        throw new Error("reconciliation reads are not the approved preview");
    if (preview.expires_at !== undefined && descriptor.expires_at !== undefined && preview.expires_at !== descriptor.expires_at)
        throw new Error("workflow expiry is not the approved preview");
    const writes = instruction.writes ?? [];
    if (Array.isArray(preview.records)) {
        const exportData = writes.map((write) => write.data).find((data) => data.kind === "history_upload");
        if (!exportData || !canonicalSame(preview.records, exportData.events) || (typeof preview.payload_hash === "string" && exportData.payload_hash !== preview.payload_hash))
            throw new Error("history records are not the approved preview");
    }
    if (preview.request && typeof preview.request === "object") {
        const requestData = writes.map((write) => write.data).find((data) => data.request_hash !== undefined);
        if (!requestData)
            throw new Error("task request is missing from the instruction");
        const approved = { ...(preview.request as Record<string, unknown>) };
        delete approved.state;
        if (typeof requestData.canonical_payload !== "string" || !canonicalSame(approved, JSON.parse(requestData.canonical_payload)))
            throw new Error("task request is not the approved preview");
        if (typeof preview.request_hash === "string" && requestData.request_hash !== preview.request_hash)
            throw new Error("task request hash is not the approved preview");
    }
    if (preview.changeset && typeof preview.changeset === "object") {
        const changesetData = writes.map((write) => write.data).find((data) => typeof data.changeset_canonical === "string");
        if (!changesetData || !canonicalSame(preview.changeset, JSON.parse(changesetData.changeset_canonical as string)) || (typeof preview.bound_digest === "string" && changesetData.changeset_hash !== preview.bound_digest))
            throw new Error("task changeset is not the approved preview");
    }
}
async function start(): Promise<void> {
    if (!loginButton || !logoutButton || !stateElement || !setupOnly || !setupSubject || !setupConfirm || !cloudGrant || !cloudGrantDetails || !consentLabel || !consentCheckbox || !consentButton)
        return;
    const bootstrap = await sessionBootstrap();
    if (appElement)
        appElement.dataset.localGoogleSub = bootstrap.googleSubject;
    if (bootstrap.setupOnly || !bootstrap.firebaseConfig) {
        loginButton.hidden = true;
        setupOnly.hidden = false;
        setupSubject.textContent = `Verified Google subject: ${bootstrap.googleSubject}`;
        setupConfirm.addEventListener("click", async () => {
            setupConfirm.disabled = true;
            try {
                const response = await fetch("/api/setup-confirmation", { method: "POST", headers: { "Content-Type": "application/json", Origin: window.location.origin, "X-Session-Capability": capability() }, body: JSON.stringify({ googleSubject: bootstrap.googleSubject }) });
                if (!response.ok)
                    throw new Error("Local setup confirmation was rejected");
                stateElement.textContent = "Local setup confirmation recorded; Firebase and task actions remain disabled.";
            }
            catch (error) {
                stateElement.textContent = error instanceof Error ? error.message : "Setup confirmation failed";
            }
            finally {
                setupConfirm.disabled = false;
            }
        });
        return;
    }
    const firebaseConfig = bootstrap.firebaseConfig;
    if (!firebaseConfig)
        return;
    const app = initializeApp(firebaseConfig);
    const auth = getAuth(app);
    await setPersistence(auth, inMemoryPersistence);
    const provider = new GoogleAuthProvider();
    let generation = 0;
    let activeUser: User | undefined;
    let identity: InstructionContext | undefined;
    let controlDb: SyncFirestore | undefined;
    let runtimeDb: SyncFirestore | undefined;
    let uploadPreview: Record<string, unknown> | undefined;
    let taskPreviewResponse: Record<string, unknown> | undefined;
    let manifestPreviewResponse: Record<string, unknown> | undefined;
    let stagedManifest: Record<string, unknown> | undefined;
    let resultPreviewResponse: Record<string, unknown> | undefined;
    let previewRevision = 0;
    let workflowBusy = false;
    let reconciliationPreviewResponse: Record<string, unknown> | undefined;
    const unresolvedOperations = new Map<string, RecoveryHandle>();
    const consumedPreviews = new Map<string, ConsentChallenge>();
    const MAX_UNRESOLVED_OPERATIONS = 8;
    let unknownOperation: {
        operationId: string;
        descriptorHash: string;
        kind: string;
    } | undefined;
    const workflow = validWorkflowConfig(bootstrap.workflowConfig) ? bootstrap.workflowConfig : undefined;
    const clearWorkflow = () => {
        workflowBusy = false;
        previewRevision += 1;
        uploadPreview = undefined;
        taskPreviewResponse = undefined;
        manifestPreviewResponse = undefined;
        stagedManifest = undefined;
        resultPreviewResponse = undefined;
        reconciliationPreviewResponse = undefined;
        unknownOperation = undefined;
        for (const box of [syncConsent, taskConsent, applyConsent, manifestConsent, resultConsent, reconcileConsent])
            if (box)
                box.checked = false;
        for (const button of [syncUpload, taskRecord, manifestRead, resultRead, resultDownload, reconcileRead])
            if (button)
                button.disabled = true;
        for (const button of [syncPreview, taskPreview, manifestPreview])
            if (button)
                button.disabled = false;
        if (reconcilePreviewButton)
            reconcilePreviewButton.hidden = true;
        if (syncSection)
            syncSection.hidden = true;
        if (syncDetails)
            syncDetails.textContent = "";
        if (downloadDetails)
            downloadDetails.textContent = "A bounded metadata read is required before any result is displayed.";
    };
    const invalidate = (message?: string) => {
        generation += 1;
        activeUser = undefined;
        identity = undefined;
        controlDb = undefined;
        runtimeDb = undefined;
        clearWorkflow();
        cloudGrant.hidden = true;
        cloudGrantDetails.textContent = "";
        consentCheckbox.checked = false;
        consentLabel.hidden = true;
        consentButton.hidden = true;
        consentButton.disabled = false;
        logoutButton.hidden = true;
        loginButton.hidden = false;
        loginButton.disabled = false;
        if (message)
            stateElement.textContent = message;
    };
    const current = (g: number, owner: User) => g === generation && activeUser === owner && auth.currentUser === owner;
    const currentAttempt = (g: number, owner: User, revision: number) => current(g, owner) && revision === previewRevision;
    const beginWorkflow = (button: HTMLButtonElement): boolean => {
        if (workflowBusy) {
            stateElement.textContent = "Another workflow operation is in progress; wait for it to finish.";
            return false;
        }
        workflowBusy = true;
        button.disabled = true;
        return true;
    };
    const endWorkflow = (g: number, owner: User, button: HTMLButtonElement) => {
        if (current(g, owner)) {
            workflowBusy = false;
            button.disabled = false;
        }
    };
    const fenceConsent = (box: HTMLInputElement | null, button: HTMLButtonElement | null) => {
        box?.addEventListener("change", () => {
            if (!box.checked) {
                previewRevision += 1;
                if (button)
                    button.disabled = true;
            }
        });
    };
    fenceConsent(syncConsent, syncUpload);
    fenceConsent(taskConsent, taskRecord);
    fenceConsent(applyConsent, taskRecord);
    fenceConsent(manifestConsent, manifestRead);
    fenceConsent(resultConsent, resultDownload);
    fenceConsent(reconcileConsent, reconcileRead);
    const expected = () => {
        if (!identity)
            throw new Error("Firebase identity is not bound");
        return identity;
    };
    const bridgePost = async (path: string, body: Record<string, unknown>, owner: User, g: number, isValid: () => boolean = () => current(g, owner), hooks: BridgeHooks = {}): Promise<Record<string, unknown>> => {
        const token = await owner.getIdToken();
        if (!isValid())
            throw new Error("Firebase account changed during workflow operation");
        hooks.onDispatch?.();
        const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", Origin: window.location.origin, "X-Session-Capability": capability() }, body: JSON.stringify({ ...body, firebaseIdToken: token }) });
        if (!response.ok)
            throw new Error(`Workflow bridge rejected ${path}`);
        const value = await response.json() as Record<string, unknown>;
        await hooks.onResponse?.(value);
        if (!isValid())
            throw new Error("Firebase account changed during workflow operation");
        return value;
    };
    const sdkClient = (database: ReturnType<typeof getFirestore>, databaseId: string): SyncFirestore => ({ databaseId, writeBatch: () => {
            const batch = writeBatch(database);
            return { set: (ref: unknown, value: unknown) => batch.set(ref as never, value as never), commit: () => batch.commit() };
        }, doc: (...parts: string[]) => doc(database, parts[0] || "invalid", ...parts.slice(1)), getDoc: async (ref: unknown) => {
            const snapshot = await getDoc(ref as Parameters<typeof getDoc>[0]);
            return { exists: () => snapshot.exists(), data: () => (snapshot.data() ?? {}) as Record<string, unknown> };
        } });
    const renderSync = (title: string, value: unknown) => {
        if (syncDetails)
            syncDetails.textContent = `${title}
${detailsText(value)}`;
    };
    const renderDownload = (title: string, value: unknown) => {
        if (downloadDetails)
            downloadDetails.textContent = `${title}
${detailsText(value)}`;
    };
    const forgetOperation = (operationId: string) => {
        unresolvedOperations.delete(operationId);
        for (const [previewId, challenge] of consumedPreviews)
            if (challenge.operationId === operationId)
                consumedPreviews.delete(previewId);
    };
    const captureReleased = (response: Record<string, unknown>, ownerContext: InstructionContext | undefined, kind: string): boolean => {
        if (!ownerContext || typeof response.operation_id !== "string" || typeof response.descriptor_hash !== "string")
            return false;
        if (!unresolvedOperations.has(response.operation_id) && unresolvedOperations.size >= MAX_UNRESOLVED_OPERATIONS)
            return false;
        unresolvedOperations.set(response.operation_id, { ownerGoogleSubject: ownerContext.googleSubject, firebaseUid: ownerContext.firebaseUid, sessionId: ownerContext.sessionId, operationId: response.operation_id, descriptorHash: response.descriptor_hash, kind, state: "released" });
        return true;
    };
    const consentHooks = (preview: Record<string, unknown>, ownerContext: InstructionContext | undefined, kind: string, owner: User, g: number, isValid: () => boolean): BridgeHooks => ({
        onDispatch: () => {
            if (!ownerContext || typeof preview.operation_id !== "string" || typeof preview.descriptor_hash !== "string")
                throw new Error("Approved consent identity is unavailable.");
            if (consumedPreviews.has(preview.operation_id))
                throw new Error("This approved consent has already been issued; wait for its outcome or trusted recovery.");
            const retained = kind !== "reconciliation_read";
            if (retained && (unresolvedOperations.size >= MAX_UNRESOLVED_OPERATIONS || consumedPreviews.size >= MAX_UNRESOLVED_OPERATIONS))
                throw new Error("Unresolved operation capacity is full; no new consent was issued.");
            if (retained) {
                consumedPreviews.set(preview.operation_id, { ownerGoogleSubject: ownerContext.googleSubject, firebaseUid: ownerContext.firebaseUid, projectId: ownerContext.projectId, workspaceId: ownerContext.workspaceId, sessionId: ownerContext.sessionId, previewId: preview.operation_id, operationId: preview.operation_id, kind, state: "issued" });
                unresolvedOperations.set(preview.operation_id, { ownerGoogleSubject: ownerContext.googleSubject, firebaseUid: ownerContext.firebaseUid, sessionId: ownerContext.sessionId, operationId: preview.operation_id, descriptorHash: preview.descriptor_hash, kind, state: "issued" });
            }
        },
        onResponse: async (response) => {
            if (kind !== "reconciliation_read" && typeof preview.operation_id === "string" && typeof response.operation_id === "string" && typeof response.descriptor_hash === "string") {
                unresolvedOperations.delete(preview.operation_id);
                const challenge = consumedPreviews.get(preview.operation_id);
                if (challenge)
                    Object.assign(challenge, { operationId: response.operation_id, state: "released" as const });
                if (!captureReleased(response, ownerContext, kind) && ownerContext)
                    unresolvedOperations.set(preview.operation_id, { ownerGoogleSubject: ownerContext.googleSubject, firebaseUid: ownerContext.firebaseUid, sessionId: ownerContext.sessionId, operationId: preview.operation_id, descriptorHash: String(preview.descriptor_hash), kind, state: "issued" });
                if (ownerContext && !isValid() && current(g, owner))
                    await markUnknown(response, owner, g, kind, true, ownerContext);
            }
        },
    });
    const eligibleUnknown = (ownerContext: InstructionContext | undefined = identity) => ownerContext && [...unresolvedOperations.values()].find((operation) => operation.state === "confirmed" && operation.ownerGoogleSubject === ownerContext.googleSubject && operation.firebaseUid === ownerContext.firebaseUid && operation.sessionId === ownerContext.sessionId && operation.kind !== "bounded_manifest_read" && operation.kind !== "reconciliation_read");
    const showNextUnknown = (ownerContext: InstructionContext | undefined = identity) => {
        const next = eligibleUnknown(ownerContext);
        unknownOperation = next ? { operationId: next.operationId, descriptorHash: next.descriptorHash, kind: next.kind } : undefined;
        if (reconcilePreviewButton)
            reconcilePreviewButton.hidden = !next;
    };
    const issuanceNotice = (ownerContext: InstructionContext | undefined = identity) => ownerContext && [...consumedPreviews.values()].find((challenge) => challenge.state === "issued" && challenge.ownerGoogleSubject === ownerContext.googleSubject && challenge.firebaseUid === ownerContext.firebaseUid && challenge.projectId === ownerContext.projectId && challenge.workspaceId === ownerContext.workspaceId && challenge.sessionId === ownerContext.sessionId);
    const refuseConsumedPreview = (preview: Record<string, unknown> | undefined, details: HTMLElement | null): boolean => {
        if (preview && typeof preview.operation_id === "string" && consumedPreviews.has(preview.operation_id)) {
            if (details)
                details.textContent = "This approved consent has already been issued; wait for its outcome or trusted recovery.";
            return true;
        }
        return false;
    };
    const showLostConsent = (preview: Record<string, unknown> | undefined, ownerContext: InstructionContext | undefined, details: HTMLElement | null) => {
        if (!preview || !ownerContext || typeof preview.operation_id !== "string")
            return;
        const challenge = consumedPreviews.get(preview.operation_id);
        if (challenge?.state === "issued" && challenge.ownerGoogleSubject === ownerContext.googleSubject && challenge.firebaseUid === ownerContext.firebaseUid && challenge.projectId === ownerContext.projectId && challenge.workspaceId === ownerContext.workspaceId && challenge.sessionId === ownerContext.sessionId && details)
            details.textContent = "Consent response unavailable; this approved operation is retained as pending and cannot be reissued until trusted recovery.";
    };
    const recoveryDetails = (kind: string): HTMLElement | null => kind === "exact_result_download" || kind === "bounded_manifest_read" ? downloadDetails : syncDetails;
    const markUnknown = async (response: Record<string, unknown>, owner: User, g: number, kind = "writeBatch", notify = true, ownerContext: InstructionContext | undefined = identity) => {
        if (typeof response.operation_id !== "string" || typeof response.descriptor_hash !== "string" || !ownerContext)
            return;
        const handle = { ownerGoogleSubject: ownerContext.googleSubject, firebaseUid: ownerContext.firebaseUid, sessionId: ownerContext.sessionId, operationId: response.operation_id, descriptorHash: response.descriptor_hash, kind, state: "released" as const };
        unresolvedOperations.set(handle.operationId, handle);
        if (current(g, owner)) {
            let callbackConfirmed = !notify;
            if (notify) {
                try {
                    const acknowledgement = await bridgePost("/api/workflow/ack", { operationId: handle.operationId, descriptorHash: handle.descriptorHash, status: "unknown", sessionId: handle.sessionId }, owner, g);
                    if (acknowledgement.status === "acknowledged")
                        forgetOperation(handle.operationId);
                    else if (acknowledgement.status === "unknown") {
                        const confirmed = unresolvedOperations.get(handle.operationId);
                        if (confirmed)
                            confirmed.state = "confirmed";
                        for (const challenge of consumedPreviews.values())
                            if (challenge.operationId === handle.operationId)
                                challenge.state = "confirmed";
                    }
                    callbackConfirmed = acknowledgement.status === "acknowledged" || acknowledgement.status === "unknown";
                }
                catch {
                    // Keep the owner-bound handle for a later return.
                }
            }
            if (callbackConfirmed && unresolvedOperations.has(handle.operationId))
                showNextUnknown(ownerContext);
            else if (!callbackConfirmed && current(g, owner)) {
                const details = recoveryDetails(kind);
                if (details)
                    details.textContent = "Recovery remains pending because the host confirmation was unavailable; return to this account to retry the original recovery.";
            }
        }
    };
    loginButton.addEventListener("click", async () => {
        loginButton.disabled = true;
        const loginGeneration = generation;
        let loginOwner: User | undefined;
        try {
            const result = await signInWithPopup(auth, provider);
            if (generation !== loginGeneration)
                throw new Error("Firebase account changed during sign-in");
            const owner = result.user as User;
            loginOwner = owner;
            generation += 1;
            activeUser = owner;
            const boundGeneration = generation;
            clearWorkflow();
            const binding = await bindFirebaseIdentity(owner, () => generation === boundGeneration && activeUser === owner && auth.currentUser === owner);
            if (!current(boundGeneration, owner))
                throw new Error("Firebase account changed during sign-in");
            stateElement.textContent = `Signed in as ${binding.googleSubject};
Firebase UID is bound for this session.`;
            loginButton.hidden = true;
            logoutButton.hidden = false;
            consentLabel.hidden = false;
            consentButton.disabled = false;
            if (workflow) {
                const selectedTaskId = typeof bootstrap.pendingTask?.payload.task_id === "string" ? bootstrap.pendingTask.payload.task_id : typeof bootstrap.pendingHistory?.[0]?.task_id === "string" ? bootstrap.pendingHistory[0].task_id as string : "";
                identity = { googleSubject: binding.googleSubject, firebaseUid: binding.firebaseUid, projectId: workflow.project_id, workspaceId: workflow.workspace_id, taskId: selectedTaskId, sessionId: workflow.session_id, controlDatabaseId: workflow.control_database_id, runtimeDatabaseId: workflow.runtime_database_id, sessionExpiresAt: workflow.session_expires_at };
                // Recover durable UNKNOWN operations after a process/UI restart.
                // This is a local lookup; reconciliation still requires a new
                // preview and explicit consent in the current session.
                if (bootstrap.workflowRecovery === true) {
                    try {
                        const recovery = await bridgePost("/api/workflow/recovery", { sessionId: workflow.session_id }, owner, boundGeneration);
                        const operations = Array.isArray(recovery.operations) ? recovery.operations : [];
                        for (const value of operations) {
                            if (!value || typeof value !== "object")
                                continue;
                            const operation = value as Record<string, unknown>;
                            if (operation.state !== "unknown" || typeof operation.operation_id !== "string" || typeof operation.descriptor_hash !== "string" || typeof operation.kind !== "string")
                                continue;
                            unresolvedOperations.set(operation.operation_id, { ownerGoogleSubject: binding.googleSubject, firebaseUid: binding.firebaseUid, sessionId: workflow.session_id, operationId: operation.operation_id, descriptorHash: operation.descriptor_hash, kind: operation.kind, state: "confirmed" });
                        }
                    }
                    catch {
                        // A failed local lookup leaves the normal workflow fenced.
                    }
                }
                const returnedUnknown = [...unresolvedOperations.values()].find((operation) => operation.state === "released" && operation.ownerGoogleSubject === binding.googleSubject && operation.firebaseUid === binding.firebaseUid && operation.sessionId === workflow.session_id && operation.kind !== "bounded_manifest_read" && operation.kind !== "reconciliation_read");
                if (returnedUnknown) {
                    await markUnknown({ operation_id: returnedUnknown.operationId, descriptor_hash: returnedUnknown.descriptorHash }, owner, boundGeneration, returnedUnknown.kind, true, identity);
                    if (!current(boundGeneration, owner))
                        throw new Error("Firebase account changed during sign-in");
                }
                else {
                    showNextUnknown(identity);
                }
                const pendingIssuance = issuanceNotice(identity);
                if (pendingIssuance && syncDetails)
                    syncDetails.textContent = "A consent response is unavailable; this approved operation remains pending and cannot be reissued until trusted recovery.";
                controlDb = sdkClient(getFirestore(app, workflow.control_database_id), workflow.control_database_id);
                runtimeDb = sdkClient(getFirestore(app, workflow.runtime_database_id), workflow.runtime_database_id);
                if (syncSection)
                    syncSection.hidden = false;
                if (!selectedTaskId) {
                    if (taskPreview)
                        taskPreview.disabled = true;
                    if (manifestPreview)
                        manifestPreview.disabled = true;
                    if (downloadDetails)
                        downloadDetails.textContent = "No trusted task is selected; task and result controls remain disabled.";
                }
                if (syncPreview && syncUpload && syncConsent)
                    syncPreview.onclick = async () => {
                        if (syncPreview.disabled)
                            return;
                        if (!beginWorkflow(syncPreview))
                            return;
                        uploadPreview = undefined;
                        syncConsent.checked = false;
                        syncUpload.disabled = true;
                        const g = generation;
                        const revision = ++previewRevision;
                        try {
                            const records = bootstrap.pendingHistory ?? [];
                            const preview = await bridgePost("/api/workflow/preview", { kind: "history_upload", projectId: workflow.project_id, workspaceId: workflow.workspace_id, records, sessionId: workflow.session_id }, owner, g, () => currentAttempt(g, owner, revision));
                            if (!currentAttempt(g, owner, revision))
                                return;
                            uploadPreview = preview;
                            syncConsent.checked = false;
                            syncUpload.disabled = records.length === 0;
                            renderSync("History preview (no SDK calls):", preview);
                        }
                        catch (error) {
                            if (current(g, owner) && syncDetails)
                                syncDetails.textContent = error instanceof Error ? error.message : "History preview failed";
                        }
                        finally {
                            endWorkflow(g, owner, syncPreview);
                        }
                    };
                if (syncUpload && syncConsent)
                    syncUpload.onclick = async () => {
                        const g = generation;
                        const revision = previewRevision;
                        const preview = uploadPreview;
                        const ownerContext = identity && { ...identity };
                        if (!preview || !syncConsent.checked) {
                            if (syncDetails)
                                syncDetails.textContent = "Explicit history upload consent is required.";
                            return;
                        }
                        if (refuseConsumedPreview(preview, syncDetails))
                            return;
                        if (!beginWorkflow(syncUpload))
                            return;
                        let consent: Record<string, unknown> | undefined;
                        try {
                            consent = await bridgePost("/api/workflow/consent", { operationId: preview.operation_id, descriptorHash: preview.descriptor_hash, consent: true, sessionId: workflow.session_id }, owner, g, () => currentAttempt(g, owner, revision), consentHooks(preview, ownerContext, "writeBatch", owner, g, () => currentAttempt(g, owner, revision)));
                            if (!currentAttempt(g, owner, revision))
                                return;
                            const instruction = consent.instruction as LiteInstruction | undefined;
                            if (!instruction)
                                throw new Error(`History upload status: ${String(consent.status || "unknown")}`);
                            await bindInstructionToPreview(instruction, preview);
                            await executeLiteInstruction({ control: controlDb!, runtime: runtimeDb! }, instruction, expected(), () => currentAttempt(g, owner, revision));
                            if (!currentAttempt(g, owner, revision))
                                return;
                            const ack = await bridgePost("/api/workflow/ack", { operationId: consent.operation_id, descriptorHash: consent.descriptor_hash, ackId: String(preview.operation_id), sessionId: workflow.session_id }, owner, g, () => currentAttempt(g, owner, revision));
                            if (currentAttempt(g, owner, revision) && syncDetails) {
                                if (ack.status === "acknowledged") {
                                    forgetOperation(String(consent.operation_id));
                                    syncDetails.textContent = "History upload recorded.";
                                } else {
                                    syncDetails.textContent = "History upload outcome is unknown; reconcile explicitly before retrying.";
                                    await markUnknown(consent, owner, g, "writeBatch", true, ownerContext);
                                }
                            }
                        }
                        catch (error) {
                            if (consent)
                                await markUnknown(consent, owner, g, "writeBatch", true, ownerContext);
                            if (current(g, owner)) {
                                showLostConsent(preview, ownerContext, syncDetails);
                                if (syncDetails && !syncDetails.textContent.includes("retained as pending"))
                                    syncDetails.textContent = error instanceof Error ? error.message : "History upload was refused";
                            }
                        }
                        finally {
                            endWorkflow(g, owner, syncUpload);
                        }
                    };
                if (taskPreview && taskRecord && taskConsent && bootstrap.pendingTask)
                    taskPreview.onclick = async () => {
                        if (taskPreview.disabled)
                            return;
                        if (!beginWorkflow(taskPreview))
                            return;
                        taskPreviewResponse = undefined;
                        taskConsent.checked = false;
                        applyConsent && (applyConsent.checked = false);
                        taskRecord.disabled = true;
                        const g = generation;
                        const revision = ++previewRevision;
                        try {
                            const preview = await bridgePost("/api/workflow/preview", { kind: "task_request", projectId: workflow.project_id, workspaceId: workflow.workspace_id, request: bootstrap.pendingTask!.payload, changeset: bootstrap.pendingTask!.changeset, sessionId: workflow.session_id }, owner, g, () => currentAttempt(g, owner, revision));
                            if (!currentAttempt(g, owner, revision))
                                return;
                            taskPreviewResponse = preview;
                            taskConsent.checked = false;
                            if (applyConsent)
                                applyConsent.checked = false;
                            taskRecord.disabled = false;
                            renderSync("Task/change preview (no SDK calls):", preview);
                        }
                        catch (error) {
                            if (current(g, owner) && syncDetails)
                                syncDetails.textContent = error instanceof Error ? error.message : "Task preview failed";
                        }
                        finally {
                            endWorkflow(g, owner, taskPreview);
                        }
                    };
                if (taskRecord && taskConsent)
                    taskRecord.onclick = async () => {
                        const g = generation;
                        const revision = previewRevision;
                        const preview = taskPreviewResponse;
                        const ownerContext = identity && { ...identity };
                        const needsApply = Boolean(bootstrap.pendingTask?.changeset);
                        if (!preview || !taskConsent.checked || (needsApply && !applyConsent?.checked)) {
                            if (syncDetails)
                                syncDetails.textContent = needsApply ? "Both upload/run and exact apply approvals are required." : "Exact task approval is required.";
                            return;
                        }
                        if (refuseConsumedPreview(preview, syncDetails))
                            return;
                        if (!beginWorkflow(taskRecord))
                            return;
                        let consent: Record<string, unknown> | undefined;
                        try {
                            consent = await bridgePost("/api/workflow/consent", { operationId: preview.operation_id, descriptorHash: preview.descriptor_hash, consent: true, sessionId: workflow.session_id }, owner, g, () => currentAttempt(g, owner, revision), consentHooks(preview, ownerContext, "writeBatch", owner, g, () => currentAttempt(g, owner, revision)));
                            if (!currentAttempt(g, owner, revision))
                                return;
                            const instruction = consent.instruction as LiteInstruction | undefined;
                            if (!instruction)
                                throw new Error(`Task status: ${String(consent.status || "unknown")}`);
                            await bindInstructionToPreview(instruction, preview);
                            await executeLiteInstruction({ control: controlDb!, runtime: runtimeDb! }, instruction, expected(), () => currentAttempt(g, owner, revision));
                            if (!currentAttempt(g, owner, revision))
                                return;
                            const ack = await bridgePost("/api/workflow/ack", { operationId: consent.operation_id, descriptorHash: consent.descriptor_hash, ackId: String(preview.operation_id), sessionId: workflow.session_id }, owner, g, () => currentAttempt(g, owner, revision));
                            if (currentAttempt(g, owner, revision) && syncDetails) {
                                if (ack.status === "acknowledged") {
                                    forgetOperation(String(consent.operation_id));
                                    syncDetails.textContent = "Task request and approvals recorded atomically.";
                                } else {
                                    syncDetails.textContent = "Task outcome is unknown; reconcile explicitly.";
                                    await markUnknown(consent, owner, g, "writeBatch", true, ownerContext);
                                }
                            }
                        }
                        catch (error) {
                            if (consent)
                                await markUnknown(consent, owner, g, "writeBatch", true, ownerContext);
                            if (current(g, owner)) {
                                showLostConsent(preview, ownerContext, syncDetails);
                                if (syncDetails && !syncDetails.textContent.includes("retained as pending"))
                                    syncDetails.textContent = error instanceof Error ? error.message : "Task record was refused";
                            }
                        }
                        finally {
                            endWorkflow(g, owner, taskRecord);
                        }
                    };
                if (manifestPreview && manifestRead && manifestConsent)
                    manifestPreview.onclick = async () => {
                        if (manifestPreview.disabled)
                            return;
                        if (!beginWorkflow(manifestPreview))
                            return;
                        manifestPreviewResponse = undefined;
                        manifestConsent.checked = false;
                        manifestRead.disabled = true;
                        stagedManifest = undefined;
                        resultPreviewResponse = undefined;
                        if (resultConsent)
                            resultConsent.checked = false;
                        resultRead!.disabled = true;
                        resultDownload!.disabled = true;
                        const g = generation;
                        const revision = ++previewRevision;
                        try {
                            const preview = await bridgePost("/api/workflow/preview", { kind: "bounded_manifest_read", projectId: workflow.project_id, workspaceId: workflow.workspace_id, taskId: identity!.taskId, fields: ["schema_version", "kind", "result_id", "result_hash", "scope", "project_id", "workspace_id", "firebase_uid", "google_subject", "task_id", "available", "expires_at", "expires_at_ts"], sessionId: workflow.session_id }, owner, g, () => currentAttempt(g, owner, revision));
                            if (!currentAttempt(g, owner, revision))
                                return;
                            manifestPreviewResponse = preview;
                            stagedManifest = undefined;
                            resultPreviewResponse = undefined;
                            manifestConsent.checked = false;
                            if (resultConsent)
                                resultConsent.checked = false;
                            if (resultRead)
                                resultRead.disabled = true;
                            if (resultDownload)
                                resultDownload.disabled = true;
                            manifestRead.disabled = false;
                            renderDownload("Manifest preview (no read):", preview);
                        }
                        catch (error) {
                            if (current(g, owner) && downloadDetails)
                                downloadDetails.textContent = error instanceof Error ? error.message : "Manifest preview failed";
                        }
                        finally {
                            endWorkflow(g, owner, manifestPreview);
                        }
                    };
                if (manifestRead && manifestConsent)
                    manifestRead.onclick = async () => {
                        const g = generation;
                        const revision = previewRevision;
                        const ownerContext = identity && { ...identity };
                        if (!manifestPreviewResponse || !manifestConsent.checked) {
                            if (downloadDetails)
                                downloadDetails.textContent = "Explicit manifest consent is required.";
                            return;
                        }
                        if (refuseConsumedPreview(manifestPreviewResponse, downloadDetails))
                            return;
                        if (!beginWorkflow(manifestRead))
                            return;
                        try {
                            const consent = await bridgePost("/api/workflow/consent", { operationId: manifestPreviewResponse.operation_id, descriptorHash: manifestPreviewResponse.descriptor_hash, consent: true, sessionId: workflow.session_id }, owner, g, () => currentAttempt(g, owner, revision), consentHooks(manifestPreviewResponse, ownerContext, "bounded_manifest_read", owner, g, () => currentAttempt(g, owner, revision)));
                            if (!currentAttempt(g, owner, revision))
                                return;
                            const instruction = consent.instruction as LiteInstruction | undefined;
                            if (!instruction)
                                throw new Error("Manifest instruction is unavailable");
                            await bindInstructionToPreview(instruction, manifestPreviewResponse);
                            const manifest = await executeLiteInstruction({ control: controlDb!, runtime: runtimeDb! }, instruction, expected(), () => currentAttempt(g, owner, revision));
                            if (!currentAttempt(g, owner, revision))
                                return;
                            const manifestAck = await bridgePost("/api/workflow/ack", { operationId: consent.operation_id, descriptorHash: consent.descriptor_hash, manifest, sessionId: workflow.session_id }, owner, g, () => currentAttempt(g, owner, revision));
                            if (!currentAttempt(g, owner, revision))
                                return;
                            if (manifestAck.status !== "acknowledged")
                                throw new Error("Manifest acknowledgement was not accepted");
                            forgetOperation(String(consent.operation_id));
                            stagedManifest = manifest;
                            resultRead!.disabled = false;
                            renderDownload("Staged manifest (exact result requires a separate preview and consent):", manifest);
                        }
                        catch (error) {
                            if (current(g, owner)) {
                                showLostConsent(manifestPreviewResponse, ownerContext, downloadDetails);
                                manifestPreviewResponse = undefined;
                                manifestConsent.checked = false;
                                manifestRead.disabled = true;
                                if (manifestPreview)
                                    manifestPreview.disabled = false;
                                if (downloadDetails && !downloadDetails.textContent.includes("retained as pending"))
                                    downloadDetails.textContent = error instanceof Error ? error.message : "Manifest read failed";
                            }
                        }
                        finally {
                            endWorkflow(g, owner, manifestRead);
                        }
                    };
                if (resultRead && resultConsent)
                    resultRead.onclick = async () => {
                        if (resultRead.disabled)
                            return;
                        if (!beginWorkflow(resultRead))
                            return;
                        resultPreviewResponse = undefined;
                        resultConsent.checked = false;
                        resultDownload!.disabled = true;
                        const g = generation;
                        const revision = ++previewRevision;
                        if (!stagedManifest || !manifestPreviewResponse) {
                            if (downloadDetails)
                                downloadDetails.textContent = "A staged manifest is required.";
                            resultRead.disabled = false;
                            return;
                        }
                        try {
                            const preview = await bridgePost("/api/workflow/preview", { kind: "exact_result_download", projectId: workflow.project_id, workspaceId: workflow.workspace_id, taskId: identity!.taskId, scope: stagedManifest.scope, metadataDescriptorHash: manifestPreviewResponse.descriptor_hash, sessionId: workflow.session_id }, owner, g, () => currentAttempt(g, owner, revision));
                            if (!currentAttempt(g, owner, revision))
                                return;
                            resultPreviewResponse = preview;
                            resultConsent.checked = false;
                            resultDownload!.disabled = false;
                            renderDownload("Exact result preview (no read):", preview);
                        }
                        catch (error) {
                            if (current(g, owner) && downloadDetails)
                                downloadDetails.textContent = error instanceof Error ? error.message : "Result preview failed";
                        }
                        finally {
                            endWorkflow(g, owner, resultRead);
                        }
                    };
                if (resultDownload && resultConsent)
                    resultDownload.onclick = async () => {
                        const g = generation;
                        const revision = previewRevision;
                        const ownerContext = identity && { ...identity };
                        if (!resultPreviewResponse || !resultConsent.checked) {
                            if (downloadDetails)
                                downloadDetails.textContent = "Separate exact result consent is required.";
                            return;
                        }
                        if (refuseConsumedPreview(resultPreviewResponse, downloadDetails))
                            return;
                        if (!beginWorkflow(resultDownload))
                            return;
                        let consent: Record<string, unknown> | undefined;
                        try {
                            consent = await bridgePost("/api/workflow/consent", { operationId: resultPreviewResponse.operation_id, descriptorHash: resultPreviewResponse.descriptor_hash, consent: true, sessionId: workflow.session_id }, owner, g, () => currentAttempt(g, owner, revision), consentHooks(resultPreviewResponse, ownerContext, "exact_result_download", owner, g, () => currentAttempt(g, owner, revision)));
                            if (!currentAttempt(g, owner, revision))
                                return;
                            const instruction = consent.instruction as LiteInstruction | undefined;
                            if (!instruction)
                                throw new Error("Result instruction is unavailable");
                            await bindInstructionToPreview(instruction, resultPreviewResponse);
                            const result = await executeLiteInstruction({ control: controlDb!, runtime: runtimeDb! }, instruction, expected(), () => currentAttempt(g, owner, revision));
                            if (!currentAttempt(g, owner, revision))
                                return;
                            const ack = await bridgePost("/api/workflow/ack", { operationId: consent.operation_id, descriptorHash: consent.descriptor_hash, result, sessionId: workflow.session_id }, owner, g, () => currentAttempt(g, owner, revision));
                            if (!currentAttempt(g, owner, revision))
                                return;
                            if (ack.status === "acknowledged") {
                                forgetOperation(String(consent.operation_id));
                                renderDownload("Exact result downloaded and imported:", result);
                            } else {
                                if (downloadDetails)
                                    downloadDetails.textContent = "Result outcome is unknown; reconcile explicitly.";
                            await markUnknown(consent, owner, g, "exact_result_download", true, ownerContext);
                            }
                        }
                        catch (error) {
                            if (consent && !(error instanceof Error && error.message.includes("account changed")))
                            await markUnknown(consent, owner, g, "exact_result_download", true, ownerContext);
                            if (current(g, owner)) {
                                showLostConsent(resultPreviewResponse, ownerContext, downloadDetails);
                                if (downloadDetails && !downloadDetails.textContent.includes("retained as pending"))
                                    downloadDetails.textContent = error instanceof Error ? error.message : "Result download failed";
                            }
                        }
                        finally {
                            endWorkflow(g, owner, resultDownload);
                        }
                    };
                if (reconcilePreviewButton && reconcileRead && reconcileConsent)
                    reconcilePreviewButton.onclick = async () => {
                        if (reconcilePreviewButton.disabled)
                            return;
                        if (!beginWorkflow(reconcilePreviewButton))
                            return;
                        reconciliationPreviewResponse = undefined;
                        reconcileConsent.checked = false;
                        reconcileRead.disabled = true;
                        const g = generation;
                        const revision = ++previewRevision;
                        if (!unknownOperation) {
                            if (syncDetails)
                                syncDetails.textContent = "No unresolved operation is available for reconciliation.";
                            reconcilePreviewButton.disabled = false;
                            return;
                        }
                        try {
                            const preview = await bridgePost("/api/workflow/preview", { kind: "reconciliation", projectId: workflow.project_id, workspaceId: workflow.workspace_id, operationId: unknownOperation.operationId, descriptorHash: unknownOperation.descriptorHash, sessionId: workflow.session_id }, owner, g, () => currentAttempt(g, owner, revision));
                            if (!currentAttempt(g, owner, revision))
                                return;
                            reconcilePreviewButton.dataset.previewId = String(preview.operation_id);
                            reconcilePreviewButton.dataset.descriptorHash = String(preview.descriptor_hash);
                            reconciliationPreviewResponse = structuredClone(preview);
                            reconcileConsent.checked = false;
                            reconcileRead.disabled = false;
                            renderSync("Reconciliation preview (exact paths):", preview);
                        }
                        catch (error) {
                            if (current(g, owner) && syncDetails)
                                syncDetails.textContent = error instanceof Error ? error.message : "Reconciliation preview failed";
                        }
                        finally {
                            endWorkflow(g, owner, reconcilePreviewButton);
                        }
                    };
                if (reconcileRead && reconcileConsent && reconcilePreviewButton)
                    reconcileRead.onclick = async () => {
                        const g = generation;
                        const revision = previewRevision;
                        const ownerContext = identity && { ...identity };
                        const preview = reconciliationPreviewResponse;
                        const operationId = reconcilePreviewButton.dataset.previewId;
                        const descriptorHash = reconcilePreviewButton.dataset.descriptorHash;
                        if (!operationId || !descriptorHash || !preview || !reconcileConsent.checked) {
                            if (syncDetails)
                                syncDetails.textContent = "Explicit reconciliation read consent is required.";
                            return;
                        }
                        if (refuseConsumedPreview({ operation_id: operationId }, syncDetails))
                            return;
                        if (!beginWorkflow(reconcileRead))
                            return;
                        try {
                            const consent = await bridgePost("/api/workflow/consent", { operationId, descriptorHash, consent: true, sessionId: workflow.session_id }, owner, g, () => currentAttempt(g, owner, revision), consentHooks({ operation_id: operationId, descriptor_hash: descriptorHash }, ownerContext, "reconciliation_read", owner, g, () => currentAttempt(g, owner, revision)));
                            if (!currentAttempt(g, owner, revision))
                                return;
                            const instruction = consent.instruction as LiteInstruction | undefined;
                            if (!instruction)
                                throw new Error("Reconciliation instruction is unavailable");
                            await bindInstructionToPreview(instruction, reconciliationPreviewResponse!);
                            const observed = await executeLiteInstruction({ control: controlDb!, runtime: runtimeDb! }, instruction, { ...expected(), reconciliationTargetKind: unknownOperation?.kind }, () => currentAttempt(g, owner, revision));
                            if (!currentAttempt(g, owner, revision))
                                return;
                        const result = await bridgePost("/api/workflow/reconcile", { operationId: consent.operation_id, descriptorHash: consent.descriptor_hash, observed, sessionId: workflow.session_id }, owner, g, () => currentAttempt(g, owner, revision));
                        if (result.status === "reconciled" || result.status === "acknowledged") {
                            forgetOperation(unknownOperation?.operationId ?? "");
                            forgetOperation(String(consent.operation_id));
                            reconciliationPreviewResponse = undefined;
                            showNextUnknown(ownerContext);
                        }
                        if (currentAttempt(g, owner, revision) && syncDetails)
                                syncDetails.textContent = `Reconciliation status: ${String(result.status || "unknown")}.`;
                        }
                        catch (error) {
                            if (current(g, owner)) {
                                reconciliationPreviewResponse = undefined;
                                reconcileConsent.checked = false;
                                reconcileRead.disabled = true;
                                if (syncDetails)
                                    syncDetails.textContent = error instanceof Error ? error.message : "Reconciliation failed";
                                showNextUnknown(ownerContext);
                            }
                        }
                        finally {
                            endWorkflow(g, owner, reconcileRead);
                            if (current(g, owner) && !reconciliationPreviewResponse)
                                reconcileRead.disabled = true;
                        }
                    };
            }
            if (bootstrap.cloudGrant) {
                cloudGrant.hidden = false;
                consentButton.hidden = false;
                cloudGrantDetails.textContent = `Purpose: ${bootstrap.cloudGrant.purpose};
destination: ${bootstrap.cloudGrant.destination};
full verified scopes: ${bootstrap.cloudGrant.scopes.join(", ")};
expires: ${bootstrap.cloudGrant.expiresAt}`;
            }
        }
        catch (error) {
            const message = error instanceof Error ? error.message : "Sign-in failed";
            if (loginOwner && activeUser === loginOwner && current(generation, loginOwner)) {
                stateElement.textContent = message;
                await signOut(auth).catch(() => undefined);
            }
            else if (generation === loginGeneration || !activeUser)
                stateElement.textContent = message;
        }
        finally {
            if (generation === loginGeneration || !activeUser)
                loginButton.disabled = false;
        }
    });
    logoutButton.addEventListener("click", async () => {
        invalidate("Signed out; no Firebase identity remains in this session.");
        await signOut(auth).catch(() => undefined);
    });
    onAuthStateChanged(auth, (user) => {
        if (activeUser && user !== activeUser)
            invalidate(user ? "Firebase account changed; workflow state was cleared." : "Signed out; workflow state was cleared.");
    });
    consentButton.addEventListener("click", async () => {
        const owner = activeUser;
        const g = generation;
        if (!consentCheckbox.checked || !owner || !bootstrap.cloudGrant) {
            stateElement.textContent = "Explicit human consent is required.";
            return;
        }
        consentButton.disabled = true;
        try {
            const token = await owner.getIdToken();
            if (!current(g, owner))
                return;
            const response = await fetch("/api/cloud-grant-consent", { method: "POST", headers: { "Content-Type": "application/json", Origin: window.location.origin, "X-Session-Capability": capability() }, body: JSON.stringify({ firebaseIdToken: token, googleSubject: localSubject(), ...bootstrap.cloudGrant, consent: true }) });
            if (!response.ok)
                throw new Error("Cloud grant consent was rejected");
            if (current(g, owner))
                stateElement.textContent = "Cloud grant consent recorded for this account and purpose.";
        }
        catch (error) {
            if (current(g, owner))
                stateElement.textContent = error instanceof Error ? error.message : "Consent failed";
        }
        finally {
            if (current(g, owner))
                consentButton.disabled = false;
        }
    });
}
start().catch((error: unknown) => {
    if (stateElement)
        stateElement.textContent = error instanceof Error ? error.message : "Setup is unavailable";
});
