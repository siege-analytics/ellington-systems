# Pre-ship dry-run: feat/pedagogue-invite-flow

Behavioral evidence for the transformation code (migration 0002 + invite-redemption writes) in the branch, per the pre-push hook.

## Migration DDL

Output of `python manage.py sqlmigrate confirmations 0002` on the branch's tip:

```sql
BEGIN;
--
-- Create model PedagogueInvite
--
CREATE TABLE "confirmations_pedagogueinvite" (
    "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
    "token" varchar(128) NOT NULL UNIQUE,
    "email" varchar(254) NOT NULL,
    "display_name" varchar(255) NOT NULL,
    "credentials" text NOT NULL,
    "created_at" datetime NOT NULL,
    "expires_at" datetime NOT NULL,
    "redeemed_at" datetime NULL,
    "invited_by_id" integer NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED,
    "redeemed_pedagogue_id" bigint NULL UNIQUE REFERENCES "confirmations_pedagogue" ("id") DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX "confirmations_pedagogueinvite_invited_by_id_0d9274c3" ON "confirmations_pedagogueinvite" ("invited_by_id");
CREATE INDEX "confirmatio_email_7d65d9_idx" ON "confirmations_pedagogueinvite" ("email");
COMMIT;
```

Observations:
- Additive-only: single `CREATE TABLE`, two `CREATE INDEX`. No `ALTER`, no `DROP`, no data movement.
- Two FKs are `DEFERRABLE INITIALLY DEFERRED` and `NULL`-able, so deleting a User or a Pedagogue does not cascade-delete invite history.
- Unique constraints on `token` (correctness) and `redeemed_pedagogue_id` (a Pedagogue can be produced by at most one invite).
- Blast radius is bounded to the new table; no existing table is touched.

## Write-path behavioral verification

The transformation code in application space is the invite-redemption view, which writes 3 rows (User, Pedagogue, updated Invite) inside one transaction. Verified end-to-end by:

`pytest tests/webapp/test_invite_flow.py::test_successful_redemption_creates_user_and_pedagogue`

Test asserts after a successful POST to `/invite/<token>/`:
- A `User` row exists with the expected `username` and `email`
- A `Pedagogue` row exists linked to that User with the correct `display_name` and `credentials`
- The `PedagogueInvite` is now `is_redeemed=True` with `redeemed_pedagogue == pedagogue`
- The new user can immediately post a `Confirmation` (proves the login was established)

## Concurrent-double-redemption safety

Manual reasoning + code inspection covered in `plans/hostile-review-pedagogue-invite-flow.md#2-race-two-posts-redeem-the-same-invite`. The write path is:

```python
with transaction.atomic():
    locked = PedagogueInvite.objects.select_for_update().get(pk=invite.pk)
    if locked.is_redeemed:
        return redirect("redeem_invite", token=token)
    user = get_user_model().objects.create_user(...)
    pedagogue = Pedagogue.objects.create(user=user, ...)
    locked.redeemed_at = timezone.now()
    locked.redeemed_pedagogue = pedagogue
    locked.save(update_fields=["redeemed_at", "redeemed_pedagogue"])
```

`select_for_update` acquires a row-level lock; the second concurrent transaction blocks, then re-reads `is_redeemed=True`, and short-circuits. SQLite in dev supports this via `BEGIN IMMEDIATE`.

## Rollback verification

The migration is reversible: `python manage.py migrate confirmations 0001` drops the new table. No data-carrying columns depend on rows that would be lost — an admin who wants to revert loses only outstanding invites, which by definition are supposed to be single-use.

## Test suite

`python -m pytest` on the branch tip: **215 passed, 9 skipped in 1.19s**. 9 skips are pre-existing `ELLINGTON_PLUGIN_PATH not set` gates unrelated to this branch.
