# LTI 1.3 Integration — Technical Spec
**Date:** May 2026 | **Author:** Ravi

---

## New DB Table: lti_platforms

```sql
CREATE TABLE lti_platforms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    issuer VARCHAR(512) NOT NULL,          -- Moodle URL (platform identifier)
    client_id VARCHAR(255) NOT NULL,       -- Issued by Moodle
    auth_login_url VARCHAR(512) NOT NULL,  -- Moodle OIDC auth endpoint
    auth_token_url VARCHAR(512) NOT NULL,  -- Moodle token endpoint
    key_set_url VARCHAR(512) NOT NULL,     -- Moodle JWKS endpoint
    deployment_ids JSONB NOT NULL DEFAULT '[]', -- ["1", "2"]
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(issuer, client_id)
);
```

## Columns Added to Existing Tables

```sql
-- learning_spaces
ALTER TABLE learning_spaces ADD COLUMN slug VARCHAR(120);
CREATE UNIQUE INDEX uq_spaces_tenant_slug ON learning_spaces(tenant_id, slug)
    WHERE slug IS NOT NULL;

-- users
ALTER TABLE users ADD COLUMN lti_sub VARCHAR(255);
-- lti_sub = "<issuer>::<sub>" (namespaced to avoid collisions between platforms)
CREATE INDEX ix_users_lti_sub ON users(lti_sub) WHERE lti_sub IS NOT NULL;
```

---

## New Files

### app/models/lti.py
SQLAlchemy ORM model for `lti_platforms`.

### app/schemas/lti.py
- `LTIPlatformCreate` — admin registration payload
- `LTIPlatformResponse` — list/detail response (includes axis-ai config values to copy)
- `LTIPlatformUpdate` — patch fields

### app/services/lti.py
Core LTI 1.3 logic:
- `get_platform(db, issuer, client_id)` → LTIPlatform | None
- `fetch_platform_jwks(key_set_url)` → list of JWK dicts (Redis-cached 1h)
- `validate_id_token(id_token, platform, nonce)` → dict of claims
- `map_lti_role(roles: list[str])` → "admin" | "creator" | "learner"
- `jit_provision_user(db, tenant_id, claims, role)` → AxisUser (create or update)
- `generate_ott(user_id, redirect_to)` → str (stores in Redis 30s)
- `consume_ott(ott)` → dict | None

### app/api/v1/lti.py
All LTI-related endpoints. Mounted at `/` (not under `/api/v1/`) for the public endpoints,
and under `/api/v1/admin/lti` for admin CRUD.

---

## Endpoints

### Public LTI Endpoints (no auth)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/.well-known/jwks.json` | axis-ai public key in JWK format |
| GET/POST | `/lti/login` | OIDC login initiation (step 2 of flow) |
| POST | `/lti/launch` | JWT validation + user provisioning + OTT redirect (step 4–9) |

### Internal Token Exchange

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/lti-exchange` | Exchange OTT for access+refresh tokens (called by Next.js server-side) |

### Admin Platform CRUD (requires admin JWT)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/admin/lti/platforms` | List all platforms |
| POST | `/api/v1/admin/lti/platforms` | Register new platform |
| GET | `/api/v1/admin/lti/platforms/{id}` | Get platform + show axis-ai config values |
| PUT | `/api/v1/admin/lti/platforms/{id}` | Update platform |
| DELETE | `/api/v1/admin/lti/platforms/{id}` | Delete platform |

---

## JWT Validation Logic (lti/launch)

```python
# 1. Parse id_token header (no verification) → get "kid"
# 2. Redis lookup: f"lti:state:{state}" → {nonce, target_link_uri} or 404
# 3. DELETE state from Redis (one-time)
# 4. Fetch platform JWKS (key_set_url), cached in Redis as f"lti:jwks:{key_set_url}"
# 5. Find JWK matching kid
# 6. Convert JWK → RSA public key (cryptography library)
# 7. Decode JWT: verify signature, iss==platform.issuer, aud==platform.client_id,
#    exp > now, nonce == stored nonce
# 8. Check deployment_id in platform.deployment_ids
# 9. Extract:
#    - sub → user identifier
#    - email, name, given_name, family_name
#    - https://purl.imsglobal.org/spec/lti/claim/roles → role list
#    - https://purl.imsglobal.org/spec/lti/claim/custom → {"space_slug": "..."}
```

---

## OTT (One-Time Token) Cookie Handoff

The LTI launch happens at `axisai.edzlms.com` (backend).
The frontend is at `axis.edzlms.com` — different domain, cannot share cookies directly.

**Solution:**
```
Backend (axisai.edzlms.com):
  → Validates LTI, provisions user, issues access+refresh tokens
  → Generates OTT: 32-byte hex, stores in Redis as:
    f"lti:ott:{ott}" = {access_token, refresh_token, user_id}  TTL 30s
  → Redirects to: https://axis.edzlms.com/lti/complete?ott=<ott>&to=<redirect_path>

Frontend (axis.edzlms.com):
  /lti/complete/page.tsx (server component):
    → Reads ?ott from URL
    → Calls POST /api/auth/lti-exchange with {ott}
    → /api/auth/lti-exchange/route.ts:
        → Calls POST axisai.edzlms.com/api/v1/auth/lti-exchange with {ott}
        → Gets back {access_token, refresh_token, user}
        → Sets axis_access cookie (httpOnly: false, 15min)
        → Sets axis_refresh cookie (httpOnly: true, 7 days)
        → Returns {ok: true, to: "/learn/python-basics"}
    → Client redirects to `to` param (validated against allowlist)
```

---

## RSA Key Pair (JWKS)

axis-ai generates and exposes its own RSA-2048 key pair.
Moodle uses this to verify tokens axis-ai signs (e.g. for service calls — not required for basic launch but needed for LTI Advantage).

**Key storage:**
- `LTI_PRIVATE_KEY_PEM` in .env (PEM format, newlines escaped as \n)
- `LTI_KEY_ID` in .env (short string, e.g. "axis-ai-key-1")
- If not set: auto-generate on startup (dev mode only — logs warning)
- Admin can hit `POST /api/v1/admin/lti/generate-keypair` to get a new PEM pair to paste into .env

**JWKS response format:**
```json
{
  "keys": [{
    "kty": "RSA",
    "kid": "axis-ai-key-1",
    "use": "sig",
    "alg": "RS256",
    "n": "<base64url modulus>",
    "e": "AQAB"
  }]
}
```

---

## Redis Key Namespaces

| Key | Value | TTL |
|-----|-------|-----|
| `lti:state:{state}` | `{nonce, target_link_uri, issuer, client_id}` | 600s |
| `lti:jwks:{key_set_url_hash}` | JWKS JSON string | 3600s |
| `lti:ott:{ott}` | `{access_token, refresh_token}` | 30s |

---

## Slug — Implementation Details

- Stored as `slug VARCHAR(120)` on `learning_spaces`
- Unique constraint: `(tenant_id, slug)` — partial index (WHERE slug IS NOT NULL)
- Auto-generated from title: lowercase, replace spaces/special chars with `-`, trim to 80 chars
- Editable by creator/admin in space create and edit modals
- Exposed in SpaceResponse schema
- Space list API returns slug (needed for creator reference)
- Lookup endpoint used at launch: `SELECT id FROM learning_spaces WHERE tenant_id=? AND slug=?`

---

## Dependencies

No new pip packages needed:
- `cryptography` — already in venv (RSA key ops, JWK conversion)
- `python-jose[cryptography]` — add if not present (JWT decode/verify)
- `httpx` — already in venv (JWKS fetch)
- `redis` — already in venv (state/nonce/OTT)

Add to `pyproject.toml` if missing:
```toml
"python-jose[cryptography]>=3.3.0",
```

---

## Moodle Setup Instructions (for customer)

```
In Moodle: Site admin → Plugins → External tool → Manage tools → Add preconfigured tool

Tool name: axis-ai
Tool URL: https://axisai.edzlms.com/lti/launch
LTI version: LTI 1.3
Public key type: Keyset URL
Public keyset: https://axisai.edzlms.com/.well-known/jwks.json
Initiate login URL: https://axisai.edzlms.com/lti/login
Redirection URI(s): https://axisai.edzlms.com/lti/launch
Default launch container: New window (or Embed)

Save → Moodle shows you: Platform ID, Client ID, Public keyset URL, Access token URL, Auth URL
→ Enter these into axis-ai Admin → LTI Platforms → Register New Platform
```

---

## Testing Checklist

```
1. Register a test Moodle platform in axis-ai admin
2. Configure External Tool in test Moodle site
3. Add tool to a Moodle course as editingteacher
4. Launch as Moodle student → confirm Creator role NOT given
5. Launch as Moodle editingteacher → confirm Creator role
6. Add custom param space_slug=<slug> → confirm redirect to correct space
7. Launch with invalid slug → confirm fallback to /learn dashboard
8. Launch twice (confirm nonce one-time use works — second replay should fail)
9. Disable LTI platform in axis-ai → launch should fail gracefully
10. Verify /.well-known/jwks.json returns valid JWK
```
