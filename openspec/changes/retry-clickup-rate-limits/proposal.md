## Why

The ClickUp completion pass (`launch-clickup-sync`'s scheduled walk over every active launch) can issue enough requests in one ten-minute tick to hit ClickUp's own rate limit. Today the shared client's `clickup-task-client` contract propagates every non-success response immediately, with no distinction for a transient `429 Too Many Requests` — so the moment the limit is hit mid-pass, every launch processed afterward in that tick fails outright (no list, no tasks, nothing corrected), and the whole scheduled job run ends in error. Observed directly in production worker logs on 2026-08-31: seven launches failed to converge in a single pass, each on a bare `429` from `create_list`/`create_task`/`read_list_state`, with no retry attempted before the failure was surfaced. The next opportunity is the following scheduled tick, and if the pass's call volume hasn't dropped, the same launches can be hit again.

## What Changes

- The ClickUp task client retries a request that receives an HTTP `429` response, waiting before retrying, instead of surfacing it to the caller immediately.
- Where ClickUp's response carries a `Retry-After` header, the wait honors it; where it does not, the client falls back to its own backoff.
- Retries are bounded: a request still eventually surfaces as a failure to the caller if ClickUp remains rate-limited past a fixed retry budget, preserving today's guarantee that a genuine failure is never silently absorbed.
- Every other non-success response (400, 404, 5xx, connection failure) continues to propagate on the first attempt exactly as today — this change is scoped to the one status code that means "slow down and try again," not to failures in general.

## Capabilities

### Modified Capabilities
- `clickup-task-client`: the requirement "A failed ClickUp request is surfaced to the caller" is narrowed for the `429` status specifically — such a response is now retried, with backoff, up to a bounded number of attempts, before it is treated as a failure and surfaced. Every other non-success response is unaffected and surfaces on the first attempt as it does today.

## Impact

- `src/commerce_ops/shared/infrastructure/driven/clickup_client.py`: every operation the capability enumerates (create/update task, create list, read a list's tasks, read a list's own state, add a tag, read a folder's Custom Fields, set a Custom Field value) gains the same bounded 429-retry behavior, since the existing requirement is exhaustive over all of them and a caller must not be able to tell them apart on this point.
- No change to `launch/infrastructure/driven/clickup_sync.py` or `launch/infrastructure/driving/clickup_sync_job.py`: they keep treating whatever the client ultimately surfaces exactly as they do today. The retry is internal to the client and invisible to every caller except through timing.
- Test coverage: the client's existing failure-propagation tests gain 429-specific cases (retried-then-succeeds, retried-past-budget-then-fails, `Retry-After` honored, other status codes unaffected).
