import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";

/**
 * Legacy `?review_id=...` redirector.
 *
 * Old Outlook-add-in builds open `http://host/?review_id=abc123` —
 * this matches the previous Streamlit URL convention. We translate
 * those URLs into the new `/reviews/abc123` route so existing buttons
 * keep working without an Add-in update.
 *
 * Lives at the dashboard route. If the user genuinely wants the
 * dashboard (no query param), this component is a no-op.
 */
export function LegacyQueryRedirect() {
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    if (location.pathname !== "/") return;
    const params = new URLSearchParams(location.search);
    const reviewId = params.get("review_id");
    if (reviewId) {
      navigate(`/reviews/${encodeURIComponent(reviewId)}`, { replace: true });
    }
  }, [location.pathname, location.search, navigate]);

  return null;
}
