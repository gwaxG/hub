---
repo: [wilson]
mr: [wilson!2865]
verified_at: 2026-11-12
---

# Wilson endpoints for Cognito JIT user migration

- `server/api/views/auth_jit_migration_view.py` holds two POST endpoints, hidden from the OpenAPI schema, that the Cognito user-migration Lambda calls:
  - `auth/verify-credentials` is for sign-in. It takes a username and password and returns the user's profile and flags.
  - `auth/lookup-user` is for forgot-password (added in !2865, by BenjaminKalfa). It takes only a username and returns email, first_name and last_name. It answers 404 for an unknown user or one with no email, and 403 for an inactive user.
- Both endpoints check the `X-Migration-Key` header against `VERIFY_CREDENTIALS_API_KEY`, using `IsMigrationLambda`. That key comes from SSM only in prod; other envs fall back to an empty key, so these endpoints answer 401 there.
- Gotcha: both match `username` exactly, while web login (`session_view.py`) finds the user by `email__iexact`. A user who types their email with different capitalisation gets a 404 from lookup-user. This was raised in the !2865 review.
- Keep these endpoints POST so usernames, which are emails, stay out of URLs and access logs.
