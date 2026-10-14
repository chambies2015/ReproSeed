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

M2b uses the same `DatabaseModel` for diagnosis, reduction and private bundle validation.
Exact declared TEXT PRIMARY KEY with a metadata-confirmed BINARY PK index is supported
alongside the existing INTEGER rowid-alias family, including mixed tables and matching
parent-family foreign keys. Exactly two ascending PK components of exact INTEGER/TEXT
declarations are also supported, with each family's storage checked independently and
all TEXT comparisons BINARY. Empty tables undergo PK index and FK group metadata checks.
Ordinary schemas with nullable TEXT/composite PK declarations are accepted only when
actual components are non-NULL and stored as their declared integer/text family, with
text decoding to Python strings.
FK policy comes from the referenced parent's ordered components, so the child's own PK can
have another shape or family. Explicit composite target columns must follow parent PK
order; implicit references use the complete PK. Any NULL child FK component means no
parent is required and no dependency edge is created. NULL parent components remain
unsupported. Unsupported collations, PK arity/order, NULL PK values, wrong stored key types,
FK cardinality/targets and unsupported FK
declarations have separate curated diagnostic causes. These expose no key values or raw
SQLite error details. Schema rejection happens before any executable baseline attempt.
See [the exact schema subset](architecture.md#supported-schema); diagnostic_version remains 1.

| Field | Meaning |
| --- | --- |
| `diagnostic_version` | Integer 1; independent diagnostic format |
| `mode` | `static` or `baseline` as explicitly requested |
| `snapshot_acquired` | Consistent private read-only-source backup completed |
| `schema_supported` | true after shared model validation; false for recognized unsupported schema; null when not established |
| `integrity_valid`, `foreign_keys_valid` | true for successful corresponding checks; false for an exact failed-check error; null when not established; the model checks integrity, schema/storage/dependencies, then FK consistency, so schema rejection leaves FK validity untested |
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

Curated input causes include `unsupported_text_key_collation`, `unsupported_unavailable_collation`,
`unsupported_null_text_primary_key`, `unsupported_text_encoding`,
`unsupported_primary_key_value`, `unsupported_foreign_key_value` and
`unsupported_foreign_key_type`. Values and original SQLite details are not included;
supported TEXT keys complete the same successful structural checks as INTEGER keys.
Composite causes include `unsupported_composite_primary_key_arity`,
`unsupported_null_composite_primary_key`, `unsupported_composite_primary_key_value`,
`unsupported_composite_key_collation`, `unsupported_composite_primary_key_order`,
`unsupported_composite_primary_key_metadata`, `unsupported_composite_foreign_key_cardinality`,
`unsupported_composite_foreign_key_type` and `unsupported_composite_foreign_key_value`.
Alternate/reordered targets use the existing `unsupported_foreign_key_target` cause with
curated full-PK wording. No component value, arbitrary SQL, process output or path is echoed.
These checks run before baseline launch and preserve diagnostic JSON version 1.
Unavailable-collation and malformed-text errors conservatively leave `integrity_valid`
null because validation may stop before establishing that result; a schema rejection does
not establish FK validity.

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
