"""The step between reading a screenshot and tallying a month.

Merging the two halves of a long leaderboard, resolving aliases, parsing
values, and cross-checking the app's own numbering against the order the
values imply. Plain Python: no engine, no HTTP, no disk.
"""

from .assemble import assemble, review, to_tables
from .models import Draft, DraftRow, DraftTable, Issue, IssueType

__all__ = [
    "Draft",
    "DraftRow",
    "DraftTable",
    "Issue",
    "IssueType",
    "assemble",
    "review",
    "to_tables",
]
