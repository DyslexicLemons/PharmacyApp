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
  | "SOLD";

/** States where Approve & Advance is valid */
export const APPROVABLE_STATES: RxState[] = ["QT", "QV1", "QP", "QV2", "READY", "HOLD", "SCHEDULED"];
/** States where Hold is valid */
export const HOLDABLE_STATES: RxState[] = ["QT", "QV1", "QP", "QV2"];
/** States where Reject is valid */
export const REJECTABLE_STATES: RxState[] = ["QV1", "HOLD"];
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
  description: string | null;
  drug_class: number;
  niosh: boolean;
}

export interface Patient {
  id: number;
  first_name: string;
  last_name: string;
  dob: string;
  address: string;
  prescriptions?: Prescription[];
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
  date_received: string | null;
  expiration_date: string | null;
  daw_code: number;
  original_quantity: number;
  remaining_quantity: number;
  instructions: string | null;
  picture: string | null;
  prescriber: Prescriber | null;
  patient: Patient;
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
}

export interface StockEntry {
  drug_id: number;
  drug_name: string;
  quantity: number;
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
  name: string;
  bin: string;
  pcn: string | null;
  phone: string | null;
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
  [key: string]: string | number | boolean | null;
}

export interface User {
  id: number;
  username: string;
  is_admin: boolean;
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
  | { view: "PATIENT_SELECT"; patients: Patient[]; query: string }
  | { view: "CREATE_PATIENT"; prefillLast: string; prefillFirst: string }
  | { view: "REGISTER" }
  | { view: "USER_MANAGEMENT" }
  | { view: "AUDIT_LOG"; page?: number }
  | { view: "SHIPMENT" }
  | { view: "SHIPMENT_HIST"; page?: number }
  | { view: "SYSTEM_SETTINGS" };
