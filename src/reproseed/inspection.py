"""Compact terminal-safe formatting of already validated bundle metadata."""

from __future__ import annotations

import json
import unicodedata
from typing import cast


def escape_terminal(value: str) -> str:
    """Make controls, Unicode direction controls and line separators visible."""
    result: list[str] = []
    for character in value:
        if unicodedata.category(character) in {"Cc", "Cf", "Cs", "Zl", "Zp"}:
            code = ord(character)
            result.append(f"\\u{code:04x}" if code <= 0xFFFF else f"\\U{code:08x}")
        else:
            result.append(character)
    return "".join(result)


_TERMINATION = {
    "single_row_closures_exhausted": (
        "Single-row deletion closures exhausted; unresolved trials may remain."
    ),
    "empty_candidate_confirmed": "No rows remain in the confirmed fixture.",
    "oracle_budget_exhausted_reserved_final_verification": (
        "Oracle budget stopped the search; final verification capacity was reserved."
    ),
    "interrupted_best_confirmed_candidate_preserved": (
        "Search interrupted; the best confirmed candidate was preserved."
    ),
}


def format_inspection(report: dict[str, object], manifest: dict[str, object]) -> str:
    """Summarize validated version-1 data without claiming a new oracle replay."""
    original = cast(dict[str, int], report["original_counts"])
    final = cast(dict[str, int], report["final_counts"])
    runtime = cast(dict[str, str], manifest["runtime"])
    artifacts = cast(dict[str, str], manifest["artifacts"])
    original_total, final_total = sum(original.values()), sum(final.values())
    reduction = (
        f"{(original_total - final_total) / original_total * 100:.1f}% removed"
        if original_total
        else "n/a; original fixture has zero rows"
    )
    lines = [
        f"ReproSeed bundle format {manifest['version']} / report format {report['version']}",
        f"Recorded tool: reproseed {escape_terminal(cast(str, manifest['tool_version']))}",
        "Recorded runtime: "
        f"Python {escape_terminal(runtime['python'])}; SQLite {escape_terminal(runtime['sqlite'])}",
        f"Artifact integrity: checked now (SHA256; {len(artifacts)} declared files)",
        "Recorded evidence: structure and consistency checked now",
        "Fixture structure/counts: checked now",
        f"Rows: {original_total} original -> {final_total} retained ({reduction})",
        "Tables (original -> retained):",
    ]
    lines.extend(
        f"  {escape_terminal(json.dumps(table, ensure_ascii=False))}: "
        f"{original[table]} -> {final[table]}"
        for table in sorted(original)
    )
    if not original:
        lines.append("  (no user tables)")
    accepted = cast(list[object], report["accepted_reductions"])
    baseline = cast(list[object], report["baseline_verification"])
    final_confirmations = cast(list[object], report["final_verification"])
    lines.extend(
        [
            f"Recorded oracle executions: {report['oracle_invocations']}",
            f"Budget charged: {report['budget_charged_invocations']}/{report['max_invocations']} "
            f"({report['unknown_interrupted_launches']} unknown interrupted launches)",
            f"Cache hits: {report['cache_hits']} (reused evidence; no new executions)",
            f"Search: {len(accepted)} accepted reductions; "
            f"{report['unresolved_attempts']} unresolved trials; "
            f"{report['invalid_candidates']} invalid candidates",
            f"Recorded baseline confirmations: {len(baseline)}/3 TARGET_FAILURE",
            f"Recorded final confirmations: {len(final_confirmations)}/3 TARGET_FAILURE",
            "Search termination: " + _TERMINATION[cast(str, report["termination_reason"])],
            "New replay: not performed by inspect (oracle not executed)",
            "Hashes and consistent recorded evidence do not authenticate historical executions.",
            "Reduction is not anonymization or proof of global minimality.",
        ]
    )
    return "\n".join(lines)
