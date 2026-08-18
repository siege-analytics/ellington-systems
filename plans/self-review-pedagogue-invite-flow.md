# Self-Review: feat/pedagogue-invite-flow

Working as: software engineer, tech lead

Covers the pedagogue invite-token flow: `PedagogueInvite` model + migration, redemption view + form + templates, admin action + inline URL, email helper, password validator stack restoration, and 11 new tests. Closes F1 from the previous PR's self-review.

## Assumptions

Domain(s): software engineering
Geospatial cross-cut: no
Goal source: session brief plus follow-up pushback from Dheeraj on 2026-07-08 (session `260708-copper-coyote`): "Do you have a way for users to have accounts created as pedagogues?" — captured in `plans/design-note-pedagogue-invite-flow.md#source`.
Plan reference: plans/design-note-pedagogue-invite-flow.md
Pre-author-inventory: NONE
Trivial-against-state: Additive to the just-merged web layer (#17). No pre-existing invite / signup / auth-customization code to inventory. `grep -rn "PedagogueInvite\|redeem_invite\|InviteRedemption" src/` returns only lines from this branch. `AUTH_PASSWORD_VALIDATORS` was the only pre-existing auth-related setting; the change there is a widening (adding 3 validators) that only increases rejection surface for weak passwords — no existing user password is stored yet, so no migration risk.
Investigate-artifact: TRIVIAL
Pre-mortem-artifact: TRIVIAL
Hostile-review-artifact: plans/hostile-review-pedagogue-invite-flow.md
Project-contribution: Ships the account-creation path pedagogues need to actually use the confirmation forms shipped in #17. Without this, external guitar teachers cannot enter the system except by Dheeraj manually editing `auth_user` rows in the Django admin, which is not a viable model for real outreach. Directly closes F1 (uncovered non-pedagogue-user path) and unblocks the human-validation loop that produces the training signal the engine needs.

## Trivial-investigation declaration

Applies to both Investigate-artifact: TRIVIAL and Pre-mortem-artifact: TRIVIAL above.

Category: Additive user-management flow inside the already-scoped `[web]` extra. No production surface exists yet (no deploy target for Ellington web). The engine library is untouched. The only cross-cutting change (widening `AUTH_PASSWORD_VALIDATORS`) affects only user rows created after this branch merges, of which there are zero today.
Cannot produce error: Because (a) the invite endpoint is behind a 256-bit random token that a caller must possess to reach any write path, (b) the redemption transaction is atomic with `select_for_update`, so concurrent double-redemption is caught rather than silently allowed, (c) the diff adds no external side effects beyond `send_mail` — which uses the console backend in dev and is guarded by `settings.EMAIL_BACKEND`, (d) `git diff develop..HEAD -- src/ellington_systems/` is empty; engine consumers cannot experience regression.
Evidence: `git diff develop..HEAD --stat` shows changes under `src/ellington_web/confirmations/` (model, view, forms, admin, templates, migration 0002, mail helper), `src/ellington_web/ellington_web/` (settings + urls), `tests/webapp/test_invite_flow.py` (new file, 11 tests), `plans/` (design note + this artifact). Test suite: `python -m pytest` → `215 passed, 9 skipped in 1.19s`. New tests exercise: valid redemption creates User+Pedagogue+links to Confirmation; expired invite returns 410; already-redeemed invite returns 410; unknown token returns 404; password mismatch rejects; taken username rejects; common password rejects; email dispatch produces the expected URL; and the previously-uncovered non-pedagogue-user path now has a test.
Falsification: Would be falsified if any existing test failed against this branch's tip, if the redemption view silently allowed double-redemption under concurrent load, or if a pedagogue could be created without a valid unredeemed unexpired token. None of these hold: existing 204-test suite still passes; concurrent double-redemption is protected by `select_for_update` inside `transaction.atomic`; view code path from `redeem_invite` shows every failure mode returns before reaching the `Pedagogue.objects.create` call.

## Peer review (Junior's checklist -- mechanics, correctness, craft floor)

Shelves engaged: writing-code:1 (no speculative abstraction), writing-code:5 (no premature optimization), writing-tests:1 (behavior-scoped tests), writing-claims:1 (grep-verified claims below), writing-claims:2 (counted claims backed by tool output), writing-claims:3 (unquantified claims grounded in specific evidence).

**writing-code:1 — Model correctness.** Checked.
- `PedagogueInvite.token` is `secrets.token_urlsafe(32)` (default), `unique=True`, `editable=False`. Confirmed via inspection at `src/ellington_web/confirmations/models.py:_new_invite_token`.
- `redeemed_pedagogue` is `OneToOneField(Pedagogue, on_delete=SET_NULL, null=True)` so deleting an old Pedagogue doesn't cascade-delete the audit trail of the invite that produced them.
- `invited_by` uses `SET_NULL` for the same reason — the historical record survives an inviter leaving.
- Evidence: `python manage.py makemigrations confirmations` produced `0002_pedagogueinvite` with no warnings.

**writing-code:5 — Redemption view correctness.** Checked.
- All three failure modes (unknown / redeemed / expired) return before form processing.
- The `transaction.atomic` block re-fetches with `select_for_update()` and re-checks `is_redeemed` — this is the concurrent-double-redemption guard.
- On success, `login(request, user)` is called *after* the transaction commits, so a failure at that point (unlikely) does not leave the invite marked redeemed without a working session — actually, `login()` after commit means we've already marked the invite redeemed. Acceptable trade-off: worst case is invitee has to log in manually via `/admin/login/`. Filed as F5 (P3, informational).

**writing-tests:1 — Test coverage of the new flow.** Checked.
- 11 new tests, one per behavior: `test_invite_defaults`, `test_redeem_page_renders_for_valid_token`, `test_unknown_token_404s`, `test_expired_invite_shows_expiry_page`, `test_already_redeemed_invite_shows_redeemed_page`, `test_successful_redemption_creates_user_and_pedagogue`, `test_password_mismatch_rejects`, `test_taken_username_rejects`, `test_weak_password_rejects`, `test_send_invite_email_dispatches`, `test_authenticated_non_pedagogue_cannot_confirm` (this last one closes F1).
- Result: `pytest tests/webapp` → 24 passed (13 pre-existing + 11 new).

**writing-code:1 — Password validation.** Checked.
- Restored the full Django validator stack (`UserAttributeSimilarity`, `MinimumLength`, `CommonPassword`, `NumericPassword`). Confirmed rejection of "abc12345" by the CommonPasswordValidator via `test_weak_password_rejects`.
- The form calls `validate_password(pw)` inside `clean()` so the errors surface as field errors, not 500s.

**writing-code:5 — Email dispatch.** Checked.
- Uses Django's `send_mail` — no manual SMTP wiring.
- `EMAIL_BACKEND` env-overridable; default is console backend so dev doesn't accidentally send.
- `DEFAULT_FROM_EMAIL` env-overridable.
- Test exercises the `locmem` backend via a session-scoped `mailoutbox` fixture; asserts the invite URL is in the body.

**writing-claims:2 — Suite health.** Checked.
- Full suite after all changes: `python -m pytest` → `215 passed, 9 skipped in 1.19s`. The 9 skips are pre-existing `ELLINGTON_PLUGIN_PATH not set` gates. Delta from develop: +11 tests, all green.

## Lead review (Lead's adversarial pass -- did the Junior actually solve this?)

**software engineering domain:**

- *Approach fit:* Single-file model + a plain function view + templates + one admin action. Right size for one deliverable. Alternative (bring in `django-allauth`) would be over-scoped — allauth is 30k+ lines to solve for social login, email verification, and password reset that this project does not need today.
- *Affirmative standard: pedagogues can now be provisioned without hand-editing auth_user.* Holds. Evidence: `test_successful_redemption_creates_user_and_pedagogue` walks the full path admin-issue → redeem → confirm-a-note, all via HTTP, no ORM manipulation.
- *Affirmative standard: F1 (uncovered non-pedagogue-user path) is closed.* Holds. `test_authenticated_non_pedagogue_cannot_confirm` asserts the redirect and asserts zero confirmations created.
- *Affirmative standard: no engine regression.* Holds. `git diff develop..HEAD -- src/ellington_systems/` is empty. Engine tests (183 tests) pass.
- *Blast radius:* Bounded to `ellington_web.confirmations` + `ellington_web.ellington_web.settings` + `ellington_web.ellington_web.urls` + new tests. No engine files touched. No existing test modified.
- *Sequencing assumption:* The design pass (next slice) needs the invite templates as one of its inputs; that's fine because design is a template + CSS pass, not a functional rewrite. The audio-pipeline plan doc is independent.

**tech lead domain:**

- *Approach fit:* Ships the minimum viable invite flow — no email verification separate from invite (the invite IS the verification), no self-service password reset (invitee contacts admin to reissue), no rate limiting (token entropy makes it unnecessary). Each of these is a defensible YAGNI call given the audience is invited teachers, not the public internet.
- *Sequencing assumption:* Assumes the design pass and audio-pipeline plan doc are legitimately follow-up slices after this. Dheeraj's silence on the ordering after option-1 was chosen is being read (per saved feedback memory) as "all fine, pick and go" — proceeding with design pass next.

**Dismissals from peer review:**
- "No rate limiting on `/invite/<token>/`." — dismissed for this slice. Token entropy makes brute force infeasible. If we see abuse in logs after real pedagogues are online, we add django-ratelimit. Filed as F6.

## Findings

| ID | Priority | Description | Resolution |
|----|----------|-------------|------------|
| F5 | P3 | If `login(request, user)` raises after the invite is marked redeemed, invitee has to log in manually via `/admin/login/`. | Documented, not fixed. Acceptable degradation. |
| F6 | P3 | No rate limiting on the redemption endpoint. Token entropy makes brute force infeasible; adding rate limits pre-emptively is premature. | Deferred. Revisit if abuse is observed. |
| F7 | P2 | No test asserts the invite email actually contains the token (verified by asserting the full URL contains the token substring transitively via `build_invite_url`, but not directly). | Deferred — the URL construction is tested in `test_send_invite_email_dispatches`; a direct token-substring assertion would be redundant. |

Zero P1 findings.

Self-Review author: Craft Agent (session `260708-copper-coyote`)
