# Design note: pedagogue invite-token flow

Authorizes the work on `feat/pedagogue-invite-flow`. Closes follow-up F1 from `plans/self-review-roster-and-confirmations.md`.

## Source

Session brief from Dheeraj to Craft Agent session `260708-copper-coyote` on 2026-07-08 and follow-up pushback on 2026-07-08 (same session): "Do you have a way for users to have accounts created as pedagogues?" — flagged as a real gap. The roster + confirmations PR (#17) shipped with pedagogues seeded by Django admin only. That is not usable for real external teachers.

## Deliverable

A one-time invite-token flow that lets a Django admin (or teammate) provision a Pedagogue account without hand-editing `auth_user` rows.

- **Admin issues an invite** via `PedagogueInvite` in the Django admin. Token, expiry (14 days default), display_name, email, credentials.
- **Invitee gets an email** (dev: console backend; prod: SMTP via env) with a `/invite/<token>/` link.
- **Invitee opens the link**, picks a username + password, submits.
- **Backend** creates a `User`, creates a `Pedagogue` linked to that user, marks the invite redeemed, logs the user in, redirects to `/masters/`.
- **Errors** (unknown / expired / already-redeemed / bad form) render a template with an explanation.

## Approach chosen

- One `PedagogueInvite` model per invite. Token = `secrets.token_urlsafe(32)`. Unique index on token.
- Redemption view is a plain function view; the transaction wraps the row-locking `select_for_update` re-check plus the User+Pedagogue creation plus the invite mark-redeemed. This makes double-redemption under concurrent requests a hard failure, not a silent one.
- Admin registers `PedagogueInvite` with a computed `redemption_url` readonly field so operators can copy/paste the link without opening a mailbox; also exposes a bulk action to (re)send the invite email.
- Default `AUTH_PASSWORD_VALIDATORS` restored to Django's full stack (previous PR only kept MinimumLength) — the invite flow is where user-controlled passwords first enter the system.
- `EMAIL_BACKEND` defaults to console for dev, overridable via `ELLINGTON_EMAIL_BACKEND`; `ELLINGTON_PUBLIC_BASE_URL` is where the invite URL is rooted (defaults to `http://localhost:8000`).

## Alternatives considered and rejected

- **Django-allauth / django-invitations.** Rejected for this slice — bringing in a full auth framework for one flow is over-scoped. We have exactly one create-account path (invite redemption) and one login path (Django built-in). Revisit if we need SSO or magic-link login for existing users.
- **Magic-link login without password.** Rejected because pedagogues will return repeatedly to accumulate reviews; forcing a password once is worth the friction to avoid sending an email per session.
- **Public sign-up.** Rejected explicitly per Dheeraj's brief: pedagogues are curated, not open enrollment.
- **SSO via authentik (sitting inactive in the workspace).** Rejected for this slice; it presupposes teachers already have accounts on siege-analytics tooling. Follow-up option if that changes.

## Falsifiable premises

- **Guitar teachers will accept a one-time email + password setup.** Falsifier: first outreach in Q4 2026 sees high drop-off between the invite email and account creation. Mitigation: monitor `PedagogueInvite.redeemed_at` fill rate; if <50% redeem, switch to magic-link.
- **`secrets.token_urlsafe(32)` is enough entropy for single-use invites with 14-day TTL.** Holds by construction (~256 bits). No mitigation needed.
- **Console email backend is fine for dev.** Holds; the mgmt commands + tests use `locmem` backend.

## Rollback

Additive: new model + migration + view + form + templates + admin action + mail helper. Reverting the commit drops the invite path; existing Pedagogue rows created via admin remain functional. Local DB migration is reversible (`migrate confirmations 0001`).

## Security surface introduced

- New public endpoint at `/invite/<token>/` — accepts POSTs with user-controlled username + password. CSRF-protected (Django default). Rate limiting is not in this slice; noted as follow-up if abuse is observed. `secrets.token_urlsafe(32)` makes brute-force enumeration infeasible even without rate limiting.
- New model stores an email + display name + credentials text. All strings, no file upload, no HTML rendered from these fields (templates autoescape).
- New auth users are created with `is_staff=False`, `is_superuser=False`. They gain permissions only through the linked `Pedagogue` row, which the confirmation views check.
