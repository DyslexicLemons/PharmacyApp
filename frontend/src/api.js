const API = import.meta.env.VITE_API_BASE || 'http://localhost:8000';


export async function fetchQueue(state) {
    const url = state ? `${API}/refills?state=${encodeURIComponent(state)}` : `${API}/refills`;
    const res = await fetch(url);
    if (!res.ok) throw new Error('Failed to fetch refills');
    return res.json();
}


export async function advanceRx(id) {
    const res = await fetch(`${API}/refills/${id}/advance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
    });
    if (!res.ok) throw new Error('Failed to advance prescription');
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