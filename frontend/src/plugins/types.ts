/**
 * Plugin interface contracts for the Pharmacy app.
 *
 * The core application only imports from this file — never from concrete
 * provider implementations.  Swap providers at startup by passing a
 * different PluginRegistry to <PluginProvider>.
 */

// ---------------------------------------------------------------------------
// Drug Catalog
// ---------------------------------------------------------------------------

export interface DrugSearchResult {
  drugId?: number;
  ndc: string;
  name: string;
  form: string;
  strength: string;
  manufacturer: string;
  unitCost: number;
  inStock: boolean;
  quantityOnHand?: number;
}

export interface DrugPricingResult {
  ndc: string;
  unitCost: number;
  awp?: number;
  source: string;
}

export interface InteractionWarning {
  severity: 'major' | 'moderate' | 'minor';
  description: string;
  ndcsInvolved: string[];
}

export interface DrugCatalogProvider {
  search(query: string, limit?: number): Promise<DrugSearchResult[]>;
  getPricing(ndc: string): Promise<DrugPricingResult>;
  checkAvailability(ndc: string, quantity: number): Promise<boolean>;
  checkInteractions(ndcs: string[]): Promise<InteractionWarning[]>;
}

// ---------------------------------------------------------------------------
// Insurance / Adjudication
// ---------------------------------------------------------------------------

export interface EligibilityResult {
  isEligible: boolean;
  memberId: string;
  groupId: string;
  planName: string;
  copayAmount?: number;
  deductibleRemaining?: number;
  coverageTier?: number;
  rejectionCode?: string;
  rejectionReason?: string;
}

export interface ClaimResult {
  approved: boolean;
  claimId?: string;
  amountDue: number;
  amountPaid: number;
  requiresPriorAuth: boolean;
  rejectionCode?: string;
  rejectionReason?: string;
  provider?: string;
}

export interface ClaimSubmissionParams {
  refillId: number;
}

export interface InsuranceAdjudicationGateway {
  adjudicateRefill(params: ClaimSubmissionParams): Promise<ClaimResult>;
}

// ---------------------------------------------------------------------------
// Registry
// ---------------------------------------------------------------------------

export interface PluginRegistry {
  drugCatalog: DrugCatalogProvider;
  insuranceGateway: InsuranceAdjudicationGateway;
}
