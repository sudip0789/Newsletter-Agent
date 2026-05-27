from __future__ import annotations

from datetime import date, datetime


def resolve_publication_date(
    requested_date: date | datetime | str | None,
) -> date | str:
    """Resolve the issue date directly from the provided date input."""
    if requested_date is None:
        return datetime.now().date()
    if isinstance(requested_date, datetime):
        return requested_date.date()
    if isinstance(requested_date, date):
        return requested_date
    if isinstance(requested_date, str):
        stripped = requested_date.strip()
        try:
            return datetime.fromisoformat(stripped).date()
        except ValueError:
            return stripped
    raise TypeError("requested_date must be a date, datetime, string, or None.")


def normalize_issue_date(issue_date: date | datetime | str | None) -> str:
    """Convert an already-resolved issue date into an ISO-like string when possible."""
    if issue_date is None:
        return ""
    if isinstance(issue_date, datetime):
        return issue_date.date().isoformat()
    if isinstance(issue_date, date):
        return issue_date.isoformat()
    return str(issue_date).strip()
