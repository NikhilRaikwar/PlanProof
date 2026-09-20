class PlanProofError(Exception):
    """Base exception for expected application errors."""


class DependencyNotReadyError(PlanProofError):
    """Raised when a required external dependency is unavailable."""


class DuplicateResourceError(PlanProofError):
    """Raised when an immutable resource would be overwritten."""
