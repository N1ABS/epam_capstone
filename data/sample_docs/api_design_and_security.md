# API Design and Security — Personal Reference

## REST API Design Principles

### Resource Naming

- Use **nouns**, not verbs: `/documents` not `/getDocuments`.
- Use **plural** for collections: `/documents`, `/users`.
- Use **hierarchy** for relationships: `/users/{id}/documents`.
- Use **query parameters** for filtering and pagination:
  `/documents?topic=ml&limit=20&offset=40`

### HTTP Methods

| Method | Use | Idempotent? | Safe? |
|---|---|---|---|
| GET | Read a resource or collection | ✅ | ✅ |
| POST | Create a new resource | ❌ | ❌ |
| PUT | Replace a resource entirely | ✅ | ❌ |
| PATCH | Partial update | ❌ | ❌ |
| DELETE | Remove a resource | ✅ | ❌ |

### Status Codes

| Code | Meaning | Common use |
|---|---|---|
| 200 OK | Success | GET, PUT, PATCH |
| 201 Created | Resource created | POST |
| 204 No Content | Success, no body | DELETE |
| 400 Bad Request | Invalid input | Validation errors |
| 401 Unauthorised | Not authenticated | Missing/invalid token |
| 403 Forbidden | Authenticated but not authorised | Insufficient permissions |
| 404 Not Found | Resource does not exist | Wrong ID |
| 422 Unprocessable Entity | Semantically invalid input | FastAPI validation |
| 429 Too Many Requests | Rate limit exceeded | Throttling |
| 500 Internal Server Error | Unhandled server error | Bug / crash |

---

## Authentication Patterns

### API Keys

Simple; suitable for server-to-server communication where the client is trusted.

```http
Authorization: Bearer sk-abc123...
```

**Best practices:**
- Hash stored keys with SHA-256; never store plaintext keys in the database.
- Allow key rotation without downtime (support multiple active keys per user).
- Scope keys to specific operations (read-only vs read-write).

### JWT (JSON Web Tokens)

Stateless; token contains signed claims. Suitable for user-facing APIs.

```
Header.Payload.Signature
```

**Payload example:**
```json
{"sub": "user_id_123", "exp": 1748000000, "role": "user"}
```

**Pitfalls:**
- Validate `exp` (expiry), `iss` (issuer), and `aud` (audience) on every request.
- Use asymmetric signing (RS256) if tokens are verified by multiple services.
- Short-lived access tokens (15 min) + longer-lived refresh tokens (7 days).

### Session Tokens

Server-side sessions; token is an opaque random string mapped to session data in a DB.
- Use `secrets.token_hex(32)` (256-bit entropy) for token generation.
- Store a hash of the token, not the token itself.
- Set `HttpOnly; Secure; SameSite=Strict` cookie flags.

---

## Input Validation

**Validate at every trust boundary** — do not trust data from the UI, external APIs,
or even your own microservices.

Validation layers:
1. **Length and type checks** — reject obviously malformed input early.
2. **Schema validation** — use Pydantic or JSON Schema to enforce structure.
3. **Business rule validation** — check domain-specific constraints.
4. **Sanitisation** — strip or escape characters that could cause injection.

**Prompt injection** (LLM-specific):
```python
import re

_INJECTION_PATTERNS = [
    r"ignore\s+(previous|prior|all)\s+instructions",
    r"forget\s+everything",
    r"reveal\s+(your\s+)?(system\s+prompt|instructions)",
    r"jailbreak",
    r"do\s+anything\s+now",
]
_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)

def validate_query(query: str) -> str:
    query = query.strip()
    if not query:
        raise ValueError("Query cannot be empty.")
    if len(query) > 2000:
        raise ValueError("Query too long.")
    if _RE.search(query):
        raise ValueError("Query contains disallowed patterns.")
    return query
```

---

## Rate Limiting

Prevent API abuse and protect free-tier quotas.

**Sliding-window algorithm** (preferred over fixed-window):
- Maintain a queue of request timestamps per user.
- On each request: evict timestamps older than the window, then check if count
  exceeds the limit.
- Advantage: no burst at window boundaries (fixed-window weakness).

**Token bucket algorithm** (alternative):
- Users accumulate tokens at a steady rate (e.g., 1 token/6 s = 10/min).
- Each request consumes one token; bucket capacity caps burst size.
- Better when short bursts are acceptable.

**Headers to return:**
```http
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 3
X-RateLimit-Reset: 1748000060
Retry-After: 45
```

---

## PII and Data Privacy

**PII (Personally Identifiable Information) examples:**
- Emails: `\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b`
- US phone: `\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b`
- SSN: `\b\d{3}-\d{2}-\d{4}\b`
- IPv4: `\b(?:25[0-5]|2[0-4]\d|[01]?\d\d?\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b`

**Handling principles:**
- Never log raw PII; replace with typed placeholders (`[EMAIL]`, `[PHONE]`) in logs.
- Use the original (unredacted) value for processing if semantics require it.
- Apply data minimisation: collect only what is needed.
- Store PII encrypted at rest (AES-256 or envelope encryption via KMS).

---

## OWASP Top 10 Relevance for AI Systems

| Risk | AI-specific manifestation | Mitigation |
|---|---|---|
| A01 Broken Access Control | Unauthenticated access to sensitive documents | Auth gate + per-user namespaces |
| A02 Cryptographic Failures | Plaintext API keys in logs or code | Env vars + log sanitisation |
| A03 Injection | Prompt injection via user input | Input validation + injection blocklist |
| A05 Security Misconfiguration | Default credentials, debug mode in production | `AUTH_ENABLED=true`, no debug flags |
| A07 Auth Failures | Timing attacks on credential comparison | `hmac.compare_digest` constant-time comparison |
| A09 Logging Failures | PII in application logs | PII detection + sanitised log copies |
| A10 SSRF | LLM instructed to fetch internal URLs | Validate/blocklist URLs before fetch |
