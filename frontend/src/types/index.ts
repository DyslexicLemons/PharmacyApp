// ---------------------------------------------------------------------------
// Refill state machine
// ---------------------------------------------------------------------------

export type RxState =
  | "QT"
  | "QV1"
  | "QP"
  | "QV2"
  | "READY"
  | "HOLD"
  | "SCHEDULED"
  | "REJECTED"
  | "SOLD"
  | "RTS";

/** States where Approve & Advance is valid */
export const APPROVABLE_STATES: RxState[] = ["QT", "QV1", "QP", "QV2", "READY", "HOLD", "SCHEDULED"];
/** States where Hold is valid */
export const HOLDABLE_STATES: RxState[] = ["QT", "QV1", "QP", "QV2"];
/** States where pharmacist reject (return to QT) is valid */
export const REJECTABLE_STATES: RxState[] = ["QV1"];
/** States where Edit is valid */
export const EDITABLE_STATES: RxState[] = ["QT", "QP", "HOLD"];

// ---------------------------------------------------------------------------
// Domain models (mirror Pydantic response schemas)
// ---------------------------------------------------------------------------

export interface Drug {
  id: number;
  drug_name: string;
  ndc: string | null;
  manufacturer: string;
  cost: number | string;
  description: string | null;
  drug_class: number;
  niosh: boolean;
  /** Physical/delivery form — drives SIG code translation defaults */
  drug_form: string | null;
}

export interface Patient {
  id: number;
  first_name: string;
  last_name: string;
  dob: string;
  address: string;
  prescriptions?: Prescription[];
}

/** Redacted patient record returned by list/search endpoints (no DOB or address). */
export interface PatientSearchResult {
  id: number;
  first_name: string;
  last_name: string;
  dob?: string;
}

export interface Prescriber {
  id: number;
  first_name: string;
  last_name: string;
  npi: string;
  phone_number: string;
  address: string;
}

export interface Prescription {
  id: number;
  date_received?: string | null;
  expiration_date?: string | null;
  daw_code?: number;
  original_quantity?: number;
  remaining_quantity: number;
  instructions?: string | null;
  picture?: string | null;
  prescriber?: Prescriber | null;
  patient?: Patient;
  drug_id?: number;
  drug?: { drug_name: string; [key: string]: unknown };
  is_inactive?: boolean;
  is_expired?: boolean;
  latest_refill?: unknown;
  picture_url?: string | null;
  prescriber_id?: number;
  patient_id?: number;
}

export interface Refill {
  id: number;
  state: RxState;
  quantity: number;
  days_supply: number;
  total_cost: number | string;
  source: string;
  bin_number: string | null;
  drug_id: number;
  drug: Drug;
  patient: Patient;
  prescription: Prescription;
  rejection_reason: string | null;
  rejected_by: string | null;
  rejection_date: string | null;
  triage_reason: string | null;
  priority?: string;
  due_date?: string | null;
}

export interface StockEntry {
  drug_id: number;
  drug_name: string;
  quantity: number;
  drug: Drug;
  package_size: number;
  rts_count: number;
  rts_quantity: number;
}

export interface Shipment {
  id: number;
  received_date: string;
  drug_id: number;
  drug_name?: string;
  quantity: number;
  lot_number: string | null;
  expiration_date: string | null;
}

export interface InsuranceCompany {
  id: number;
  plan_id: string;
  plan_name: string;
  bin_number: string | null;
  pcn: string | null;
  phone_number: string | null;
}

export interface PatientInsurance {
  id: number;
  patient_id: number;
  insurance_company_id: number;
  insurance_company?: InsuranceCompany;
  member_id: string;
  group_number: string | null;
  rx_bin: string | null;
  rx_pcn: string | null;
  is_active?: boolean;
}

export interface RTSLookup {
  refill_id: number;
  drug_name: string;
  ndc: string | null;
  quantity: number;
  patient_name: string;
  bin_number: number | null;
  completed_date: string | null;
}

export interface ReturnToStock {
  id: number;
  refill_id: number;
  drug_id: number;
  drug: Drug;
  quantity: number;
  returned_at: string;
  returned_by: string;
}

export interface AuditLogEntry {
  id: number;
  timestamp: string;
  action: string;
  entity_type: string;
  entity_id: number | null;
  prescription_id: number | null;
  user_id: number | null;
  username: string | null;
  details: string | null;
}

export interface SystemConfig {
  bin_count: number;
  simulation_enabled: boolean;
  sim_arrival_rate: number;
  sim_reject_rate: number;
}

export interface SimWorkerRefillContext {
  id: number;
  prescription_id: number;
  drug_name: string;
  patient_name: string;
}

export interface SimWorker {
  id: number;
  name: string;
  role: "technician" | "pharmacist";
  is_active: boolean;
  speed: number;
  current_station: "triage" | "fill" | "verify_1" | "verify_2" | "window" | null;
  busy_until: string | null;
  task_started_at: string | null;
  current_refill_id: number | null;
  current_refill: SimWorkerRefillContext | null;
  progress_pct: number | null;
  secs_remaining: number | null;
}

export interface User {
  id: number;
  username: string;
  is_admin: boolean;
  role: "admin" | "pharmacist" | "technician";
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface AuthUser {
  username: string;
  isAdmin: boolean;
}

export interface QuickCode {
  code: string;
  expiresAt: number;
}

export interface LoginResponse {
  username: string;
  is_admin: boolean;
  access_token: string | null;
  quick_code?: string;
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
}

export interface BillingResult {
  total_cost: number;
  insurance_paid: number | null;
  patient_pays: number;
  copay: number | null;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------

export type NotificationType = "info" | "error" | "warning" | "success";

export interface Notification {
  id: number;
  message: string;
  type: NotificationType;
  fading?: boolean;
}

// ---------------------------------------------------------------------------
// App routing
// ---------------------------------------------------------------------------

export type RouteState =
  | { view: "HOME" }
  | { view: "QUEUE"; state: string; page?: number }
  | { view: "REFILL_DETAIL"; refillId: number; fromQueueState?: string }
  | { view: "EDIT_REFILL"; refillId: number }
  | { view: "PATIENT"; pid: number; page?: number }
  | { view: "VIEW_PRESCRIPTION"; prescription: Prescription; patientName: string; patientId: number }
  | { view: "FILL_SCRIPT"; prescription: Prescription; patientName: string; fromPid: number }
  | { view: "DRUGS"; page?: number }
  | { view: "PATIENTS"; page?: number }
  | { view: "STOCK"; page?: number }
  | { view: "REFILL_HIST"; page?: number }
  | { view: "PRESCRIBERS"; page?: number }
  | { view: "CREATE_PRESCRIPTION"; patientId?: number }
  | { view: "NO_MATCH"; query: string }
  | { view: "PATIENT_SELECT"; patients: PatientSearchResult[]; query: string }
  | { view: "CREATE_PATIENT"; prefillLast: string; prefillFirst: string }
  | { view: "REGISTER" }
  | { view: "USER_MANAGEMENT" }
  | { view: "AUDIT_LOG"; page?: number }
  | { view: "SHIPMENT" }
  | { view: "SHIPMENT_HIST"; page?: number }
  | { view: "SYSTEM_SETTINGS" }
  | { view: "ADMIN_CONSOLE" }
  | { view: "RTS_LOOKUP"; refillId?: number }
  | { view: "RTS_HIST"; page?: number }
  | { view: "WORKER_DASHBOARD" }
  | { view: "PROVIDER_INFO" }
  | { view: "EDIT_PATIENT"; pid: number };

// ---------------------------------------------------------------------------
// Dashboard analytics
// ---------------------------------------------------------------------------

export interface DashboardStateSummary { state: string; count: number }
export interface DashboardDailyThroughput { date: string; count: number; revenue: number }
export interface DashboardTopDrug { drug_name: string; dispense_count: number; total_revenue: number }
export interface DashboardPriorityBreakdown { priority: string; count: number }
export interface DashboardInsuranceSplit {
  insured: number;
  uninsured: number;
  insured_revenue: number;
  uninsured_revenue: number;
}
export interface DashboardStats {
  total_patients: number;
  total_active_prescriptions: number;
  total_active_refills: number;
  total_fills_completed: number;
  queue_states: DashboardStateSummary[];
  daily_throughput: DashboardDailyThroughput[];
  top_drugs: DashboardTopDrug[];
  priority_breakdown: DashboardPriorityBreakdown[];
  total_revenue: number;
  total_insurance_paid: number;
  total_copay_collected: number;
  insurance_split: DashboardInsuranceSplit;
  total_rejected: number;
  rejection_rate_pct: number;
  overdue_active_refills: number;
  late_fills_in_range: number;
  fills_with_due_date_in_range: number;
  late_fill_rate_pct: number;
}
