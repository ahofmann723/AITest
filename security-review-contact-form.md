# Security Review — `brandnube.com/#contact` (Contact Form)

**Target:** `https://brandnube.com/#contact`
**Date:** 2026-08-13
**Method:** Passive review of the supplied form HTML and response headers. No active
injection or endpoint probing was performed. Server-side items are marked
**[NEEDS VERIFICATION]** and should only be tested against infrastructure you own/authorize.

---

## Application fingerprint
- **Platform:** WordPress, using the **Contact Form 7** plugin.
- **Plugin version:** **6.1.5** (leaked via `<input name="_wpcf7_version" value="6.1.5">`).
- Form ID `376`, container post `6`. Submission is CF7's standard AJAX flow (REST endpoint
  `/wp-json/contact-form-7/v1/contact-forms/376/feedback`).
- Fields: `your-name`, `your-email`, `your-company`, `phone`, `your-country`, `select-social`.
  No file-upload field.

---

## Findings

### 1. Missing security headers on this host — *Confirmed (Low–Medium)*
Present and good: **`Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`**
(strong — HSTS with preload), and `Server: Apache` with no version / no `X-Powered-By`.

**Absent here (all recommended):**
- **`X-Content-Type-Options: nosniff`** — missing (MIME-sniffing hardening).
- **`X-Frame-Options` / CSP `frame-ancestors`** — missing (no clickjacking protection on the page
  hosting the form).
- **`Content-Security-Policy`** — missing (defence-in-depth against XSS from any theme/plugin).
- **`Referrer-Policy`** — missing.
- **`Permissions-Policy`** — missing (optional).

**Note the inconsistency across your estate:** `myaccount.brandnube.com` *had* `nosniff`,
`X-Frame-Options: SAMEORIGIN`, and `Referrer-Policy` but *no* HSTS, while this host is the reverse
(HSTS preload but none of those three). **Recommendation:** define one security-header baseline and
apply it to every host — at minimum `nosniff`, a frame policy, `Referrer-Policy`, HSTS, and (ideally)
a CSP.

### 2. Plugin/platform version disclosure — *Confirmed (Low / Info)*
`_wpcf7_version = 6.1.5` and the WordPress/CF7 markup fingerprint the exact stack, letting an
attacker match version-specific advisories. This is CF7 default behavior.
**Fix:** primarily, **keep CF7, WordPress core, and all plugins/themes patched** and monitor CF7
security advisories; the hidden version field can optionally be filtered out for defense-in-depth,
but patch currency matters far more.

### 3. Email header injection — *[NEEDS VERIFICATION] (Medium if misconfigured)*
The classic contact-form risk: if the CF7 **Mail** template places raw user input into email
*headers* (e.g. a `Reply-To`, `Cc:`, or `Bcc:` built from `[your-email]`/`[your-name]`), CR/LF in
those fields can inject extra headers and turn the form into a spam relay. CF7 sanitizes newlines
out of header-context fields by default, so a stock config is generally safe.
**Verify:** in wp-admin → Contact → Mail (and "Mail (2)"), confirm no user field is concatenated
into additional headers beyond the standard `Reply-To: [your-email]`, and that the "To" is a fixed
address. **Fix if needed:** hardcode recipients/headers; never build `Cc`/`Bcc` from user input.

### 4. Stored XSS in admin / HTML mail — *[NEEDS VERIFICATION] (Low–Medium)*
`your-name` and `your-company` accept arbitrary text (maxlength 400). If submissions are stored
(e.g. the **Flamingo** plugin) or the notification email is sent as **HTML**, confirm the values are
escaped on output so a payload like `<img src=x onerror=…>` can't fire in the admin dashboard or a
mail client. CF7/Flamingo escape on output by default; confirm no custom HTML mail template echoes
fields raw.
**Fix:** ensure output escaping wherever submissions are rendered; prefer plain-text mail.

### 5. CSRF — *Confirmed design characteristic (Low / Info)*
Contact Form 7 intentionally does **not** use a per-user CSRF token (the form is public and the only
side effect is sending a contact email). Impact of a forged submission is low (an email is sent as
if by the victim). Accept as-is, or add a token via a hardening plugin if your threat model requires
it. Do **not** treat this as high severity for a contact form.

### 6. Anti-automation / rate limiting — *Confirmed present, verify enforcement (Low)*
Good: **reCAPTCHA is properly wired** — `data-sitekey="6LdpBYwsAAAAAGkf80D1NpccRWOCilTVLMJr6dPK"`,
the `_wpcf7_recaptcha_response` field, and a `<noscript>` fallback iframe are all present (score-based
reCAPTCHA v3 integration). *The site key is public by design — exposing it is not a vulnerability.*
**Verify:** the reCAPTCHA **secret** is configured server-side and the score threshold is enforced;
consider additional rate limiting / WAF on the `/wp-json/contact-form-7/.../feedback` endpoint to blunt
low-and-slow spam that passes the score check.

---

## Positive observations
- **HSTS with `includeSubdomains; preload`** — strong transport hardening (stronger than the
  `myaccount.` host, which lacked HSTS entirely).
- **reCAPTCHA v3 correctly integrated** with a `<noscript>` fallback.
- **No file-upload field** — avoids the most severe historical CF7 vulnerability class
  (unrestricted file upload).
- **Server/PHP versions suppressed** at the header level (`Server: Apache`, no `X-Powered-By`).
- Server-side validation types declared (`wpcf7-validates-as-email`, `-as-tel`, `-as-required`);
  CF7 revalidates on the server, not just in the browser.

## Priority order for remediation
1. #1 — add the missing security headers and **standardize one baseline across all hosts**
   (`brandnube.com` and `myaccount.brandnube.com` currently disagree).
2. #3 — verify the Mail template has no header-injection exposure.
3. #2 / #6 — keep CF7 + WordPress + plugins patched; confirm reCAPTCHA secret/threshold + rate limiting.
4. #4 / #5 — confirm admin/mail output escaping; decide on CSRF posture.

## What I could not do here
- The domain is blocked by this environment's network egress, so I reviewed only the pasted HTML and
  headers — no live fetch, no active testing.
- Server-side items (#3, #4, #6 enforcement) require checking the wp-admin CF7 config or authorized
  dynamic testing against your own site.
- No `Set-Cookie` was present on this response (normal for a logged-out WordPress page), so session
  cookie flags weren't assessable here.
- Broader WordPress hardening (wp-login/xmlrpc exposure, REST user enumeration at
  `/wp-json/wp/v2/users`, plugin/theme inventory) is out of scope for this form review but worth a
  separate pass given the platform.
