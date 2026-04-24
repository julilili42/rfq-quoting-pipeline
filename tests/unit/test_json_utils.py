"""Robust JSON extraction from messy LLM output."""
import pytest

from quoting.extraction.json_utils import extract_json_object


def test_plain_json():
    assert extract_json_object('{"a": 1}') == '{"a": 1}'


def test_json_with_leading_prose():
    raw = 'Here is the extraction:\n{"a": 1}'
    assert extract_json_object(raw) == '{"a": 1}'


def test_json_with_markdown_fence():
    raw = '```json\n{"a": 1}\n```'
    assert extract_json_object(raw) == '{"a": 1}'


def test_json_with_plain_fence():
    raw = '```\n{"a": 1}\n```'
    assert extract_json_object(raw) == '{"a": 1}'


def test_nested_objects_handled_correctly():
    raw = '{"outer": {"inner": {"deep": 1}}, "x": [1, 2, 3]}'
    assert extract_json_object(raw) == raw


def test_braces_inside_string_ignored():
    raw = '{"note": "value contains } braces {"}'
    assert extract_json_object(raw) == raw


def test_escaped_quotes_in_string():
    raw = r'{"msg": "He said \"hi\""}'
    assert extract_json_object(raw) == raw


def test_trailing_prose_after_json():
    raw = '{"a": 1}\n\nThat concludes the extraction.'
    assert extract_json_object(raw) == '{"a": 1}'


def test_raises_on_no_object():
    with pytest.raises(ValueError, match="No JSON"):
        extract_json_object("just some text")


def test_raises_on_unbalanced():
    with pytest.raises(ValueError, match="Unbalanced"):
        extract_json_object('{"a": 1')
