import type {
  Refill,
  Patient,
  PatientSearchResult,
  PatientInsurance,
  Prescription,
  Drug,
  StockEntry,
  Shipment,
  Prescriber,
  InsuranceCompany,
  User,
  AuditLogEntry,
  SystemConfig,
  BillingResult,
  LoginResponse,
  PaginatedResponse,
} from "@/types";

const V1 = '/api/v1';

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/** Error thrown by handleResponse — includes the HTTP status code. */
export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

function authHeaders(token: string): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  };
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (res.status === 401) {
    window.dispatchEvent(new CustomEvent('auth:expired'));
    throw new ApiError(401, 'Session expired — please log in again');
  }
  if (!res.ok) {
    const error = await res.json().catch(() => ({})) as { detail?: string };
    throw new ApiError(res.status, error.detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Auth (no token required)
// ---------------------------------------------------------------------------

export async function loginUser(username: string, password: string): Promise<LoginResponse> {
  const res = await fetch(`${V1}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({})) as { detail?: string };
    throw new Error(error.detail || 'Invalid credentials');
  }
  return res.json() as Promise<LoginResponse>;
}

export async function loginWithCode(code: string): Promise<LoginResponse> {
  const res = await fetch(`${V1}/login/code`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({})) as { detail?: string };
    throw new Error(error.detail || 'Invalid or expired code');
  }
  return res.json() as Promise<LoginResponse>;
}

// ---------------------------------------------------------------------------
// Refills
// ---------------------------------------------------------------------------

export async function fetchQueue(
  state: string | null,
  token: string,
  limit = 15,
  offset = 0,
  sortBy = "due",
  sortDir = "asc",
): Promise<PaginatedResponse<Refill>> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    sort_by: sortBy,
    sort_dir: sortDir,
  });
  if (state && state !== 'ALL') params.set('state', state);
  const res = await fetch(`${V1}/refills?${params}`, { headers: authHeaders(token) });
  return handleResponse(res);
}

export async function advanceRx(
  id: number,
  payload: Record<string, unknown>,
  token: string,
): Promise<Refill> {
  const res = await fetch(`${V1}/refills/${id}/advance`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
  return handleResponse(res);
}

export async function getRefill(id: number, token: string, queue?: string): Promise<Refill> {
  const params = queue && queue !== 'ALL' ? `?queue=${encodeURIComponent(queue)}` : '';
  const res = await fetch(`${V1}/refills/${id}${params}`, { headers: authHeaders(token) });
  return handleResponse(res);
}

export async function editRefill(
  id: number,
  data: Record<string, unknown>,
  token: string,
): Promise<Refill> {
  const res = await fetch(`${V1}/refills/${id}/edit`, {
    method: 'PATCH',
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

export async function getRefillHist(
  token: string,
  limit = 100,
  offset = 0,
): Promise<PaginatedResponse<Refill> | Refill[]> {
  const res = await fetch(`${V1}/refill_hist?limit=${limit}&offset=${offset}`, {
    headers: authHeaders(token),
  });
  return handleResponse(res);
}

export async function checkConflict(
  patientId: number,
  drugId: number,
  token: string,
): Promise<{ has_conflict: boolean; active_refills: { id: number; state: string; due_date: string; quantity: number }[]; recent_fills: { id: number; sold_date: string; days_supply: number; quantity: number }[]; message?: string }> {
  const res = await fetch(
    `${V1}/refills/check_conflict?patient_id=${patientId}&drug_id=${drugId}`,
    { headers: authHeaders(token) },
  );
  return handleResponse(res);
}

export async function uploadJsonPrescription(
  data: Record<string, unknown>,
  token: string,
): Promise<Refill> {
  const res = await fetch(`${V1}/refills/upload_json`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

export async function createManualPrescription(
  data: Record<string, unknown>,
  token: string,
): Promise<Refill> {
  const res = await fetch(`${V1}/refills/create_manual`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Patients
// ---------------------------------------------------------------------------

export async function searchPatients(q: string, token: string): Promise<PatientSearchResult[]> {
  const res = await fetch(`${V1}/patients/search?name=${encodeURIComponent(q)}`, {
    headers: authHeaders(token),
  });
  return handleResponse(res);
}

export async function getPatient(id: number, token: string): Promise<Patient> {
  const res = await fetch(`${V1}/patients/${id}`, { headers: authHeaders(token) });
  return handleResponse(res);
}

export async function getPatients(
  token: string,
  limit = 50,
  offset = 0,
): Promise<PaginatedResponse<PatientSearchResult>> {
  const res = await fetch(`${V1}/patients?limit=${limit}&offset=${offset}`, {
    headers: authHeaders(token),
  });
  return handleResponse(res);
}

export async function createPatient(
  data: Record<string, unknown>,
  token: string,
): Promise<Patient> {
  const res = await fetch(`${V1}/patients`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

export async function updatePatient(
  id: number,
  data: Record<string, unknown>,
  token: string,
): Promise<Patient> {
  const res = await fetch(`${V1}/patients/${id}`, {
    method: 'PATCH',
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

export async function getPatientInsurance(
  patientId: number,
  token: string,
): Promise<PatientInsurance[]> {
  const res = await fetch(`${V1}/patients/${patientId}/insurance`, {
    headers: authHeaders(token),
  });
  return handleResponse(res);
}

export async function addPatientInsurance(
  patientId: number,
  data: Record<string, unknown>,
  token: string,
): Promise<PatientInsurance> {
  const res = await fetch(`${V1}/patients/${patientId}/insurance`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Prescriptions
// ---------------------------------------------------------------------------

export async function getPrescription(id: number, token: string): Promise<Prescription> {
  const res = await fetch(`${V1}/prescriptions/${id}`, { headers: authHeaders(token) });
  return handleResponse(res);
}

export async function fillScript(
  prescriptionId: number,
  data: Record<string, unknown>,
  token: string,
): Promise<Refill> {
  const res = await fetch(`${V1}/prescriptions/${prescriptionId}/fill`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

export async function updatePrescription(
  id: number,
  data: Record<string, unknown>,
  token: string,
): Promise<Prescription> {
  const res = await fetch(`${V1}/prescriptions/${id}`, {
    method: 'PATCH',
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

export async function holdPrescription(id: number, token: string): Promise<Prescription> {
  const res = await fetch(`${V1}/prescriptions/${id}/hold`, {
    method: 'POST',
    headers: authHeaders(token),
  });
  return handleResponse(res);
}

export async function inactivatePrescription(
  id: number,
  username: string,
  password: string,
  token: string,
): Promise<Prescription> {
  const res = await fetch(`${V1}/prescriptions/${id}/inactivate`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify({ username, password }),
  });
  return handleResponse(res);
}

export async function updatePrescriptionPicture(
  id: number,
  file: File,
  token: string,
): Promise<Prescription> {
  // Multipart file upload — do NOT set Content-Type, browser sets it with boundary
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${V1}/prescriptions/${id}/picture`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` },
    body: formData,
  });
  return handleResponse(res);
}

export async function createPrescription(
  data: Record<string, unknown>,
  token: string,
): Promise<Prescription> {
  const res = await fetch(`${V1}/prescriptions`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

export async function lockPrescription(id: number, token: string): Promise<void> {
  const res = await fetch(`${V1}/prescriptions/${id}/lock`, {
    method: 'POST',
    headers: authHeaders(token),
  });
  return handleResponse(res);
}

export async function unlockPrescription(id: number, token: string): Promise<void> {
  await fetch(`${V1}/prescriptions/${id}/lock`, {
    method: 'DELETE',
    headers: authHeaders(token),
  });
  // 204 No Content — ignore response body
}

export async function checkPrescriptionLock(
  id: number,
  token: string,
): Promise<{ locked: boolean; locked_by: string | null }> {
  const res = await fetch(`${V1}/prescriptions/${id}/lock`, {
    headers: authHeaders(token),
  });
  return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Drugs & stock
// ---------------------------------------------------------------------------

export async function getDrugs(
  token: string,
  limit = 100,
  offset = 0,
): Promise<PaginatedResponse<Drug> | Drug[]> {
  const res = await fetch(`${V1}/drugs?limit=${limit}&offset=${offset}`, {
    headers: authHeaders(token),
  });
  return handleResponse(res);
}

export async function getStock(
  token: string,
  limit = 100,
  offset = 0,
): Promise<PaginatedResponse<StockEntry> | StockEntry[]> {
  const res = await fetch(`${V1}/stock?limit=${limit}&offset=${offset}`, {
    headers: authHeaders(token),
  });
  return handleResponse(res);
}

export async function createShipment(
  data: Record<string, unknown>,
  token: string,
): Promise<Shipment> {
  const res = await fetch(`${V1}/shipments`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

export async function getShipments(
  token: string,
  limit = 20,
  offset = 0,
): Promise<PaginatedResponse<Shipment> | Shipment[]> {
  const res = await fetch(`${V1}/shipments?limit=${limit}&offset=${offset}`, {
    headers: authHeaders(token),
  });
  return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Prescribers
// ---------------------------------------------------------------------------

export async function getPrescribers(
  token: string,
  limit = 100,
  offset = 0,
): Promise<PaginatedResponse<Prescriber> | Prescriber[]> {
  const res = await fetch(`${V1}/prescribers?limit=${limit}&offset=${offset}`, {
    headers: authHeaders(token),
  });
  return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Insurance & billing
// ---------------------------------------------------------------------------

export async function getInsuranceCompanies(token: string): Promise<InsuranceCompany[]> {
  const res = await fetch(`${V1}/insurance_companies`, { headers: authHeaders(token) });
  return handleResponse(res);
}

export async function calculateBilling(
  data: Record<string, unknown>,
  token: string,
): Promise<BillingResult> {
  const res = await fetch(`${V1}/billing/calculate`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Users (admin)
// ---------------------------------------------------------------------------

export async function getUsers(token: string): Promise<User[]> {
  const res = await fetch(`${V1}/users`, { headers: authHeaders(token) });
  return handleResponse(res);
}

export async function createUser(
  data: { username: string; password: string; is_admin: boolean },
  token: string,
): Promise<User> {
  const res = await fetch(`${V1}/users`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------

export async function getSystemConfig(token: string): Promise<SystemConfig> {
  const res = await fetch(`${V1}/config`, { headers: authHeaders(token) });
  return handleResponse(res);
}

export async function updateSystemConfig(
  data: SystemConfig,
  token: string,
): Promise<SystemConfig> {
  const res = await fetch(`${V1}/config`, {
    method: 'PUT',
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

export async function generateTestPrescriptions(
  token: string,
): Promise<{ prescriptions_created: number; active_refills_created: number; sold_prescriptions: number }> {
  const res = await fetch(`${V1}/commands/generate_test_prescriptions`, {
    method: 'POST',
    headers: authHeaders(token),
  });
  return handleResponse(res);
}

export async function adminGeneratePrescribers(
  count: number,
  token: string,
): Promise<{ prescribers_created: number }> {
  const res = await fetch(`${V1}/commands/generate_prescribers`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify({ count }),
  });
  return handleResponse(res);
}

export async function adminGeneratePatients(
  count: number,
  token: string,
): Promise<{ patients_created: number }> {
  const res = await fetch(`${V1}/commands/generate_patients`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify({ count }),
  });
  return handleResponse(res);
}

export async function adminGeneratePrescriptions(
  count: number,
  state: string,
  token: string,
): Promise<{ prescriptions_created: number; refills_created: number; refill_history_created: number; state: string }> {
  const res = await fetch(`${V1}/commands/generate_prescriptions`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify({ count, state }),
  });
  return handleResponse(res);
}

export async function adminClearPrescriptions(
  token: string,
): Promise<{ refills_deleted: number; refill_history_deleted: number; prescriptions_deleted: number }> {
  const res = await fetch(`${V1}/commands/clear_prescriptions`, {
    method: 'POST',
    headers: authHeaders(token),
  });
  return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Simulation control
// ---------------------------------------------------------------------------

export async function updateSimulationConfig(
  token: string,
  patch: {
    simulation_enabled?: boolean;
    sim_arrival_rate?: number;
    sim_reject_rate?: number;
  },
): Promise<import('@/types').SystemConfig> {
  const res = await fetch(`${V1}/config`, {
    method: 'PUT',
    headers: authHeaders(token),
    body: JSON.stringify(patch),
  });
  return handleResponse(res);
}

export interface QueuePriorityBucket {
  pastdue: number;
  stat: number;
  high: number;
  normal: number;
}

export interface QueueSummary {
  generated_at: string;
  refills_by_state: Record<string, number>;
  priority_breakdown: Record<string, QueuePriorityBucket>;
  total_active: number;
  overdue_scheduled: number;
  expiring_soon_30d: number;
}

export async function fetchQueueSummary(token: string): Promise<QueueSummary> {
  const res = await fetch(`${V1}/queue-summary`, { headers: authHeaders(token) });
  return handleResponse(res);
}

export async function getAuditLog(
  token: string,
  limit = 100,
  offset = 0,
  { action, username, prescriptionId }: { action?: string; username?: string; prescriptionId?: number } = {},
): Promise<PaginatedResponse<AuditLogEntry> | AuditLogEntry[]> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (action) params.set('action', action);
  if (username) params.set('username', username);
  if (prescriptionId) params.set('prescription_id', String(prescriptionId));
  const res = await fetch(`${V1}/audit_log?${params}`, { headers: authHeaders(token) });
  return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Simulation workers
// ---------------------------------------------------------------------------

export async function listSimWorkers(token: string): Promise<import('@/types').SimWorker[]> {
  const res = await fetch(`${V1}/sim-workers`, { headers: authHeaders(token) });
  return handleResponse(res);
}

export async function createSimWorker(
  token: string,
  body: { name: string; role: string; speed: number; is_active: boolean },
): Promise<import('@/types').SimWorker> {
  const res = await fetch(`${V1}/sim-workers`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(body),
  });
  return handleResponse(res);
}

export async function updateSimWorker(
  token: string,
  id: number,
  patch: { name?: string; speed?: number; is_active?: boolean },
): Promise<import('@/types').SimWorker> {
  const res = await fetch(`${V1}/sim-workers/${id}`, {
    method: 'PUT',
    headers: authHeaders(token),
    body: JSON.stringify(patch),
  });
  return handleResponse(res);
}

export async function deleteSimWorker(token: string, id: number): Promise<void> {
  const res = await fetch(`${V1}/sim-workers/${id}`, {
    method: 'DELETE',
    headers: authHeaders(token),
  });
  return handleResponse(res);
}

export async function seedSimWorkers(token: string): Promise<{ seeded: number; message: string }> {
  const res = await fetch(`${V1}/commands/seed_sim_workers`, {
    method: 'POST',
    headers: authHeaders(token),
  });
  return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Return to Stock (RTS)
// ---------------------------------------------------------------------------

export async function rtsLookup(
  refillId: number,
  token: string,
): Promise<import('@/types').RTSLookup> {
  const res = await fetch(`${V1}/rts/lookup/${refillId}`, { headers: authHeaders(token) });
  return handleResponse(res);
}

export async function rtsLookupByRx(
  prescriptionId: number,
  token: string,
): Promise<import('@/types').RTSLookup> {
  const res = await fetch(`${V1}/rts/lookup/rx/${prescriptionId}`, { headers: authHeaders(token) });
  return handleResponse(res);
}

export async function processRTS(
  refillId: number,
  token: string,
): Promise<import('@/types').ReturnToStock> {
  const res = await fetch(`${V1}/rts`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify({ refill_id: refillId }),
  });
  return handleResponse(res);
}

export async function getRTSHistory(
  token: string,
  limit = 20,
  offset = 0,
): Promise<PaginatedResponse<import('@/types').ReturnToStock>> {
  const res = await fetch(`${V1}/rts?limit=${limit}&offset=${offset}`, { headers: authHeaders(token) });
  return handleResponse(res);
}
