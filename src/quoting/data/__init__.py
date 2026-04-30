"""Data-access layer.

The application talks to master data exclusively through the
repository abstraction here. The default implementation reads from a
local CSV; future adapters (SQL, SAP) can be dropped in without
touching the rest of the code.
"""

from .records import StammdatenRecord
from .repository import (
    CsvStammdatenRepository,
    InMemoryStammdatenRepository,
    StammdatenRepository,
    build_repository,
)

__all__ = [
    "StammdatenRecord",
    "StammdatenRepository",
    "CsvStammdatenRepository",
    "InMemoryStammdatenRepository",
    "build_repository",
]
