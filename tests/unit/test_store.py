"""Tests for quoting.reviews.store — JSON I/O and _to_jsonable."""
from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from quoting.reviews.store import _to_jsonable, read_json, write_json

# ---------- read_json ----------

def test_read_json_missing_file(tmp_path):
    assert read_json(tmp_path / "nope.json") is None


def test_read_json_corrupt_file(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert read_json(p) is None


def test_read_json_happy_path(tmp_path):
    p = tmp_path / "data.json"
    p.write_text('{"key": 42}', encoding="utf-8")
    assert read_json(p) == {"key": 42}


def test_read_json_list(tmp_path):
    p = tmp_path / "list.json"
    p.write_text('[1, 2, 3]', encoding="utf-8")
    assert read_json(p) == [1, 2, 3]


# ---------- write_json ----------

def test_write_json_creates_file(tmp_path):
    p = tmp_path / "out.json"
    write_json(p, {"hello": "world"})
    assert p.exists()
    assert json.loads(p.read_text()) == {"hello": "world"}


def test_write_json_no_tmp_leftover(tmp_path):
    p = tmp_path / "out.json"
    write_json(p, {"x": 1})
    assert not (tmp_path / "out.json.tmp").exists()


def test_write_json_creates_parent_dirs(tmp_path):
    p = tmp_path / "deep" / "nested" / "out.json"
    write_json(p, {"nested": True})
    assert p.exists()


def test_write_json_roundtrip(tmp_path):
    p = tmp_path / "rt.json"
    payload = {"a": 1, "b": [1, 2, 3], "c": {"d": None}}
    write_json(p, payload)
    assert read_json(p) == payload


# ---------- _to_jsonable ----------

def test_to_jsonable_primitive():
    assert _to_jsonable(42) == 42
    assert _to_jsonable("hello") == "hello"
    assert _to_jsonable(None) is None


def test_to_jsonable_list():
    assert _to_jsonable([1, 2, 3]) == [1, 2, 3]


def test_to_jsonable_dict():
    assert _to_jsonable({"a": 1}) == {"a": 1}


def test_to_jsonable_nested():
    assert _to_jsonable({"a": [1, {"b": 2}]}) == {"a": [1, {"b": 2}]}


def test_to_jsonable_dataclass():
    @dataclass
    class Foo:
        x: int
        y: str

    result = _to_jsonable(Foo(x=1, y="hi"))
    assert result == {"x": 1, "y": "hi"}


def test_to_jsonable_depth_limit():
    # Build a deeply nested dict beyond the limit
    deep: dict = {}
    node = deep
    for _ in range(55):
        node["child"] = {}
        node = node["child"]

    with pytest.raises(ValueError, match="max depth"):
        _to_jsonable(deep)
