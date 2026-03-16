/**
 * DataContext — previously fetched drugs and prescribers with raw useEffect +
 * useState. Now backed by React Query, which gives us automatic caching,
 * background refetching, and deduplication for free.
 *
 * The context value shape is intentionally identical to the old one so every
 * consumer (PrescriptionForm, EditRefillView, etc.) works without changes.
 */
import { createContext, useContext } from "react";
import { useQuery } from "@tanstack/react-query";
import { getDrugs, getPrescribers } from "@/api";
import { AuthContext } from "./AuthContext";

export const DataContext = createContext();

export const DataProvider = ({ children }) => {
  const { isAuthenticated, token } = useContext(AuthContext);

  const {
    data: drugs = [],
    isLoading: loadingDrugs,
    error: drugsError,
  } = useQuery({
    queryKey: ["drugs", token],
    queryFn: () => getDrugs(token),
    enabled: isAuthenticated && !!token,
    // Unwrap paginated response shape or plain array
    select: (data) => data.items ?? data,
    // Drugs change rarely — keep the cache fresh for 5 minutes
    staleTime: 5 * 60 * 1000,
  });

  const {
    data: prescribers = [],
    isLoading: loadingPrescribers,
    error: prescribersError,
  } = useQuery({
    queryKey: ["prescribers", token],
    queryFn: () => getPrescribers(token),
    enabled: isAuthenticated && !!token,
    select: (data) => data.items ?? data,
    staleTime: 5 * 60 * 1000,
  });

  return (
    <DataContext.Provider
      value={{
        drugs,
        prescribers,
        loadingDrugs,
        loadingPrescribers,
        errorDrugs: drugsError?.message ?? "",
        errorPrescribers: prescribersError?.message ?? "",
      }}
    >
      {children}
    </DataContext.Provider>
  );
};
