/**
 * DataContext — previously fetched drugs and prescribers with raw useEffect +
 * useState. Now backed by React Query, which gives us automatic caching,
 * background refetching, and deduplication for free.
 *
 * The context value shape is intentionally identical to the old one so every
 * consumer (PrescriptionForm, EditRefillView, etc.) works without changes.
 */
import { createContext, useContext, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { getDrugs, getPrescribers } from "@/api";
import { AuthContext } from "./AuthContext";
import type { Drug, Prescriber, PaginatedResponse } from "@/types";

interface DataContextValue {
  drugs: Drug[];
  prescribers: Prescriber[];
  loadingDrugs: boolean;
  loadingPrescribers: boolean;
  errorDrugs: string;
  errorPrescribers: string;
}

export const DataContext = createContext<DataContextValue>({
  drugs: [],
  prescribers: [],
  loadingDrugs: false,
  loadingPrescribers: false,
  errorDrugs: "",
  errorPrescribers: "",
});

function unwrapItems<T>(data: PaginatedResponse<T> | T[]): T[] {
  return Array.isArray(data) ? data : data.items;
}

export const DataProvider = ({ children }: { children: ReactNode }) => {
  const { isAuthenticated, token } = useContext(AuthContext);

  const {
    data: drugs = [],
    isLoading: loadingDrugs,
    error: drugsError,
  } = useQuery({
    queryKey: ["drugs", token],
    queryFn: () => getDrugs(token!),
    enabled: isAuthenticated && !!token,
    // Unwrap paginated response shape or plain array
    select: unwrapItems<Drug>,
    // Drugs change rarely — keep the cache fresh for 5 minutes
    staleTime: 5 * 60 * 1000,
  });

  const {
    data: prescribers = [],
    isLoading: loadingPrescribers,
    error: prescribersError,
  } = useQuery({
    queryKey: ["prescribers", token],
    queryFn: () => getPrescribers(token!),
    enabled: isAuthenticated && !!token,
    select: unwrapItems<Prescriber>,
    staleTime: 5 * 60 * 1000,
  });

  return (
    <DataContext.Provider
      value={{
        drugs,
        prescribers,
        loadingDrugs,
        loadingPrescribers,
        errorDrugs: (drugsError as Error)?.message ?? "",
        errorPrescribers: (prescribersError as Error)?.message ?? "",
      }}
    >
      {children}
    </DataContext.Provider>
  );
};
