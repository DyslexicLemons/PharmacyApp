/**
 * React context for the plugin registry.
 *
 * Wrap the application in <PluginProvider registry={...}> once at the root
 * (main.tsx).  Components then pull individual providers via the hooks below
 * without knowing which concrete implementation is active.
 *
 * Usage in a component:
 *
 *   const catalog = useDrugCatalog();
 *   const results = await catalog.search('metformin');
 *
 *   const gateway = useInsuranceGateway();
 *   const claim   = await gateway.adjudicateRefill({ refillId: 42 });
 */

import React, { createContext, useContext } from 'react';
import type { DrugCatalogProvider, InsuranceAdjudicationGateway, PluginRegistry } from './types';

const PluginContext = createContext<PluginRegistry | null>(null);

export function PluginProvider({
  registry,
  children,
}: {
  registry: PluginRegistry;
  children: React.ReactNode;
}) {
  return (
    <PluginContext.Provider value={registry}>
      {children}
    </PluginContext.Provider>
  );
}

function useRegistry(): PluginRegistry {
  const ctx = useContext(PluginContext);
  if (!ctx) {
    throw new Error(
      'useRegistry: No PluginProvider found in the component tree. ' +
      'Wrap your app in <PluginProvider registry={...}> in main.tsx.'
    );
  }
  return ctx;
}

export function useDrugCatalog(): DrugCatalogProvider {
  return useRegistry().drugCatalog;
}

export function useInsuranceGateway(): InsuranceAdjudicationGateway {
  return useRegistry().insuranceGateway;
}
