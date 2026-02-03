import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import "./styles.css";

const queryClient = new QueryClient();

// Prevent duplicate React roots on HMR / dev-server reconnect
const rootEl = document.getElementById("root") as HTMLElement;

// Store root on the element itself so HMR reuse works
let root: ReactDOM.Root;
if ((rootEl as any).__reactRoot) {
  root = (rootEl as any).__reactRoot;
} else {
  // Clear any stale DOM from previous render before creating root
  rootEl.innerHTML = "";
  root = ReactDOM.createRoot(rootEl);
  (rootEl as any).__reactRoot = root;
}

root.render(
  <QueryClientProvider client={queryClient}>
    <App />
  </QueryClientProvider>
);

// HMR cleanup: unmount on dispose to prevent ghost renders
if (import.meta.hot) {
  import.meta.hot.dispose(() => {
    root.unmount();
    rootEl.innerHTML = "";
    delete (rootEl as any).__reactRoot;
  });
}
