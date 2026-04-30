"""Tests for the stammdaten data-access layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from quoting.data import (
    CsvStammdatenRepository,
    InMemoryStammdatenRepository,
    StammdatenRecord,
    StammdatenRepository,
    build_repository,
)


@pytest.fixture
def csv_file(tmp_path: Path) -> Path:
    path = tmp_path / "stammdaten.csv"
    path.write_text(
        "artikel_nr,bezeichnung,werkstoff,abmessungen,einheit,"
        "basispreis_eur,zkalk_offset_eur,preis_min_eur,preis_max_eur,"
        "sales_group,material_group,n_offers\n"
        "001GLP108015,Gleitstück PTFE/Graphit 108x15,PTFE,108x15,ST,"
        "24.50,1.20,20.00,30.00,VG 30 - Industrial,Compressor,5\n"
        "002APZ00031B,Abnahmeprüfzeugnis 3.1,,,ST,"
        "45.00,0.0,,,,,1\n",
        encoding="utf-8",
    )
    return path


class TestStammdatenRecord:
    def test_to_row_round_trips_fields(self) -> None:
        record = StammdatenRecord(
            artikel_nr="ABC123",
            bezeichnung="Test",
            werkstoff="PTFE",
            basispreis_eur=12.5,
        )

        row = record.to_row()

        assert row["artikel_nr"] == "ABC123"
        assert row["bezeichnung"] == "Test"
        assert row["werkstoff"] == "PTFE"
        assert row["basispreis_eur"] == 12.5
        assert row["einheit"] == "ST"  # default


class TestCsvStammdatenRepository:
    def test_loads_records_from_disk(self, csv_file: Path) -> None:
        repo = CsvStammdatenRepository(csv_file)

        records = repo.all()

        assert len(records) == 2
        assert records[0].artikel_nr == "001GLP108015"
        assert records[0].werkstoff == "PTFE"
        assert records[0].basispreis_eur == pytest.approx(24.5)

    def test_empty_strings_become_none(self, csv_file: Path) -> None:
        repo = CsvStammdatenRepository(csv_file)

        cert = repo.by_artikelnr("002APZ00031B")

        assert cert is not None
        assert cert.werkstoff is None
        assert cert.abmessungen is None
        assert cert.preis_min_eur is None

    def test_by_artikelnr_returns_none_for_missing(self, csv_file: Path) -> None:
        repo = CsvStammdatenRepository(csv_file)

        assert repo.by_artikelnr("does-not-exist") is None

    def test_as_rows_matches_legacy_dict_shape(self, csv_file: Path) -> None:
        repo = CsvStammdatenRepository(csv_file)

        rows = repo.as_rows()

        # Required keys for the matcher / pricing modules
        for required in ("artikel_nr", "bezeichnung", "werkstoff", "basispreis_eur"):
            assert required in rows[0]

    def test_caches_after_first_load(self, csv_file: Path) -> None:
        repo = CsvStammdatenRepository(csv_file)
        first = repo.all()

        # Mutating the file shouldn't change cached results
        csv_file.write_text("artikel_nr,bezeichnung\n", encoding="utf-8")
        second = repo.all()

        assert first is second

    def test_rejects_csv_missing_required_columns(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.csv"
        bad.write_text("foo,bar\n1,2\n", encoding="utf-8")

        with pytest.raises(ValueError, match="missing required columns"):
            CsvStammdatenRepository(bad).all()


class TestInMemoryStammdatenRepository:
    def test_lookup_by_artikelnr(self) -> None:
        repo = InMemoryStammdatenRepository(
            [StammdatenRecord(artikel_nr="X1", bezeichnung="Foo")],
        )

        record = repo.by_artikelnr("X1")

        assert record is not None
        assert record.bezeichnung == "Foo"

    def test_satisfies_repository_protocol(self) -> None:
        repo = InMemoryStammdatenRepository([])
        assert isinstance(repo, StammdatenRepository)


class TestBuildRepository:
    def test_existing_csv_yields_csv_repository(self, csv_file: Path) -> None:
        repo = build_repository(csv_file)
        assert isinstance(repo, CsvStammdatenRepository)

    def test_missing_path_falls_back_to_mock(self, tmp_path: Path) -> None:
        repo = build_repository(tmp_path / "nope.csv")

        records = repo.all()

        assert isinstance(repo, InMemoryStammdatenRepository)
        assert len(records) > 0  # mock dataset is non-empty

    def test_none_path_yields_mock(self) -> None:
        repo = build_repository(None)
        assert isinstance(repo, InMemoryStammdatenRepository)
