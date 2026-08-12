# Facemarket LiveKit plugin final-fix report

**Date:** 2026-08-12

**Branch:** `codex/facemarket-livekit-plugin`

**Input:** `final-findings.md`

## Status

All Critical, Important, and Minor release-hardening findings were fixed in the single allowed final-review wave. The changes were regression-first, focused on the reviewed contracts, and verified as source, runtime behavior, and built artifacts.

## Fixes

1. **Wheel namespace and fresh import**
   - Changed Hatchling wheel selection from `livekit/plugins/facemarket` to `livekit`, preserving the `livekit/plugins/facemarket` namespace instead of rewriting it to top-level `facemarket`.
   - Added archive and fresh-target install/import tests.
   - Verified the release wheel imports `livekit.plugins.facemarket` from the isolated target directory.

2. **Real LiveKit Room contract and configured RTC URL**
   - Added optional constructor `livekit_url: str | None = None`, with `LIVEKIT_URL` fallback.
   - `start()` now sends the configured URL and validates connectivity with `room.isconnected()`.
   - Replaced the old fake fields with a narrow `isconnected()` fake and added an installed `rtc.Room` contract test confirming that it has `isconnected()` and no public `url`.

3. **Interrupt protocol**
   - `interrupt(request_id=None)` now publishes exact event `control.interrupt`, reliably, with the optional request correlation ID.

4. **Payloadless known inbound events**
   - Omitted `data` now normalizes to `{}` for known events.
   - Explicit `null`, list, scalar, or string data remains invalid.
   - Added coverage for payloadless `scene.ready`, `system.idleTrigger`, and `session.closing`; events with required fields still fail after normalization when those fields are missing.

5. **Stop cancellation and retry semantics**
   - All callers await the shared stop task through `asyncio.shield()`.
   - Canceling one waiter no longer cancels teardown for other callers.
   - A failed or internally canceled stop task is cleared deterministically for retry.
   - Remote stop success is remembered, so a later owned-client teardown retry does not send a duplicate remote stop request.
   - Added coverage for concurrent waiter cancellation, internal cancellation, API failure retry, and owned-client close failure retry.

6. **Turn and response correlation**
   - Separated the current user-turn request ID, frozen active-response request ID, and per-utterance response ID.
   - Response start/finish use the same frozen request/response IDs even when a new user turn barges in.
   - Completed turns are consumed at response finish; consecutive proactive utterances receive independent request and response IDs.

7. **Asynchronous prompt-start rollback**
   - The publication boundary now returns its tracked task and reports success/failure to the bridge.
   - A failed prompt-start clears prompt mode and never emits `response.audio.promptFinish`.
   - Local error callbacks are dispatched directly; no error event is recursively published to the room.
   - Reset now precedes publication cancellation during stop, preventing a canceled pending prompt start from scheduling a late finish event.

8. **Example lifecycle**
   - Verified the installed LiveKit Agents API: `JobContext.add_shutdown_callback` accepts an async no-argument callback.
   - The example registers `avatar.stop` for actual job shutdown rather than calling it immediately after `AgentSession.start()`.
   - `FACEMARKET_PRESERVE_SESSION=true` intentionally omits the stop callback for later explicit reconnect.

9. **Configuration hardening**
   - Constructor values now fall back to environment values only when `None`; explicit blanks are rejected.
   - Added validation for `avatar_id`, Facemarket configuration, LiveKit URL/credentials, room fields, and positive renderer token TTL.
   - Replaced `typing.Self` with a Python-3.10-safe annotation to match the declared interpreter range.

10. **Sdist hardening**
    - Excluded `.superpowers` and `docs/superpowers` workflow artifacts from builds.
    - Added an sdist archive-content regression test.

English and Chinese READMEs, the approved design, and implementation-plan interface notes were updated to match the final API and lifecycle behavior.

## TDD evidence

- The first focused red run produced 35 failures for the reviewed missing/broken behaviors, including flattened wheel layout, failed isolated import, absent `livekit_url`, old Room fields, payloadless protocol rejection, mutable correlation, immediate example stop, and workflow files in the sdist.
- A separate prompt-stop race test failed by observing a late `response.audio.finish` after cancellation; resetting the bridge before tracked-task cancellation made it pass.
- A Python 3.10 compatibility regression reproduced the `typing.Self` import failure before the annotation was corrected.
- Each focused regression passed after its minimal implementation change, followed by the full suite.

## Verification

- Ruff: `.venv/bin/python -m ruff check .` — passed.
- Black: `.venv/bin/python -m black --check livekit tests examples` — passed.
- Compile: `.venv/bin/python -m compileall -q livekit examples` — passed.
- Tests: `.venv/bin/python -m pytest -q` — `100 passed in 2.35s` in the final pre-commit run.
- Standard isolated build: `.venv/bin/python -m build --outdir /private/tmp/facemarket-release.pcBrm1/dist` — passed after network approval installed Hatchling in isolated build environments.
- Twine: `.venv/bin/python -m twine check /private/tmp/facemarket-release.pcBrm1/dist/*` — both wheel and sdist passed.
- Wheel archive: 14 files; contains `livekit/plugins/facemarket/__init__.py`; contains no top-level `facemarket/` package or workflow artifacts.
- Sdist archive: 28 files; contains package, tests, example, and public documentation; contains no `.superpowers` or `docs/superpowers` paths.
- Fresh wheel target: installed with `--no-deps` into `/private/tmp/facemarket-wheel-target.unE8Ir`; isolated import printed `0.1.0` and resolved to `/private/tmp/facemarket-wheel-target.unE8Ir/livekit/plugins/facemarket/__init__.py`.
- Diff hygiene: `git diff --check` passed during self-review.

## Remaining concerns

- Python 3.10 itself is not installed in this local environment, so the release was executed on Python 3.14. The only plugin use of a 3.11-only typing symbol was removed, and a guarded import regression protects that boundary, but an actual Python 3.10 CI job remains the strongest cross-version proof.
- No real credentialed Facemarket/LiveKit end-to-end run was performed; this remains outside the approved MVP and the repository tests use the documented fake/external boundaries.
