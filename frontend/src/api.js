const BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';
const V1 = `${BASE}/api/v1`;

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function authHeaders(token) {
    return {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
    };
}

async function handleResponse(res) {
    if (res.status === 401) {
        window.dispatchEvent(new CustomEvent('auth:expired'));
        throw new Error('Session expired — please log in again');
    }
    if (!res.ok) {
        const error = await res.json().catch(() => ({}));
        throw new Error(error.detail || `HTTP ${res.status}`);
    }
    return res.json();
}

// ---------------------------------------------------------------------------
// Auth (no token required)
// ---------------------------------------------------------------------------

export async function loginUser(username, password) {
    const res = await fetch(`${V1}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
        const error = await res.json().catch(() => ({}));
        throw new Error(error.detail || 'Invalid credentials');
    }
    return res.json();
}

export async function loginWithCode(code) {
    const res = await fetch(`${V1}/login/code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
    });
    if (!res.ok) {
        const error = await res.json().catch(() => ({}));
        throw new Error(error.detail || 'Invalid or expired code');
    }
    return res.json();
}

// ---------------------------------------------------------------------------
// Refills
// ---------------------------------------------------------------------------

export async function fetchQueue(state, token, limit = 100, offset = 0) {
    const params = new URLSearchParams({ limit, offset });
    if (state && state !== 'ALL') params.set('state', state);
    const res = await fetch(`${V1}/refills?${params}`, { headers: authHeaders(token) });
    return handleResponse(res);
}

export async function advanceRx(id, payload = {}, token) {
    const res = await fetch(`${V1}/refills/${id}/advance`, {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify(payload),
    });
    return handleResponse(res);
}

export async function getRefill(id, token) {
    const res = await fetch(`${V1}/refills/${id}`, { headers: authHeaders(token) });
    return handleResponse(res);
}

export async function editRefill(id, data, token) {
    const res = await fetch(`${V1}/refills/${id}/edit`, {
        method: 'PATCH',
        headers: authHeaders(token),
        body: JSON.stringify(data),
    });
    return handleResponse(res);
}

export async function getRefillHist(token, limit = 100, offset = 0) {
    const res = await fetch(`${V1}/refill_hist?limit=${limit}&offset=${offset}`, {
        headers: authHeaders(token),
    });
    return handleResponse(res);
}

export async function checkConflict(patientId, drugId, token) {
    const res = await fetch(`${V1}/refills/check_conflict?patient_id=${patientId}&drug_id=${drugId}`, {
        headers: authHeaders(token),
    });
    return handleResponse(res);
}

export async function uploadJsonPrescription(data, token) {
    const res = await fetch(`${V1}/refills/upload_json`, {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify(data),
    });
    return handleResponse(res);
}

export async function createManualPrescription(data, token) {
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

export async function searchPatients(q, token) {
    const res = await fetch(`${V1}/patients/search?name=${encodeURIComponent(q)}`, {
        headers: authHeaders(token),
    });
    return handleResponse(res);
}

export async function getPatient(id, token) {
    const res = await fetch(`${V1}/patients/${id}`, { headers: authHeaders(token) });
    return handleResponse(res);
}

export async function getPatients(token, limit = 50, offset = 0) {
    const res = await fetch(`${V1}/patients?limit=${limit}&offset=${offset}`, {
        headers: authHeaders(token),
    });
    return handleResponse(res);
}

export async function createPatient(data, token) {
    const res = await fetch(`${V1}/patients`, {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify(data),
    });
    return handleResponse(res);
}

export async function updatePatient(id, data, token) {
    const res = await fetch(`${V1}/patients/${id}`, {
        method: 'PATCH',
        headers: authHeaders(token),
        body: JSON.stringify(data),
    });
    return handleResponse(res);
}

export async function getPatientInsurance(patientId, token) {
    const res = await fetch(`${V1}/patients/${patientId}/insurance`, {
        headers: authHeaders(token),
    });
    return handleResponse(res);
}

export async function addPatientInsurance(patientId, data, token) {
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

export async function getPrescription(id, token) {
    const res = await fetch(`${V1}/prescriptions/${id}`, { headers: authHeaders(token) });
    return handleResponse(res);
}

export async function fillScript(prescriptionId, data, token) {
    const res = await fetch(`${V1}/prescriptions/${prescriptionId}/fill`, {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify(data),
    });
    return handleResponse(res);
}

export async function updatePrescription(id, data, token) {
    const res = await fetch(`${V1}/prescriptions/${id}`, {
        method: 'PATCH',
        headers: authHeaders(token),
        body: JSON.stringify(data),
    });
    return handleResponse(res);
}

export async function updatePrescriptionPicture(id, file, token) {
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

export async function createPrescription(data, token) {
    const res = await fetch(`${V1}/prescriptions`, {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify(data),
    });
    return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Drugs & stock
// ---------------------------------------------------------------------------

export async function getDrugs(token, limit = 100, offset = 0) {
    const res = await fetch(`${V1}/drugs?limit=${limit}&offset=${offset}`, {
        headers: authHeaders(token),
    });
    return handleResponse(res);
}

export async function getStock(token, limit = 100, offset = 0) {
    const res = await fetch(`${V1}/stock?limit=${limit}&offset=${offset}`, {
        headers: authHeaders(token),
    });
    return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Prescribers
// ---------------------------------------------------------------------------

export async function getPrescribers(token, limit = 100, offset = 0) {
    const res = await fetch(`${V1}/prescribers?limit=${limit}&offset=${offset}`, {
        headers: authHeaders(token),
    });
    return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Insurance & billing
// ---------------------------------------------------------------------------

export async function getInsuranceCompanies(token) {
    const res = await fetch(`${V1}/insurance_companies`, { headers: authHeaders(token) });
    return handleResponse(res);
}

export async function calculateBilling(data, token) {
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

export async function getUsers(token) {
    const res = await fetch(`${V1}/users`, { headers: authHeaders(token) });
    return handleResponse(res);
}

export async function createUser(data, token) {
    // data: { username, password, is_admin }
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

export async function generateTestPrescriptions(token) {
    const res = await fetch(`${V1}/commands/generate_test_prescriptions`, {
        method: 'POST',
        headers: authHeaders(token),
    });
    return handleResponse(res);
}

export async function getAuditLog(token, limit = 100, offset = 0, action = null) {
    const params = new URLSearchParams({ limit, offset });
    if (action) params.set('action', action);
    const res = await fetch(`${V1}/audit_log?${params}`, { headers: authHeaders(token) });
    return handleResponse(res);
}
