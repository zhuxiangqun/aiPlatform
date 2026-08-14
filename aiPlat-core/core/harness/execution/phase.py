"""Harness kernel-level Pipeline stage constants (generic, no business concepts).

Replaces the business-enum dependency on BuilderSessionPhase.
All stage names are string constants that can be compared directly or used as state keys.
"""


class PipelinePhase:
    """Generic identifiers for Pipeline execution stages.

    These constants are not bound to any business module's semantics.
    The state machine matches on stage names as strings rather than comparing enum types.
    """

    DIALOGUE = "dialogue"
    EXECUTING = "executing"
    PAUSED = "paused"
    DONE = "done"
    FAILED = "failed"
