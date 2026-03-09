import React, { createContext, useState, useEffect, useContext } from "react";
import { getDrugs, getPrescribers } from "@/api";
import { AuthContext } from "./AuthContext";

export const DataContext = createContext();

export const DataProvider = ({ children }) => {
  const { isAuthenticated, token } = useContext(AuthContext);

  const [drugs, setDrugs] = useState([]);
  const [prescribers, setPrescribers] = useState([]);

  // loading states
  const [loadingDrugs, setLoadingDrugs] = useState(false);
  const [loadingPrescribers, setLoadingPrescribers] = useState(false);

  // error states
  const [errorDrugs, setErrorDrugs] = useState("");
  const [errorPrescribers, setErrorPrescribers] = useState("");

  // Only fetch global reference data (drugs, prescribers) once authenticated.
  // Patients, stock, refillHist, and queue data are fetched by their own views.
  useEffect(() => {
    if (!isAuthenticated || !token) return;

    let mounted = true;

    setLoadingDrugs(true);
    getDrugs(token)
      .then((data) => mounted && setDrugs(data.items ?? data))
      .catch((err) => mounted && setErrorDrugs(err.message))
      .finally(() => mounted && setLoadingDrugs(false));

    setLoadingPrescribers(true);
    getPrescribers(token)
      .then((data) => mounted && setPrescribers(data.items ?? data))
      .catch((err) => mounted && setErrorPrescribers(err.message))
      .finally(() => mounted && setLoadingPrescribers(false));

    return () => {
      mounted = false;
    };
  }, [isAuthenticated, token]);

  return (
    <DataContext.Provider
      value={{
        drugs,
        prescribers,
        loadingDrugs,
        loadingPrescribers,
        errorDrugs,
        errorPrescribers,
      }}
    >
      {children}
    </DataContext.Provider>
  );
};
