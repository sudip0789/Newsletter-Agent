from __future__ import annotations

from datetime import date, datetime, timedelta


def resolve_publication_date(
    requested_date: date | datetime | str | None,
) -> date | str:
    """Convert a prep date into the next day's publication date."""
    if requested_date is None:
        return datetime.now().date() + timedelta(days=1)
    if isinstance(requested_date, datetime):
        return requested_date.date() + timedelta(days=1)
    if isinstance(requested_date, date):
        return requested_date + timedelta(days=1)
    if isinstance(requested_date, str):
        stripped = requested_date.strip()
        try:
            return datetime.fromisoformat(stripped).date() + timedelta(days=1)
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
