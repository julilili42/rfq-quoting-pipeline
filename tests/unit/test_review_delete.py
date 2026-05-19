from fastapi import HTTPException

from quoting.api import _common
from quoting.api.routers import reviews as reviews_router


def test_delete_review_removes_review_folder(sqlite_repo):
    sqlite_repo.create_review("review-123", subject="Anfrage")
    folder = sqlite_repo.artifact_dir("review-123")
    (folder / "rfq.pdf").write_bytes(b"%PDF-test")

    response = reviews_router.delete_review("review-123")

    assert response.status_code == 204
    assert not folder.exists()
    assert sqlite_repo.get_review("review-123") is None


def test_review_dir_rejects_path_traversal(sqlite_repo):
    try:
        _common.review_dir("../outside")
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("Expected path traversal to be rejected")
