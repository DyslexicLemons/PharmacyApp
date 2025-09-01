import React, { createContext, useState, useEffect } from "react";
import { getPatients, getDrugs, getStock, getRefillHist, getPrescribers } from "@/api";

export const DataContext = createContext();

export const DataProvider = ({ children }) => {
  const [patients, setPatients] = useState([]);
  const [drugs, setDrugs] = useState([]);
  const [stock, setStock] = useState([]);
  const [prescribers, setPrescribers] = useState([]);
  const [refillHist, setRefillHist] = useState([]);

  // loading states
  const [loadingPatients, setLoadingPatients] = useState(true);
  const [loadingDrugs, setLoadingDrugs] = useState(true);
  const [loadingStock, setLoadingStock] = useState(true);
  const [loadingRefillHist, setLoadingRefillHist] = useState(true);
  const [loadingPrescribers, setLoadingPrescribers] = useState(true);

  // error states
  const [errorPatients, setErrorPatients] = useState("");
  const [errorDrugs, setErrorDrugs] = useState("");
  const [errorStock, setErrorStock] = useState("");
  const [errorRefillHist, setErrorRefillHist] = useState("");
  const [errorPrescribers, setErrorPrescribers] = useState("");

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

    getPrescribers()
      .then((data) => mounted && setPrescribers(data))
      .catch((err) => mounted && setErrorPrescribers(err.message))
      .finally(() => mounted && setLoadingPrescribers(false));

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
        prescribers,

        loadingPatients,
        loadingDrugs,
        loadingStock,
        loadingRefillHist,
        loadingPrescribers,

        errorPatients,
        errorDrugs,
        errorStock,
        errorRefillHist,
        errorPrescribers,
      }}
    >
      {children}
    </DataContext.Provider>
  );
};