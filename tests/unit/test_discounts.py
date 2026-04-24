"""Volume discount tiers."""
from quoting.pricing import volume_discount


def test_no_discount_below_100():
    assert volume_discount(0) == 0.0
    assert volume_discount(50) == 0.0
    assert volume_discount(99) == 0.0


def test_five_percent_at_100():
    assert volume_discount(100) == 0.05
    assert volume_discount(499) == 0.05


def test_ten_percent_at_500():
    assert volume_discount(500) == 0.10
    assert volume_discount(999) == 0.10


def test_fifteen_percent_at_1000():
    assert volume_discount(1000) == 0.15
    assert volume_discount(99999) == 0.15
