import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { DataProvider } from "@/context/DataContext";
import { AuthProvider } from "@/context/AuthProvider";
import { PluginProvider } from "@/plugins/PluginContext";
import { createDefaultRegistry } from "@/plugins/apiBackedProviders";
import { useAuthStore } from "@/stores/authStore";

// Build the plugin registry once.  getToken is evaluated on every API call so
// the registry never needs to be recreated after login/logout.
const pluginRegistry = createDefaultRegistry(() => useAuthStore.getState().token);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Only retry once on failure — fast feedback in a pharmacy context
      retry: 1,
      // Don't refetch just because the user switches browser tabs
      refetchOnWindowFocus: false,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <DataProvider>
          <PluginProvider registry={pluginRegistry}>
            <App />
          </PluginProvider>
        </DataProvider>
      </AuthProvider>
    </QueryClientProvider>
  </React.StrictMode>
);
