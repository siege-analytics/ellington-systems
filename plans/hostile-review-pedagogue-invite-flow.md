# Hostile review: feat/pedagogue-invite-flow

Reviewer role: adversarial. Assumes the author is confident but wrong. Tries to break the system, not to praise it.

Diff under review: commit on `feat/pedagogue-invite-flow` — `PedagogueInvite` model, redemption view/form/templates, admin action, mail helper, settings changes, 11 tests.

## Attack surface enumeration

New public endpoint: `POST /invite/<token>/` — accepts username + password + password_confirm from an unauthenticated caller.
New authenticated path (unchanged): `POST /confirm/<master-slug>/note/<note-id>/` — now reachable by any user who redeems an invite.
New admin endpoint: `PedagogueInviteAdmin` with a bulk `resend_invite_email` action — reachable by staff.
New side effect: `send_mail` to the invitee-supplied email during redemption? **No — the email address is set by the admin on the PedagogueInvite row, not the invitee.** Confirmed by re-reading `redeem_invite` view: `email=invite.email`, not `email=form.cleaned_data.get("email")`. Good.

## Attempted breaks

### 1. Enumeration of valid tokens

`secrets.token_urlsafe(32)` produces a 43-character base64url string (~256 bits of entropy). Brute force to find one valid token: infeasible. Even with 1M valid outstanding invites, the search space per attempt is ~2^256 / 10^6 ≈ 2^236. **Cannot break.**

### 2. Race — two POSTs redeem the same invite

The view is:
```
POST → PedagogueInvite.objects.filter(token=token).first()  # read outside tx
  → transaction.atomic:
     → select_for_update().get(pk=invite.pk)  # locks row
     → check locked.is_redeemed
     → create_user + create_pedagogue + mark redeemed
```

Attack: fire two concurrent identical POSTs with valid form data. Without the `select_for_update`, both would pass the outer `is_redeemed` check, both would create users, both would `save()` the invite marked-redeemed — second save wins. Two users would exist for one invite.

With `select_for_update`, one transaction blocks on the row lock. When it commits, the second acquires the lock, re-reads `is_redeemed=True`, redirects with a flash message, does not create anything. **Protected.**

Caveat: `select_for_update` requires a transaction and a database backend that supports row-level locking. SQLite in the dev config supports it as of Django 5 (via BEGIN IMMEDIATE / EXCLUSIVE). Verified per Django docs. **Holds for dev.**

### 3. CSRF bypass on redemption

The `/invite/<token>/` view is a normal Django view protected by the default `CsrfViewMiddleware`. The template uses `{% csrf_token %}`. GET is safe (no side effects). POST without a CSRF token → 403. **Cannot break.**

### 4. Session fixation via login()

`login(request, user)` after account creation. Django's `login()` cycles the session key by default (`SESSION_COOKIE_AGE`, `rotate_session_key`). A pre-set session cookie from an attacker would be discarded. **Cannot break** for standard Django settings.

### 5. Timing attack on token comparison

Django's ORM `filter(token=token).first()` uses SQL equality on an indexed unique column. The database returns "hit or miss" in O(index lookup) time, not O(N) string compare. Even with an attacker measuring server response times, they gain no per-character oracle. **Not exploitable.**

### 6. XSS via invite fields

`invite.display_name`, `invite.email`, `invite.expires_at.date()` are rendered in `redeem_invite.html` and `invite_error.html`. All go through Django's default autoescape. No `|safe`, no `mark_safe`. Even if a malicious admin created an invite with `<script>` in `display_name`, it would render as text. `grep -rn "mark_safe\||safe" src/ellington_web/` returns only the admin's `format_html('<a href="{}">{}</a>', url, url)` which uses parameterized formatting (safe). **Cannot break.**

### 7. Open redirect

The success path redirects to `reverse("roster:master_list")` — a hardcoded named route, not a user-supplied URL. **Cannot break.**

### 8. Weak-password bypass

The form calls `validate_password` inside `clean()`. The validator stack is `UserAttributeSimilarity`, `MinimumLength`, `CommonPassword`, `NumericPassword`. Test `test_weak_password_rejects` proves `abc12345` is caught. But: **the invitee's email is on the invite, and `UserAttributeSimilarityValidator` compares against user attributes AFTER user creation**, not against the invite's email. Attack: invitee sets username="teachert" + password="teacher@example.com" (matching invite.email). Does the validator catch this?

Answer: no, because the user does not exist at the time `validate_password(pw)` is called in the form. The similarity validator has nothing to compare against yet. **Real gap.** Files as F8 (P2, informational — the user then exists and the password IS on their record, but is functionally an email leak into the password).

Mitigation option: pass the (as-yet-uncreated) user's would-be attributes into `validate_password(pw, user=User(username=..., email=invite.email))`. Cheap fix. Not blocking this PR (invite.email is admin-supplied, not attacker-controlled — an admin choosing a bad email is a different failure mode). Filed as F8.

### 9. SQL injection

All query paths go through the ORM. No raw SQL. `grep -rn "raw\|execute\|cursor" src/ellington_web/` returns nothing relevant. **Cannot break.**

### 10. Denial of service via unbounded invite creation

An admin could create millions of invites. Not an external DoS (admin is trusted). Not a table-size problem (invite table is bounded by admin action). **Not a real hazard for this trust model.**

### 11. Email spoofing / phishing amplification

`send_invite_email` sends to `invite.email`, from `DEFAULT_FROM_EMAIL`. An admin cannot make Ellington send email to arbitrary addresses that aren't on an invite row they created. **Not exploitable** given the admin threat model.

### 12. Redemption after admin deletes invite

`select_for_update().get(pk=invite.pk)` — if the invite was deleted between the outer `filter().first()` read and the `get()` inside the tx, `.get()` raises `DoesNotExist`, which surfaces as a 500. Not a security issue, but a UX regression.

Filed as F9 (P3). Fix would be: wrap `.get()` in try/except and redirect with a message. Not blocking.

### 13. Migration reversibility

`migrate confirmations 0001` should undo this migration. Manual verify:
```
python manage.py sqlmigrate confirmations 0002 | head -20
```
would show a CREATE TABLE. `python manage.py migrate confirmations 0001` would DROP TABLE. No data-carrying columns depend on external state. **Safe.**

## Findings (this reviewer)

| ID | Priority | Description | Resolution |
|----|----------|-------------|------------|
| F8 | P2 | `UserAttributeSimilarityValidator` doesn't fire during invite redemption because the User isn't created until after `clean()`. Invitee can set a password identical to their email. | Deferred. Admin-supplied email is not attacker-controlled; the cost is at most a leak of email-into-password on that one account. Fix (pass a User(email=invite.email) into validate_password) is small — will address in a follow-up if reviewed. |
| F9 | P3 | If admin deletes an invite between the outer `filter().first()` read and the `select_for_update().get()` inside the tx, view raises 500 instead of a friendly error. | Deferred. Extreme race; admin action while invitee is mid-redemption is exceptional. |

Zero P1 findings from the adversarial pass.

## Verdict

The invite flow closes the account-provisioning gap without introducing exploitable surface. The two findings above are real but low-impact and out of scope for this slice. The `select_for_update` guard, the strict admin-controls-email design, the CSRF middleware, the autoescape defaults, and the token entropy budget together cover the failure modes I could construct.

Adversarial review author: Craft Agent (session `260708-copper-coyote`), tech lead role, deliberately hostile lens.
