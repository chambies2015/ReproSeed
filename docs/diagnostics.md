# Diagnostic document version 1

`reproseed diagnose --config ...` defaults to text. `--format json` writes one JSON
document to stdout for normal completion, invalid inputs and handled interruption.
This document is independent of version-1 report.json and replay.toml. Diagnosis never
writes a bundle or evidence beside the source. Redirect stdout explicitly to retain it.

Without `--allow-exec`, configuration/assets, a consistent private SQLite snapshot,
the reducer's supported schema subset, integrity and foreign keys are checked now.
Static exit 0 means these structural checks succeeded, with no oracle execution or
reproduction claim. With `--allow-exec`, exactly three fresh baseline attempts run unless
interruption or a hard nonlaunch blocks completion. Every executed PASS or UNRESOLVED
observation is retained and the remaining confirmations are attempted. All three must
be TARGET_FAILURE; there is no majority vote.

| Field | Meaning |
| --- | --- |
| `diagnostic_version` | Integer 1; independent diagnostic format |
| `mode` | `static` or `baseline` as explicitly requested |
| `snapshot_acquired` | Consistent private read-only-source backup completed |
| `schema_supported` | true after shared model validation; false for recognized unsupported schema; null when not established |
| `integrity_valid`, `foreign_keys_valid` | true for successful model validation or a recognized schema rejection after prior validation; false for an exact failed-check error; null when not established; the shared model checks integrity, then FKs, then schema |
| `assets_validated` | Explicit files passed checks and were copied privately |
| `structurally_suitable` | Snapshot/model validation completed successfully |
| `table_counts`, `total_rows` | Sorted user-table counts and their sum; empty/zero if model validation did not complete |
| `oracle_contract` | Expected exit, stream, exact whole UTF-8 line matching, marker byte length and argument count; null if config is invalid |
| `limits` | Per-attempt timeout, combined-output byte limit and configured reduction invocation budget; null if config is invalid |
| `required_baseline_confirmations` | Integer 3 |
| `oracle_executed` | true if a launch is confirmed, false for established nonexecution, null for uncertain launch/incomplete accounting with no confirmed launches |
| `baseline_confirmed` | true only for three completed TARGET_FAILURE results without interruption or input error |
| `baseline_results` | Ordered actual completed results: outcome, reason, reason_code, exit_code, output_bytes, duration_seconds, executed |
| `actual_invocations` | Confirmed launches charged by the existing invocation counter |
| `unknown_interrupted_launches` | Launches interrupted inside process construction with no established launch/nonlaunch |
| `budget_charged_invocations` | Known launches plus unknown interrupted launches; this is a conservative charge |
| `interrupted_invocations` | Existing counter evidence: UNRESOLVED/interrupted with executed true, false or null |
| `unreported_invocations` | Confirmed launches lacking result/interruption metadata after a transfer boundary; no result is invented |
| `accounting_complete` | false when a further interruption aborts accounting recovery; counts then describe only the committed accounting snapshot |
| `interrupted` | Completion was prevented by interruption |
| `error` | null or a curated stage, reason code and actionable message for invalid inputs |

The configured reduction budget is summarized, but diagnosis performs no search and
does not consume a later reduction's budget. Completed outcome/reason classification
comes from `run_oracle` unchanged. `reason_code` maps its actual reason to a stable label:
`target_contract_matched`, `clean_non_target_exit`, `unexpected_exit`,
`missing_exact_marker`, `marker_zero_exit_contradiction`, `process_signal`, `timeout`,
`output_limit`, `output_read_error`, `launch_error` or `staging_error`. A future unmapped
reason is labeled `unrecognized_reason`, without changing its classification.

Exit codes are 0 for successful static checks or a confirmed requested baseline, 1 for
an executable-mode baseline not established, 2 for invalid configuration/schema/input,
and 130 for interruption. A hard launch/staging failure has executed=false and is not
charged as an actual invocation. The timeout includes process runtime and open output
pipes; cleanup uses the existing bounded process-tree/owned-directory implementation.

No document field contains row values, source paths, original argv/marker values, raw
stdout/stderr or inherited environment values. Table names are schema metadata. Text
escapes terminal controls, including Unicode direction controls. Runtime durations and
output-byte counts describe actual observations and may differ between executions.
Integer and boolean facts, table ordering and static formatting are deterministic.

Diagnosis sources each fresh invocation from one private pristine database and frozen
explicit assets. The supplied source and assets remain unchanged by tool operations.
Authorized oracle code still runs with the user's OS permissions; temporary copies are
not a sandbox. Structural readiness and a confirmed baseline do not guarantee that a
subsequent reduction or its final verification will succeed.
