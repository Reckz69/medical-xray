const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const TOKEN_KEY = "denoisex_access_token";

/* ============================================
   TYPES (mirror backend/gateway/schemas)
   ============================================ */

export interface User {
  id: string;
  email: string;
  name: string;
  role: string;
  organization_id: string;
}

export interface TokenPair {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface ScanOutput {
  type: string;
  mime_type: string;
  size_bytes: number;
  checksum: string | null;
}

export interface Scan {
  id: string;
  organization_id: string;
  user_id: string;
  status: string;
  original_name: string;
  format: string;
  size_bytes: number;
  content_hash: string;
  width: number;
  height: number;
  created_at: string;
  deleted_at: string | null;
  model_id: string | null;
  noise_variance: number | null;
  routing_message: string | null;
  was_bypassed: boolean;
  processing_time_ms: number | null;
  completed_at: string | null;
  outputs: ScanOutput[];
}

export interface ScanList {
  items: Scan[];
  total: number;
  offset: number;
  limit: number;
}

export interface UploadScanResponse {
  scan: Scan;
  job_id: string | null;
  job_status: string | null;
  duplicate: boolean;
  message: string | null;
}

export interface Job {
  id: string;
  scan_id: string;
  status: string;
  attempt: number;
  max_attempts: number;
  worker_id: string | null;
  error: string | null;
  trace_id: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  next_retry_at: string | null;
  scan_status: string;
}

export interface OutputUrl {
  output_type: string;
  download_url: string;
  content_type: string;
  expires_in: number;
}

/* Non-enveloped /health/* responses (raw JSON, never wrapped). */

export interface ReadyResponse {
  status: "ok" | "degraded";
  checks: Record<string, string>;
}

export type HealthChecks = Record<string, string>;

export interface WorkerHealth {
  alive: boolean;
  last_heartbeat: string | null;
  model_loaded: boolean;
  model_name: string | null;
  model_version: string | null;
  gpu: string | null;
}

export interface InfraHealth {
  status: "ok" | "degraded";
  checked_at: string;
  app_version: string;
  git_sha: string;
  model_version: string;
  checks: HealthChecks;
  worker: WorkerHealth;
  rabbitmq: {
    queue_name: string;
    queue_depth: number | null;
  };
}

export const JOB_STATUS = {
  QUEUED: "QUEUED",
  RUNNING: "RUNNING",
  FAILED: "FAILED",
  RETRYING: "RETRYING",
  COMPLETED: "COMPLETED",
  CANCELLED: "CANCELLED",
} as const;

export const SCAN_STATUS = {
  QUEUED: "QUEUED",
  RUNNING: "RUNNING",
  COMPLETED: "COMPLETED",
  FAILED: "FAILED",
  CANCELLED: "CANCELLED",
} as const;

export const OUTPUT_TYPES = {
  ORIGINAL: "ORIGINAL",
  NOISE_MAP: "NOISE_MAP",
  UNET: "UNET",
  ENHANCED: "ENHANCED",
} as const;

export const OUTPUT_LABELS: Record<string, { label: string; description: string }> = {
  ORIGINAL: { label: "Original", description: "Raw uploaded scan" },
  NOISE_MAP: { label: "Noise Map", description: "Isolated residual noise" },
  UNET: { label: "U-Net", description: "N2N U-Net denoised" },
  ENHANCED: { label: "Enhanced", description: "Final clinical output" },
};

const TERMINAL_SCAN_STATUSES: string[] = [
  SCAN_STATUS.COMPLETED,
  SCAN_STATUS.FAILED,
  SCAN_STATUS.CANCELLED,
];

/* ============================================
   ERROR TYPE
   ============================================ */

interface ApiErrorBody {
  code?: string;
  message?: string;
  trace_id?: string;
  status?: number;
}

export class ApiError extends Error {
  code: string;
  status: number;
  traceId: string | null;

  constructor(message: string, code: string, status: number, traceId: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.traceId = traceId;
  }
}

function isApiErrorBody(body: unknown): body is ApiErrorBody {
  return typeof body === "object" && body !== null;
}

/* ============================================
   TOKEN STORAGE
   ============================================ */

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

export function hasToken(): boolean {
  return getToken() !== null;
}

/* ============================================
   HTTP HELPERS
   ============================================ */

interface Envelope<T> {
  success: boolean;
  data: T;
  meta: Record<string, unknown>;
  trace_id: string | null;
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: BodyInit | null;
}

async function request<T>(
  path: string,
  options: RequestOptions = {},
  retryOnUnauthorized = true
): Promise<T> {
  const headers = new Headers(options.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });

  if (!response.ok) {
    if (response.status === 401 && token && retryOnUnauthorized) {
      const refreshed = await refreshSession();
      if (refreshed) return request<T>(path, options, false);
    }

    const body = (await response.json().catch(() => null)) as unknown;
    const message = isApiErrorBody(body) && body.message
      ? body.message
      : `Request failed (${response.status})`;
    const code = isApiErrorBody(body) && body.code ? body.code : "request_failed";
    const traceId = isApiErrorBody(body) && body.trace_id ? body.trace_id : null;
    throw new ApiError(message, code, response.status, traceId);
  }

  if (response.status === 204) return undefined as T;

  const json = (await response.json()) as Envelope<T>;
  return json.data;
}

/* ============================================
   HEALTH
   ============================================ */

export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/health/live`, { method: "GET" });
    return response.ok;
  } catch {
    return false;
  }
}

/** Readiness probe — returns the raw (non-enveloped) body or null on network error. */
export async function checkReady(): Promise<ReadyResponse | null> {
  try {
    const response = await fetch(`${API_BASE_URL}/health/ready`, { method: "GET" });
    return (await response.json().catch(() => null)) as ReadyResponse | null;
  } catch {
    return null;
  }
}

/**
 * Operational health matrix (gateway, infra deps, worker heartbeat, queue depth).
 * Non-enveloped and auth-gated in production. Attach a bearer token when present
 * so the caller can fall back to /health/ready on a 401.
 *
 * Returns the full body even when degraded (HTTP 503 carries a parseable JSON
 * payload with worker/queue data); throws only when no payload is available.
 */
export async function checkInfra(token?: string | null): Promise<InfraHealth> {
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_BASE_URL}/health/infra`, {
    method: "GET",
    headers,
  });
  const body = (await response.json().catch(() => null)) as InfraHealth | null;
  if (response.status === 401 || response.status === 403) {
    throw new ApiError(
      "Health matrix requires authorization",
      "unauthorized",
      response.status
    );
  }
  if (body === null) {
    throw new ApiError(
      `Health check failed (${response.status})`,
      "health_check_failed",
      response.status
    );
  }
  return body;
}

/* ============================================
   AUTH
   ============================================ */

export async function login(email: string, password: string): Promise<User> {
  const data = await request<TokenPair>(
    "/api/v1/auth/login",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    },
    false
  );
  setToken(data.access_token);
  return data.user;
}

export async function register(input: {
  name: string;
  email: string;
  password: string;
  organization_name?: string;
}): Promise<User> {
  const data = await request<TokenPair>(
    "/api/v1/auth/register",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
    false
  );
  setToken(data.access_token);
  return data.user;
}

export async function refreshSession(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (!response.ok) {
      setToken(null);
      return false;
    }
    const json = (await response.json()) as Envelope<TokenPair>;
    setToken(json.data.access_token);
    return true;
  } catch {
    setToken(null);
    return false;
  }
}

export async function logout(): Promise<void> {
  try {
    await request<void>("/api/v1/auth/logout", { method: "POST" }, false);
  } finally {
    setToken(null);
  }
}

export async function me(): Promise<User> {
  return request<User>("/api/v1/auth/me", { method: "GET" });
}

/** Placeholder password-reset flow — backend acknowledges the request. */
export async function forgotPassword(email: string): Promise<void> {
  await request<void>(
    "/api/v1/auth/forgot-password",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    },
    false
  );
}

/* ============================================
   SCANS
   ============================================ */

export async function uploadScan(file: File): Promise<UploadScanResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return request<UploadScanResponse>("/api/v1/scans", {
    method: "POST",
    body: formData,
  });
}

export async function listScans(offset = 0, limit = 20): Promise<ScanList> {
  return request<ScanList>(`/api/v1/scans?offset=${offset}&limit=${limit}`, {
    method: "GET",
  });
}

export async function getScan(scanId: string): Promise<Scan> {
  return request<Scan>(`/api/v1/scans/${scanId}`, { method: "GET" });
}

export async function getOutputUrl(scanId: string, outputType: string): Promise<OutputUrl> {
  return request<OutputUrl>(`/api/v1/scans/${scanId}/outputs/${outputType}/url`, {
    method: "GET",
  });
}

/** Soft-delete a scan (returns 204; the item disappears from list/gallery). */
export async function deleteScan(scanId: string): Promise<void> {
  return request<void>(`/api/v1/scans/${scanId}`, { method: "DELETE" });
}

/* ============================================
   JOBS (polling)
   ============================================ */

export async function getJob(jobId: string): Promise<Job> {
  return request<Job>(`/api/v1/jobs/${jobId}`, { method: "GET" });
}

export function isScanTerminal(status: string): boolean {
  return TERMINAL_SCAN_STATUSES.includes(status);
}

export interface JobPoll {
  promise: Promise<Job>;
  cancel: () => void;
}

export function pollJob(
  jobId: string,
  onUpdate: (job: Job) => void,
  options: { intervalMs?: number; timeoutMs?: number } = {}
): JobPoll {
  const { intervalMs = 1500, timeoutMs = 120000 } = options;
  const deadline = Date.now() + timeoutMs;
  let cancelled = false;

  const promise = new Promise<Job>((resolve, reject) => {
    const tick = async () => {
      try {
        const job = await getJob(jobId);
        if (cancelled) return;
        onUpdate(job);
        if (isScanTerminal(job.scan_status)) {
          resolve(job);
          return;
        }
        if (Date.now() > deadline) {
          reject(new ApiError("Timed out waiting for processing to finish", "job_timeout", 0));
          return;
        }
        window.setTimeout(() => void tick(), intervalMs);
      } catch (error) {
        if (!cancelled) reject(error);
      }
    };

    void tick();
  });

  return {
    promise,
    cancel: () => {
      cancelled = true;
    },
  };
}
