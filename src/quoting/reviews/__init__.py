"""Cross-cutting review helpers.

The rest of the codebase historically duplicated three pieces of logic:

* PDF lookup (``find_draft_pdf`` / ``find_final_pdf``) — copied across
  ``review_api``, ``document_view``, ``quotation_flow`` and
  ``review_loader``.
* JSON I/O against review folders (``mail.json``, ``approval.json``,
  ``manual_overrides.json`` …) — atomic-write boilerplate sprinkled in
  several places.
* Reset / cleanup of a review folder — the API and the Streamlit UI
  each rolled their own variant.

This package is the canonical home for those concerns. Importing from
here is preferred over re-implementing them.
"""
from .lifecycle import reset_review_artifacts
from .pdfs import (
    draft_pdf_filename,
    final_pdf_filename,
    find_current_pdf,
    find_draft_pdf,
    find_final_pdf,
)
from .quotation_store import load_saved_quotation, quotation_from_dict
from .store import (
    ReviewFiles,
    load_mail_meta,
    load_review_state,
    read_json,
    read_json_list,
    saved_attachment_paths,
    write_json,
)
from .summary import ReviewSummary, scan_reviews
from .urls import api_base_url, pdf_url

__all__ = [
    "ReviewFiles",
    "draft_pdf_filename",
    "final_pdf_filename",
    "find_current_pdf",
    "find_draft_pdf",
    "find_final_pdf",
    "load_mail_meta",
    "load_review_state",
    "read_json",
    "read_json_list",
    "saved_attachment_paths",
    "write_json",
    "reset_review_artifacts",
    "api_base_url",
    "pdf_url",
    "ReviewSummary",
    "scan_reviews",
    "load_saved_quotation",
    "quotation_from_dict",
]
