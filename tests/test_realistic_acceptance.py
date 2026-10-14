"""Large relational examples exercise the public CLI and independent oracles."""

from __future__ import annotations

from pathlib import Path

import pytest
from milestone_smoke import exercise_example


@pytest.mark.parametrize(
    "example", ["reservation_overbook", "approval_cycle", "text_key_entitlements"]
)
def test_realistic_complete_relocated_acceptance(example: str, tmp_path: Path) -> None:
    measured = exercise_example(example, tmp_path / example)
    assert measured["unresolved_attempts"] == 0
    assert measured["invalid_candidates"] == 0
    assert measured["termination_reason"] == "single_row_closures_exhausted"
    assert measured["schema_metadata_and_retained_values_preserved"] is True
    assert measured["source_and_bundle_unchanged"] is True
