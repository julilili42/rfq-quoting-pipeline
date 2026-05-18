from fastapi import HTTPException

from quoting.api import _common
from quoting.api.routers import reviews as reviews_router


def test_delete_review_removes_review_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(_common, "REVIEW_DIR", tmp_path)
    review_dir = tmp_path / "review-123"
    review_dir.mkdir()
    (review_dir / "mail.json").write_text("{}", encoding="utf-8")

    response = reviews_router.delete_review("review-123")

    assert response.status_code == 204
    assert not review_dir.exists()


def test_review_dir_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(_common, "REVIEW_DIR", tmp_path / "reviews")
    outside = tmp_path / "outside"
    outside.mkdir()

    try:
        _common.review_dir("../outside")
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("Expected path traversal to be rejected")
