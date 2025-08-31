import React, { createContext, useState, useEffect } from "react";
import { getPatients, getDrugs } from "@/api";

export const DataContext = createContext();

export const DataProvider = ({ children }) => {
  const [patients, setPatients] = useState([]);
  const [drugs, setDrugs] = useState([]);
  const [loadingPatients, setLoadingPatients] = useState(true);
  const [loadingDrugs, setLoadingDrugs] = useState(true);
  const [errorPatients, setErrorPatients] = useState("");
  const [errorDrugs, setErrorDrugs] = useState("");

  useEffect(() => {
    let mounted = true;

    getPatients()
      .then((data) => mounted && setPatients(data))
      .catch((err) => mounted && setErrorPatients(err.message))
      .finally(() => mounted && setLoadingPatients(false));

    getDrugs()
      .then((data) => mounted && setDrugs(data))
      .catch((err) => mounted && setErrorDrugs(err.message))
      .finally(() => mounted && setLoadingDrugs(false));

    return () => {
      mounted = false;
    };
  }, []);

  return (
    <DataContext.Provider
      value={{
        patients,
        drugs,
        loadingPatients,
        loadingDrugs,
        errorPatients,
        errorDrugs,
      }}
    >
      {children}
    </DataContext.Provider>
  );
};
