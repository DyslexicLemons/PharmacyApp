import React, { createContext, useState, useEffect } from "react";
import { getPatients, getDrugs, getStock } from "@/api";

export const DataContext = createContext();

export const DataProvider = ({ children }) => {
  const [patients, setPatients] = useState([]);
  const [drugs, setDrugs] = useState([]);
  const [stock, setStock] = useState([]);
  const [loadingPatients, setLoadingPatients] = useState(true);
  const [loadingDrugs, setLoadingDrugs] = useState(true);
  const [loadingStock, setLoadingStock] = useState(true);
  const [errorPatients, setErrorPatients] = useState("");
  const [errorDrugs, setErrorDrugs] = useState("");
  const [errorStock, setErrorStock] = useState("");

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

    getStock()
      .then((data) => mounted && setStock(data))
      .catch((err) => mounted && setErrorStock(err.message))
      .finally(() => mounted && setLoadingStock(false));

    return () => {
      mounted = false;
    };
  }, []);

  return (
    <DataContext.Provider
      value={{
        patients,
        drugs,
        stock,
        loadingPatients,
        loadingDrugs,
        loadingStock,
        errorPatients,
        errorDrugs,
        errorStock
      }}
    >
      {children}
    </DataContext.Provider>
  );
};
