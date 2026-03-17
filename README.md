Password hashing and migration

This project hashes user passwords using a two-step approach to avoid bcrypt's 72-byte input limit and to maintain compatibility with a PBKDF2 fallback.

Current scheme

- When a user registers, we first compute the SHA-256 hex digest of the raw password (64 hex chars). We then pass that digest into the configured `pwd_context` hash function (bcrypt via `passlib[bcrypt]` in production, or a PBKDF2 fallback in lightweight environments).
- On login, the same SHA-256 digest is computed from the submitted password and verified with the configured `pwd_context` verify method.

Why SHA-256 pre-hashing?

- Bcrypt has a 72-byte input limit. Pre-hashing with SHA-256 produces a fixed-length input and avoids accidental truncation which can cause errors or weaken security.
- Pre-hashing is a common and acceptable pattern when done consistently for both hashing and verification.

Migration guidance

If you have existing users whose password hashes were produced by a different scheme (for example: direct `pwd_context.hash(raw_password)` without pre-hashing), you'll need to migrate them to the new scheme.

Recommended approaches:

1) Transparent migration on first login (recommended)
- On login, attempt verification using the new scheme (SHA-256 pre-hash) first.
- If verification fails, try the legacy verification (e.g., `pwd_context.verify(raw_password, stored_hash)`). If the legacy check succeeds, re-hash the password using the new scheme and update the stored hash. This transparently upgrades the user's password hash on next login.

2) Force password reset
- Require all users to reset their password via email reset flow. This is simplest and safest from a verification standpoint but requires user interaction.

3) Bulk migration (only if you can safely verify credentials)
- If you have plaintext passwords (rare and not recommended) or can otherwise re-obtain them securely, re-hash them with the new scheme.

Implementation notes

- We provide helper functions in `backend/main.py`:
  - `hash_password(password: str) -> str` — computes sha256(password) and then uses `pwd_context.hash(...)`.
  - `verify_password(password: str, hashed_password: str) -> bool` — computes sha256(password) and calls `pwd_context.verify(...)`.

- To implement transparent migration, on a successful legacy verify you can run:

  row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
  if row:
      new_hash = hash_password(raw_password)
      conn.execute("UPDATE users SET password = ? WHERE id = ?", (new_hash, row[0]))
      conn.commit()

Security notes

- Use `passlib[bcrypt]` or a stronger modern hasher (e.g., Argon2) in production.
- Always serve your app over HTTPS and set secure cookie flags on session cookies.
- Avoid storing or logging plaintext passwords.

If you want, I can implement the transparent migration helper and wire it into the login handler so legacy hashes are upgraded automatically on first successful login. Would you like me to do that now?
