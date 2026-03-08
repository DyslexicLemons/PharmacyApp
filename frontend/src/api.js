const API = import.meta.env.VITE_API_BASE || 'http://localhost:8000';


export async function fetchQueue(state) {
    const url = state ? `${API}/refills?state=${encodeURIComponent(state)}` : `${API}/refills`;
    const res = await fetch(url);
    if (!res.ok) throw new Error('Failed to fetch refills');
    return res.json();
}


export async function advanceRx(id, payload = {}) {
    const res = await fetch(`${API}/refills/${id}/advance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || 'Failed to advance prescription');
    }
    return res.json();
}


export async function searchPatients(q) {
    const res = await fetch(`${API}/patients/search?name=${encodeURIComponent(q)}`);
    if (!res.ok) throw new Error('Search failed');
    return res.json();
}


export async function getPatient(id) {
    const res = await fetch(`${API}/patients/${id}`);
    if (!res.ok) throw new Error('Patient fetch failed');
    return res.json();
}

export async function getPatients() {
    const res = await fetch(`${API}/patients`);
    if (!res.ok) throw new Error('Patient fetch failed');
    return res.json();
}

export async function getDrugs() {
    const res = await fetch(`${API}/drugs`);
    if (!res.ok) throw new Error('Unable to get Drugs :(');
    return res.json();
}

export async function getStock() {
    const res = await fetch(`${API}/stock`);
    if (!res.ok) throw new Error('Unable to get Stock :(');
    return res.json();
}

export async function getPrescribers() {
    const res = await fetch(`${API}/prescribers`);
    if (!res.ok) throw new Error('Unable to get Prescribers :(');
    return res.json();
}

export async function getRefillHist() {
    const res = await fetch(`${API}/refill_hist`);
    if (!res.ok) throw new Error('Unable to get refill Hist :(');
    return res.json();
}

export async function fillScript(prescriptionId, data) {
    const res = await fetch(`${API}/prescriptions/${prescriptionId}/fill`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || 'Failed to create fill');
    }
    return res.json();
}

export async function generateTestPrescriptions() {
    const res = await fetch(`${API}/commands/generate_test_prescriptions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    });
    if (!res.ok) throw new Error('Failed to generate test prescriptions');
    return res.json();
}

export async function getInsuranceCompanies() {
    const res = await fetch(`${API}/insurance_companies`);
    if (!res.ok) throw new Error('Unable to get insurance companies');
    return res.json();
}

export async function getPatientInsurance(patientId) {
    const res = await fetch(`${API}/patients/${patientId}/insurance`);
    if (!res.ok) throw new Error('Unable to get patient insurance');
    return res.json();
}

export async function addPatientInsurance(patientId, data) {
    const res = await fetch(`${API}/patients/${patientId}/insurance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || 'Failed to add insurance');
    }
    return res.json();
}

export async function calculateBilling(data) {
    const res = await fetch(`${API}/billing/calculate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || 'Failed to calculate billing');
    }
    return res.json();
}