# Security Review Patterns

## P0 — Critical
- SQL injection (unescaped user input in queries)
- XSS (unsanitized user output in HTML/JS)
- Hardcoded secrets (API keys, passwords, tokens in source)
- Authentication bypass (missing auth checks, default credentials)
- Path traversal (unsanitized file paths with ../)
- Command injection (user input in shell commands)
- eval() / exec() on untrusted input
- Insecure deserialization (pickle, yaml.load on untrusted data)

## P1 — High
- Missing input validation
- Missing rate limiting
- Insecure random number generation (not using secrets module)
- Race conditions in auth/authorization checks
- Sensitive data in logs
- Missing CSRF protection
- Open redirect
# test autoreview comment
