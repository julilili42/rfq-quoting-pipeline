"""Tests for review UI session-state helpers."""
from __future__ import annotations

from quoting.ui.review_ui import state


class _FakeStreamlit:
    def __init__(self):
        self.session_state = {
            "ed_kundennr": "10042",
            "ed_kunde_firma": "Muster GmbH",
            "cert_0": True,
            "art_0": "001GLP108015",
            "changed_fields": {"kundennummer"},
            "review_id": "abc123",
        }


def test_reset_editor_state_clears_header_and_position_widget_keys(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(state, "st", fake_st)

    state.reset_editor_state()

    assert "ed_kundennr" not in fake_st.session_state
    assert "ed_kunde_firma" not in fake_st.session_state
    assert "cert_0" not in fake_st.session_state
    assert "art_0" not in fake_st.session_state
    assert "changed_fields" not in fake_st.session_state
    assert fake_st.session_state["review_id"] == "abc123"
