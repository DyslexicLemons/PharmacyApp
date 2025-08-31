import React, { createContext, useState, useEffect } from "react";
import { getPatients, getDrugs, getStock, getRefillHist} from "@/api";

export const DataContext = createContext();

export const DataProvider = ({ children }) => {
  const [patients, setPatients] = useState([]);
  const [drugs, setDrugs] = useState([]);
  const [stock, setStock] = useState([]);
  const [refillHist, setRefillHist] = useState([]);
  const [loadingPatients, setLoadingPatients] = useState(true);
  const [loadingDrugs, setLoadingDrugs] = useState(true);
  const [loadingStock, setLoadingStock] = useState(true);
  const [LoadingRefillHist, setLoadingRefillHist] = useState(true);
  const [errorPatients, setErrorPatients] = useState("");
  const [errorDrugs, setErrorDrugs] = useState("");
  const [errorStock, setErrorStock] = useState("");
  const [errorRefillHist, setErrorRefillHist] = useState("");

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

    getRefillHist()
      .then((data) => mounted && setRefillHist(data))
      .catch((err) => mounted && setErrorRefillHist(err.message))
      .finally(() => mounted && setLoadingRefillHist(false));

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
        refillHist,
        loadingPatients,
        loadingDrugs,
        loadingStock,
        LoadingRefillHist,
        errorPatients,
        errorDrugs,
        errorStock,
        errorRefillHist
      }}
    >
      {children}
    </DataContext.Provider>
  );
};
