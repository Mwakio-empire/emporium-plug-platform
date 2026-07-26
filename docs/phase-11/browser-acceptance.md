# Phase 11 browser acceptance

Executed on 22 July 2026 against the local Django server with the safe local cache and notification providers.

## Journey

1. Signed in through the real customer login form using a synthetic account, then assigned the synthetic session an authorized test role without bypassing the notification view.
2. Opened `/notifications/operations/`.
3. Confirmed the page identified the test user as Super Admin and exposed the Notifications navigation item.
4. Confirmed a manual payment-notification failure showed event, branch, safe reference, attempts and error code.
5. Confirmed the recipient was masked as `***0222` and the rendered message body was absent.
6. Submitted a four-character evidence note and observed the required eight-character validation error; the item stayed open.
7. Submitted a meaningful evidence note and observed the success message.
8. Confirmed the item left the manual queue and appeared as `Manually Resolved` in recent state.
9. Queried the resulting record and confirmed the resolving username, timestamp and evidence note were retained.
10. Removed the synthetic account and notification fixture after testing.

## Result

Pass. Branch isolation, role denial and cross-branch resolution denial are additionally covered by automated tests.

The first ordinary local-server attempt demonstrated that Redis is required by normal development settings for login throttling. Acceptance was repeated using the documented `LOCAL_CACHE_ONLY=True` isolated UI mode; this did not alter notification business behavior.
