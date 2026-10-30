# Operations Button Grid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render operations-card actions as compact two-column Card JSON 2.0 rows while preserving action order, callbacks, divider, and footer.

**Architecture:** Keep `_operation_buttons(...)` responsible for producing valid direct Card JSON 2.0 buttons. Add a small renderer helper that groups those buttons in pairs and wraps each pair in a compact, content-width `column_set`; `render_operations_card(...)` inserts the rows at the current button position. No server, callback, or normal-card code changes.

**Tech Stack:** Python 3.9+, Feishu Card JSON 2.0, pytest.

## Global Constraints

- Use Card JSON 2.0 `column_set`; never reintroduce the removed JSON 1.0 `action` container.
- Keep button order and each button's existing `behaviors[0].value` unchanged.
- Use two content-width columns with `8px` spacing per row; an odd final row contains only its left column and reserves no empty half-row.
- Preserve the operations summary, divider, configured footer, and every normal streaming-card layout.
- Add no dependencies and do not modify `server.py`, `hook_runtime.py`, or Hermes files.

---

### Task 1: Render operations buttons in two-column rows

**Files:**
- Modify: `hermes_feishu_card/operations.py`
- Test: `tests/unit/test_operations.py`

**Interfaces:**
- Consumes: `_operation_buttons(report, operation, store) -> list[dict[str, object]]`
- Produces: `_operation_button_rows(buttons) -> list[dict[str, object]]`

- [ ] **Step 1: Write the failing tests**

Update the operations-card test helpers to collect buttons recursively from
`column_set.columns[].elements`. Assert four actions produce two rows with two
content-width columns each, `8px` spacing, stable row ids, unique element ids, unchanged
callback values, and the divider/footer still occupy the final two positions.
Add an odd-count state assertion using the `confirm_repair` state: its two
buttons form one complete row; use a one-button state such as `failed` to assert
the final row contains only one left column.

```python
rows = [item for item in card["body"]["elements"] if item.get("tag") == "column_set"]
assert [row["element_id"] for row in rows] == [
    "operations_row_0",
    "operations_row_1",
]
assert all(row["flex_mode"] == "none" for row in rows)
assert all(len(row["columns"]) == 2 for row in rows)
assert all(row["horizontal_spacing"] == "8px" for row in rows)
assert all(
    column["width"] == "auto" and "weight" not in column
    for row in rows
    for column in row["columns"]
)
assert [item.get("element_id") for item in card["body"]["elements"]][-2:] == [
    "operations_divider",
    "operations_footer",
]
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_operations.py -q
```

Expected: the new row assertions fail because buttons are still direct body elements.

- [ ] **Step 3: Implement the minimal two-column renderer**

Add a helper with the following shape and use `elements.extend(...)` with its
result in `render_operations_card(...)`:

```python
def _operation_button_rows(
    buttons: list[dict[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row_index in range(0, len(buttons), 2):
        pair = buttons[row_index : row_index + 2]
        rows.append(
            {
                "tag": "column_set",
                "element_id": f"operations_row_{row_index // 2}",
                "flex_mode": "none",
                "horizontal_spacing": "8px",
                "columns": [
                    {
                        "tag": "column",
                        "width": "auto",
                        "vertical_align": "top",
                        "elements": [button],
                    }
                    for button in pair
                ],
            }
        )
    return rows
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_operations.py tests/integration/test_server.py tests/integration/test_hook_runtime_integration.py -q
```

Expected: all selected tests pass; callbacks remain discoverable through nested V2 buttons.

- [ ] **Step 5: Run release verification and commit**

Run:

```bash
.venv/bin/python -m pytest -q
git diff --check
```

Expected: the full suite passes and `git diff --check` prints nothing.

Commit:

```bash
git add hermes_feishu_card/operations.py tests/unit/test_operations.py docs/superpowers/plans/2026-07-10-operations-button-grid.md
git commit -m "feat: arrange operations buttons in two columns"
```
