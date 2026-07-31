# Sequence — Login & Token Refresh

Lifecycle: access token lives in memory (Zustand); refresh token lives in an
httpOnly Secure SameSite=Lax cookie. Silent refresh on 401.

```mermaid
sequenceDiagram
    autonumber
    participant C as Client (Browser/Zustand)
    participant G as Gateway (FastAPI)
    participant P as PostgreSQL
    participant R as Redis

    C->>G: POST /api/v1/auth/login {email, password}
    Note over G: rate limit 5/min/IP (Redis)<br/>check ENABLE_SIGNUP / org status

    alt bad credentials
        G-->>C: 401 UNAUTHORIZED
    else success
        G->>P: verify bcrypt hash (credentials.password_hash)
        P-->>G: user + role + refresh_token_version
        G->>P: UPDATE users.last_login_at
        G->>P: INSERT audit_logs (LOGIN, ip, user_agent, trace_id)
        G-->>C: 200 { access_token (15min), user }
        C->>G: Set-Cookie: refresh_token (httpOnly, Secure, SameSite=Lax)
        Note over R: jti of refresh token tracked for rotation
    end

    Note over C: ── later: access token expired ──

    C->>G: POST /api/v1/auth/refresh (cookie)
    G->>G: verify refresh token + refresh_token_version
    G->>R: check jti not blacklisted
    alt valid
        G->>P: rotate refresh_token_version (bump)
        G-->>C: 200 { access_token (new), user }
    else invalid/revoked
        G-->>C: 401 TOKEN_EXPIRED → client clears session
    end

    Note over C: ── logout ──

    C->>G: POST /api/v1/auth/logout
    G->>P: bump refresh_token_version
    G->>R: blacklist jti until expiry
    G-->>C: 204
```

## Security posture

- **XSS** cannot steal the refresh token (httpOnly cookie).
- **CSRF** mitigated by SameSite=Lax + custom-header checks on state-changing requests.
- Logout revokes the entire token family by bumping `refresh_token_version`.
- Register is rate-limited 3/day/IP; signup can be disabled via `ENABLE_SIGNUP`.
