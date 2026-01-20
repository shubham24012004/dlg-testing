"""Compatibility shim for legacy imports.

Prefer ``DatabaseOperation.SQLAlchemy.DatabaseModels`` going forward.
"""

from DatabaseOperation.SQLAlchemy.DatabaseModels import FetchResult, LspMaster

SourceRow = LspMaster
