# Async Operations Task 3 Report

## Status

DONE

## Scope Delivered

- Added `OPERATIONS_ACTION_TIMEOUT_SECONDS = 2.0` and applied it only to the Gateway's `operations.select` local `/card/actions` POST.
- Kept the normal streaming, terminal, and `interaction.select` timeout paths unchanged.
- Gateway callbacks return the Sidecar's immediate in-progress card and retain the transport secret/profile context for the returned successor operation.
- Updated existing real-HTTP Gateway integration expectations to distinguish immediate in-progress callbacks from later same-card completion PATCHes.

## RED Evidence

- `test_operations_select_passes_admission_and_forwards_profile_context` initially failed with `assert 5.0 == 2.0`, proving the operations forward path still used the previous timeout.

## GREEN Evidence

- `.venv/bin/python -m pytest tests/unit/test_hook_runtime.py tests/integration/test_hook_runtime_integration.py tests/unit/test_operations.py tests/integration/test_server.py -q`: 404 passed in 17.51s.

## Boundary

- No real Feishu/Lark smoke run was performed; coverage uses the installed adapter, real local Sidecar HTTP, and controlled background completion.
