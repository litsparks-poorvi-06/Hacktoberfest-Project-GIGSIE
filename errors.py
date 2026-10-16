"""Shared exceptions for Gigsie's workflow modules.

A ``WorkflowError`` is raised when a requested action simply cannot happen
(for example: no profile selected, an application already exists, or an illegal
status change). The message is always written to be shown directly to a user and
never contains secrets, tracebacks, or API keys.

Input problems are *not* raised - they are returned as findings lists by the
``validation`` module, so the UI can show them all at once.
"""

from __future__ import annotations


class WorkflowError(Exception):
    """A requested action cannot be completed. The message is safe to show."""
