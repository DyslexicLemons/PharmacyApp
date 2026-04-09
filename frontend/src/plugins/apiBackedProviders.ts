/**
 * Default plugin implementations backed by the Pharmacy API.
 *
 * These call the backend endpoints that are themselves provider-agnostic
 * (e.g. GET /drugs/search delegates to whichever DrugCatalogProvider is
 * registered on the server).
 *
 * Pass a `getToken` function so providers can read the current auth token
 * from the Zustand store at call time without importing it directly — this
 * keeps the plugin layer independent of the auth implementation.
 */

import type {
  ClaimResult,
  ClaimSubmissionParams,
  DrugCatalogProvider,
  DrugPricingResult,
  DrugSearchResult,
  InsuranceAdjudicationGateway,
  InteractionWarning,
  PluginRegistry,
} from './types';

const V1 = '/api/v1';

// ---------------------------------------------------------------------------
// Internal fetch helper
// ---------------------------------------------------------------------------

async function apiFetch<T>(
  path: string,
  token: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${V1}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      ...(options.headers ?? {}),
    },
  });

  if (res.status === 401) {
    window.dispatchEvent(new CustomEvent('auth:expired'));
    throw new Error('Session expired — please log in again');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({})) as { detail?: string };
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Drug catalog
// ---------------------------------------------------------------------------

function makeApiDrugCatalog(getToken: () => string | null): DrugCatalogProvider {
  return {
    async search(query, limit = 20): Promise<DrugSearchResult[]> {
      const token = getToken();
      if (!token) return [];
      const params = new URLSearchParams({ q: query, limit: String(limit) });
      return apiFetch<DrugSearchResult[]>(`/drugs/search?${params}`, token);
    },

    async getPricing(ndc): Promise<DrugPricingResult> {
      const token = getToken();
      if (!token) throw new Error('Not authenticated');
      return apiFetch<DrugPricingResult>(`/drugs/${encodeURIComponent(ndc)}/pricing`, token);
    },

    async checkAvailability(ndc, quantity): Promise<boolean> {
      const token = getToken();
      if (!token) return false;
      const params = new URLSearchParams({ quantity: String(quantity) });
      const result = await apiFetch<{ available: boolean }>(
        `/drugs/${encodeURIComponent(ndc)}/availability?${params}`,
        token,
      );
      return result.available;
    },

    async checkInteractions(ndcs): Promise<InteractionWarning[]> {
      const token = getToken();
      if (!token) return [];
      const params = new URLSearchParams({ ndcs: ndcs.join(',') });
      return apiFetch<InteractionWarning[]>(`/drugs/interactions?${params}`, token);
    },
  };
}

// ---------------------------------------------------------------------------
// Insurance adjudication
// ---------------------------------------------------------------------------

function makeApiInsuranceGateway(getToken: () => string | null): InsuranceAdjudicationGateway {
  return {
    async adjudicateRefill(params: ClaimSubmissionParams): Promise<ClaimResult> {
      const token = getToken();
      if (!token) throw new Error('Not authenticated');
      return apiFetch<ClaimResult>(
        `/refills/${params.refillId}/adjudicate`,
        token,
        { method: 'POST' },
      );
    },
  };
}

// ---------------------------------------------------------------------------
// Factory — call once at app startup in main.tsx
// ---------------------------------------------------------------------------

/**
 * Build the default PluginRegistry backed by the Pharmacy API.
 *
 * @param getToken  Returns the current JWT from the auth store (or null if
 *                  the user is not logged in).  Evaluated at call time so the
 *                  registry itself doesn't need to be rebuilt on login/logout.
 *
 * Example (main.tsx):
 *
 *   import { useAuthStore } from '@/stores/authStore';
 *   import { createDefaultRegistry } from '@/plugins/apiBackedProviders';
 *
 *   const registry = createDefaultRegistry(() => useAuthStore.getState().token);
 */
export function createDefaultRegistry(getToken: () => string | null): PluginRegistry {
  return {
    drugCatalog: makeApiDrugCatalog(getToken),
    insuranceGateway: makeApiInsuranceGateway(getToken),
  };
}
