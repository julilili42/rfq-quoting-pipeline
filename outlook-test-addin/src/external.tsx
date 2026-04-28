import { createRoot } from "react-dom/client";
import "./style.css";

function ExternalApp() {
  return (
    <div className="panel">
      <h1>External Debug Page</h1>
      <p className="muted">
        Diese Seite wird im neuen Review-API-Flow nicht mehr verwendet.
      </p>

      <section>
        <h2>Status</h2>
        <pre>
          Der Outlook-Button sendet die Mail jetzt direkt an die lokale Review-API
          und öffnet danach die Streamlit Review-UI.
        </pre>
      </section>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<ExternalApp />);