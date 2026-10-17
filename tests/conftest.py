"""LOCAL PATCH test adaptations (see /root/.hermes/backups/LOCAL-PATCHES.md, PATCH-021).

These upstream tests assert behaviour that a registered local patch removes ON PURPOSE,
so on this branch they are expected to fail. Each id is mapped to the patch that
intentionally changes the asserted behaviour; the test is skipped with that reason
instead of being silently deleted, so an upstream change to the same test still shows
up as a diff on the next merge. Verified 2026-09-25: every id below passes on pristine
v4.6.9 and fails only with the local patches applied.

Keep this list minimal. A test that fails for any OTHER reason must be fixed, not added.
"""
import pytest

_PATCH_012 = (
    "LOCAL PATCH (PATCH-012): the content-area tool_activity rows are hidden in every "
    "state by user request; tools remain visible in the 思考过程 panel"
)
_PATCH_011 = (
    "LOCAL PATCH (PATCH-011): footer tool count / token counts are hidden by user request"
)
_PATCH_007 = (
    "LOCAL PATCH (PATCH-007): token payload also carries prompt/cache fields for the "
    "rolling cache-rate footer (exact-equality token assertion)"
)
_PATCH_024 = (
    "LOCAL PATCH (PATCH-024): known hourglass statuses are rendered as HFC cards, so "
    "the upstream plain-text adapter recall route does not apply"
)

INTENTIONAL_LOCAL_BEHAVIOUR = {
    "tests/unit/test_331_adapted.py::test_actual_queued_interruption_block_delivers_metrics_then_next_turn": _PATCH_007,
    "tests/unit/test_331_adapted.py::test_invalid_tool_duration_does_not_break_rendering": _PATCH_012,
    "tests/unit/test_331_adapted.py::test_parallel_tool_windows_keep_each_running_predecessor_in_call_order": _PATCH_012,
    "tests/unit/test_331_adapted.py::test_terminal_tool_row_retains_measured_or_derived_duration": _PATCH_012,
    "tests/unit/test_331_adapted.py::test_tool_duration_survives_private_checkpoint_and_legacy_record": _PATCH_012,
    "tests/unit/test_card_layout_state_and_tools.py::test_content_tool_row_carries_a_long_command_whole_even_though_the_header_caps_it": _PATCH_012,
    "tests/unit/test_card_layout_state_and_tools.py::test_failed_tool_is_tagged_red": _PATCH_012,
    "tests/unit/test_card_layout_state_and_tools.py::test_finished_card_keeps_one_tool_row_as_evidence_of_what_ran": _PATCH_012,
    "tests/unit/test_card_layout_state_and_tools.py::test_footer_reports_state_elapsed_time_and_tool_count": _PATCH_011,
    "tests/unit/test_card_layout_state_and_tools.py::test_header_action_row_names_the_work_and_stays_within_the_cap": _PATCH_012,
    "tests/unit/test_card_layout_state_and_tools.py::test_tool_ordinal_counts_each_call_and_survives_status_updates": _PATCH_012,
    "tests/unit/test_card_layout_state_and_tools.py::test_tool_row_shows_state_name_ordinal_and_elapsed_time": _PATCH_012,
    "tests/unit/test_card_layout_state_and_tools.py::test_verb_only_tool_line_is_dropped_from_the_row": _PATCH_012,
    "tests/unit/test_stream_thinking_to_body.py::test_opt_out_moves_live_thinking_to_bounded_panel_only": _PATCH_012,
    "tests/unit/test_timeline_active_visibility.py::test_terminal_compaction_keeps_old_interrupted_body_tools_in_the_panel": _PATCH_012,
    # v4.7.0 (2026-10-04): opt-in task-presentation tests that read the content-area
    # tool_activity_ row PATCH-012 removes (StopIteration / any() over that row).
    # Verified: all pass on pristine v4.7.0, fail only on the patched tree.
    "tests/unit/test_presentation.py::test_task_current_action_keeps_identifiable_target_when_upstream_preview_was_shortened": _PATCH_012,
    "tests/unit/test_presentation.py::test_task_does_not_hide_parameters_when_no_detail_panel_exists": _PATCH_012,
    "tests/unit/test_presentation.py::test_task_event_sourced_generic_interrupt_uses_header_and_keeps_tool_evidence": _PATCH_012,
    "tests/unit/test_presentation.py::test_task_parallel_tools_only_move_parameters_that_are_in_the_rendered_panel": _PATCH_012,
    "tests/unit/test_presentation.py::test_task_reused_tool_id_cannot_hide_current_parameters_using_old_detail": _PATCH_012,
    "tests/unit/test_presentation.py::test_task_running_card_has_one_state_and_one_visible_action": _PATCH_012,
    "tests/unit/test_presentation.py::test_task_silent_tool_is_last_observed_action_not_live_claim": _PATCH_012,
    "tests/unit/test_presentation.py::test_task_truncated_process_detail_keeps_parameters_in_body": _PATCH_012,
    "tests/unit/test_task_clarify_summary.py::test_classic_clarify_keeps_existing_json_rendering": _PATCH_012,
    "tests/unit/test_task_clarify_summary.py::test_task_batch_question_summary_is_bounded_and_full_questions_remain_in_process": _PATCH_012,
    "tests/unit/test_task_clarify_summary.py::test_task_clarify_summarizes_known_question_without_json_or_state_mutation": _PATCH_012,
    "tests/unit/test_task_clarify_summary.py::test_task_keeps_argument_fallback_without_complete_current_process_detail": _PATCH_012,
    "tests/unit/test_task_clarify_summary.py::test_unknown_or_invalid_question_shape_uses_existing_fallback": _PATCH_012,
    "tests/unit/test_task_terminal_presentation.py::test_task_approval_stop_merges_only_event_notice": _PATCH_012,
    # v5.0.0 (2026-10-15): the legacy_hide=False case asserts the content-area tool_activity_
    # row is rendered; PATCH-012 hides it in every state. Passes on pristine v5.0.0.
    "tests/unit/test_card_preview.py::test_expanded_completed_history_keeps_successful_tools_without_default_body_duplicates[False]": _PATCH_012,
    # PATCH-024 classifies the hourglass family as HFC cards, not adapter-native text,
    # so core's text egress helper must not attempt a plain-text recall registration.
    "tests/unit/test_localized_transient_notices.py::test_actual_adapter_egress_preserves_plain_text_and_result": _PATCH_024,
}


def pytest_collection_modifyitems(config, items):
    for item in items:
        base = item.nodeid.split("[", 1)[0]
        # Exact parametrized ids win, so a patch can skip only the one case it changes.
        reason = INTENTIONAL_LOCAL_BEHAVIOUR.get(item.nodeid) or INTENTIONAL_LOCAL_BEHAVIOUR.get(base)
        if reason:
            item.add_marker(pytest.mark.skip(reason=reason))
