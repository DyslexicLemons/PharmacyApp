// src/main.jsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { DataProvider } from "@/context/DataContext";
import { AuthProvider } from "@/context/AuthContext";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <AuthProvider>
      <DataProvider>
        <App />
      </DataProvider>
    </AuthProvider>
  </React.StrictMode>
);