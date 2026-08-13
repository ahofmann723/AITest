# Security Review — `myaccount.brandnube.com/register.php`

**Target:** `https://myaccount.brandnube.com/register.php?plan=BASIC&productref=BASIC&package=BASIC&service=3`
**Date:** 2026-08-13
**Method:** Passive review of the returned HTML/JS only. No active injection, fuzzing, or
authenticated testing was performed. Items needing dynamic testing are marked
**[NEEDS VERIFICATION]** and should only be tested against infrastructure you own or are
authorized to test.

---

## Application fingerprint

- **Platform:** Dolibarr ERP/CRM with the **SellYourSaaS** module (SaaS instance provisioning).
  - Evidence: `<meta name="author" content="Dolibarr Development Team">`, `mainmyaccount.inc.php`,
    `dol_loginsellyoursaas`, `register_instance.php`, `source/theme/eldy/…`, "Installing your instance…".
- **Exact version:** **22.0.3** — leaked on every asset via `?version=22.0.3`.
- Form posts (`POST`) to `register_instance.php`. Each submission provisions a real hosted
  instance, so the form is a resource-creating action, not just a data write.

---

## Findings

### 1. Internal session variable leaked in HTML comment — *Confirmed (Low/Medium)*
```html
<!-- _SESSION['dol_loginsellyoursaas'] = 235 -->
```
A server-side session value and an internal user/login ID (`235`) are printed into the page
as a debug comment. This exposes internal identifiers and confirms the session key name to
anyone viewing source. It's a leftover debug artifact that should not ship to production.
**Fix:** remove the debug comment from the template/output path.

### 2. Exact framework + version disclosure — *Confirmed (Low / Info)*
`?version=22.0.3` on every CSS/JS reveals the precise Dolibarr build, letting an attacker map
directly to version-specific CVEs. The `<meta name="author">`, path names, and the SellYourSaaS
markers compound this.
**Fix:** strip or genericize the version query string on public pages; avoid advertising the
author/stack in meta. (Defense-in-depth — keeping the install patched matters more.)

### 3. URL parameters reflected into HTML — *[NEEDS VERIFICATION] (potential reflected XSS, Medium–High)*
The URL params are echoed into the page. The commented block at the bottom mirrors the **raw**
query values:
```html
<!--
    <input type="hidden" name="package"    value="BASIC" />
    <input type="hidden" name="service"    value="3" />
    <input type="hidden" name="productref" value="BASIC" />
-->
```
and the active hidden `service` field reflects `value="3"` straight from `service=3`. Because
`BASIC`/`3` contain no special characters, I can't tell from source alone whether the reflection
is properly HTML/attribute-escaped. If it isn't, a payload in `service`, `package`, `productref`,
or `plan` (e.g. breaking out of the `value="…"` attribute, or terminating the `-->` comment)
could yield **reflected XSS**.
**Verify:** request the page with a benign marker in each param (e.g.
`service=3"x=y` and `package=z--><b>t</b>`) and inspect whether it lands unescaped in the
response. **Fix:** HTML-entity-encode every reflected parameter; whitelist `service` to an
integer and `package/productref/plan` to a known set.

### 4. Tamperable internal-ID hidden fields → parameter tampering / IDOR — *[NEEDS VERIFICATION] (Medium–High)*
The form ships several empty-but-user-controllable hidden fields that are internal keys posted
to `register_instance.php`:
```
socid, fromsocid, reusesocid, reusecontractid, partner, partnerkey, forcesubdomain, disablecustomeremail
```
`socid` (company/third-party ID), `reusesocid`, `reusecontractid`, and `fromsocid` are database
identifiers. If the backend trusts them without an ownership/authorization check, an attacker
could associate a new instance with **another customer's** company or contract, reuse another
tenant's records, suppress customer notification email (`disablecustomeremail=1`), or force a
chosen subdomain. This is a classic SaaS multi-tenant IDOR surface.
**Verify (authorized only):** submit with crafted `socid`/`reusesocid`/`reusecontractid` values
and confirm the server rejects IDs the session doesn't own. **Fix:** never trust these from the
client; derive them server-side from the authenticated/session context, or validate ownership.

### 5. User-controllable resource path in `extcss` — *[NEEDS VERIFICATION] (Medium)*
```html
<input type="hidden" name="extcss" value="dist/css/myaccount.css" />
```
A file path is posted from the client. If `register_instance.php` (or a follow-up page) uses this
value to include/emit a stylesheet reference without validation, it becomes a path-injection /
resource-injection vector (arbitrary path, traversal, or reflected reference).
**Fix:** ignore client-supplied `extcss`; select the theme CSS server-side from an allowlist.

### 6. CKEditor 4 + PHP file-manager connector exposed on a public page — *[NEEDS VERIFICATION] (Medium–High)*
The unauthenticated registration page loads the full (end-of-life) **CKEditor 4** and wires its
PHP file browser/upload connectors:
```js
var ckeditorFilebrowserBrowseUrl =
  'source/core/filemanagerdol/browser/default/browser.php?Connector=source/core/filemanagerdol/connectors/php/connector.php';
```
CKEditor 4 is out of support and has known XSS issues, and CKFinder/CKEditor PHP connectors have
historically enabled arbitrary file upload/traversal when reachable unauthenticated. There is no
reason a signup page needs a rich-text editor or file manager.
**Verify:** check whether `…/connector.php` and `…/browser.php` are reachable without auth.
**Fix:** don't load CKEditor/the file manager on the public registration page; ensure those
endpoints require authentication and are not internet-exposed.

### 7. Image/file-serving endpoint `viewimage.php` — *[NEEDS VERIFICATION] (Medium)*
```
source/viewimage.php?cache=1&modulepart=mycompany&file=logos%2Fthumbs%2F…
```
Dolibarr's `viewimage.php`/`document.php` (`modulepart` + `file` params) have had directory-
traversal / arbitrary-file-read CVEs. Worth confirming this build enforces the path restrictions
for the `file`/`modulepart` parameters.
**Fix:** keep patched; validate `modulepart` against an allowlist and canonicalize/anchor `file`.

### 8. Anti-automation appears incomplete — *[NEEDS VERIFICATION] (Medium)*
The submit button carries `class="g-recaptcha"` and there's an `onSubmitCallBackForReCaptcha`
handler, but the page includes **no reCAPTCHA `api.js` and no `data-sitekey`/`data-callback`**,
and the comment says "if option enabled." If reCAPTCHA is effectively off, this form — which
provisions real instances/servers per submit — can be driven by automated mass-signups, causing
resource exhaustion, cost, and junk-tenant abuse.
**Fix:** enforce a working CAPTCHA and server-side rate limiting on `register_instance.php`.

### 9. Client-side-only validation — *Confirmed pattern (Low)*
Password policy (`pattern`, `minlength=8`), domain constraints (`applyDomainConstraints`), and
required fields are enforced only in the browser. These are UX helpers and are trivially bypassed
by posting directly.
**Fix:** re-validate password strength, field lengths, domain format, and required fields
server-side (assume this is already the case in Dolibarr, but confirm).

### 10. Response headers — *Confirmed (mixed)*
Reviewed from the actual response headers.

**Present / good:**
| Header | Value |
| --- | --- |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `SAMEORIGIN` (clickjacking) |
| `Referrer-Policy` | `same-origin` |
| `Cache-Control` | `no-store, no-cache, must-revalidate` (+ `Pragma`, `Expires`) — good for a form page |
| `Server` | `Apache` — version suppressed at the server-header level (good; note the app still leaks 22.0.3 via #2) |

**Missing / to fix:**
- **`Content-Security-Policy` — absent (Medium).** This is the single most important gap here: a CSP
  is the mitigating control for finding #3 (reflected parameters). Even a modest policy
  (`default-src 'self'`, scripted `script-src` without `'unsafe-inline'` where feasible,
  `frame-ancestors 'self'`, `object-src 'none'`, `base-uri 'self'`) would sharply reduce XSS impact.
  Note the page uses inline `<script>` and inline event patterns, so a strict `script-src` will need
  nonces/hashes — plan for that.
- **`Strict-Transport-Security` — absent (Low–Medium).** No HSTS means no protection against
  SSL-strip / protocol-downgrade. Add e.g. `Strict-Transport-Security: max-age=31536000; includeSubDomains`
  (consider `preload` once you're confident all subdomains are HTTPS — relevant since instances are
  provisioned as `*.brandnube.com`).
- **`Permissions-Policy` — absent (Low).** Optional hardening; lock down features you don't use
  (`camera=(), microphone=(), geolocation=()`, etc.).

**Cookie flags — still unconfirmed.** This particular response contained **no `Set-Cookie`** header
(the session cookie was likely already set on an earlier request). I therefore still can't verify
`Secure` / `HttpOnly` / `SameSite` on the Dolibarr session cookie (`DOLSESSID…`). Capture the headers
of the first/session-establishing request (fresh browser, no cookies) and confirm the session cookie
is `Secure; HttpOnly; SameSite=Lax` (or `Strict`).

---

## Positive observations
- CSRF protection is present: an `anti-csrf-token` meta and a matching `token` hidden field are
  emitted, and the form uses `POST` (not `GET`).
- Good baseline response headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`,
  `Referrer-Policy: same-origin`, strong `Cache-Control`/`Pragma` no-store, and a version-suppressed
  `Server: Apache` banner.
- The password field sets `autocomplete="new-password"`, `spellcheck="false"`, `autocapitalize="off"`.
- Country/TLD `select2` rendering references `dol_escape_htmltag(...)` sanitization for `data-html`;
  those option sets are server-controlled (country list, Basic/Premium tiers), not user input, so the
  `escapeMarkup: return markup` (escaping disabled) usage is low-risk **as long as** no user-controlled
  data ever populates a `data-html` attribute.

## Priority order for remediation
1. #4 (IDOR / tamperable IDs) and #6 (public file-manager/CKEditor) — highest potential impact.
2. #3 (reflected XSS) — verify and fix encoding; **add a CSP (#10)**, the main missing mitigation.
3. #8 (anti-automation), #5 (`extcss`), #7 (`viewimage.php`), **add HSTS (#10)**.
4. #1, #2, #9 — hardening / info-leak cleanup.

## What I could not do here
- No dynamic/active testing (injection, IDOR probing, endpoint reachability) was performed — those
  require authorized testing against your own infrastructure.
- Response headers were reviewed (#10). Still outstanding: **session cookie flags** — this response
  had no `Set-Cookie`; capture the session-establishing request to confirm `Secure/HttpOnly/SameSite`.
- No TLS/cipher/certificate review was performed.
