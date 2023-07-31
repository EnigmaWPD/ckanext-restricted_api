# CKAN Restricted API

<div align="center">
  <em>Extension to allow dataset restriction via CKAN API.</em>
</div>
<div align="center">
  <a href="https://pypi.org/project/ckanext-restricted_api" target="_blank">
      <img src="https://img.shields.io/pypi/v/ckanext-restricted_api?color=%2334D058&label=pypi%20package" alt="Package version">
  </a>
  <a href="https://pypistats.org/packages/ckanext-restricted_api" target="_blank">
      <img src="https://img.shields.io/pypi/dm/ckanext-restricted_api.svg" alt="Downloads">
  </a>
  <a href="https://gitlabext.wsl.ch/EnviDat/ckanext-restricted_api/-/raw/main/LICENSE" target="_blank">
      <img src="https://img.shields.io/github/license/EnviDat/ckanext-restricted_api.svg" alt="Licence">
  </a>
</div>

---

**Documentation**: <a href="https://envidat.gitlab-pages.wsl.ch/ckanext-restricted_api/" target="_blank">https://envidat.gitlab-pages.wsl.ch/ckanext-restricted_api/</a>

**Source Code**: <a href="https://gitlabext.wsl.ch/EnviDat/ckanext-restricted_api" target="_blank">https://gitlabext.wsl.ch/EnviDat/ckanext-restricted_api</a>

---

**This plugin is primarily intended for custom frontends built on the CKAN API.**

By using API tokens from CKAN core (>2.9), this plugin provides an authentication flow where:

1. Users receive a login token via email (via reset key in core).
2. API token is returned on valid login token (reset key) submission.
3. The API token should then be included in Authorization headers from the frontend --> CKAN calls.

Based on work by @espona (Lucia Espona Pernas) for ckanext-restricted (https://github.com/EnviDat/ckanext-restricted).

A second login flow is also supported, using Azure AD:

1. User logs in with authorization code flow in frontend (@azure/msal-browser or similar).
2. Azure token is passed to azure specific endpoint.
3. Token is validated and API token for CKAN is returned.
4. The API token should then be included in Authorization headers from the frontend --> CKAN calls.

## Install

```bash
pip install ckanext-restricted-api
```

## Config

Optional variables can be set in your ckan.ini:

- **restricted_api.guidelines_url**
  - Description: A link to your website guidelines.
  - Default: None, not included.
- **restricted_api.policies_url**
  - Description: A link to your website policies.
  - Default: None, not included.
- **restricted_api.welcome_template**
  - Description: Path to welcome template to render as html email.
  - Default: uses default template.
- **restricted_api.reset_key_template**
  - Description: Path to reset key template to render as html email
  - Default: uses default template.
- **restricted_api.cookie_name**
  - Description: Set to place the API token in a cookie, with given name.
    The cookie will default to `secure`, `httpOnly`, `samesite: Lax`.
  - Default: None, no cookie used.
- **restricted_api.cookie_domain**
  - Description: The domain for samesite to respect, required if cookie set.
  - Default: None.
- **restricted_api.cookie_samesite**
  - Description: To change the cookie samesite value to `Strict`.
    Only enable this if you know what you are doing.
  - Default: None, samesite value is set to `Lax`.
- **restricted_api.cookie_http_only**
  - Description: Use a httpOnly cookie, recommended.
  - Default: true.
- **restricted_api.cookie_path**
  - Description: Set a specific path to use the cookie, e.g. `/api`.
  - Default: `/` (all paths).
- **restricted_api.anonymous_usernames**
  - Description: Set to true to anonymise usernames when generated.
  - Default: false.
- **restricted_api.anonymous_domain_exceptions**
  - Description: Email domain exceptions that should not be anonymised, if enabled.
  - Default: None.

## Endpoints

TBC

**POST**

**GET**

## Using the cookie in an Authorization header

If configured, the cookie containing an API token can't do much on it's own.

It is possible to extract the cookie value using frontend JS and pass to the CKAN backend, but this makes your site vulnerable to XSS attacks.

Instead the cookie should be stored in a secure way:

- `samesite=Lax` with `domain=YOUR_DOMAIN` to help prevent CSRF.
  - `samesite=Strict` is even more secure, but significantly impacts UX for your site.
- `secure` to help prevent man-in-the-middle.
- `httpOnly` to help prevent XSS.
  - Setting this means the cookie can no longer be accessed from your JS code.

Then a middleware must be used to convert the cookie value into a header than CKAN can interpret:

**NGINX server example**
(nginx is the default/recommended server to reverse proxy CKAN)
(https://docs.ckan.org/en/latest/maintaining/installing/deployment.html)

```nginx
# Add the cookie-based API token to the request Authorization header
# This is passed to the CKAN backend & read automatically by CKAN
proxy_set_header 'Authorization' $cookie_${AUTH_COOKIE_NAME};

# If using caching omit the cookie
proxy_cache_bypass $cookie_${AUTH_COOKIE_NAME};
proxy_no_cache $cookie_${AUTH_COOKIE_NAME};
```

**Apache server example**

```apache
SetEnvIf Cookie "(^|;\ *)${AUTH_COOKIE_NAME}=([^;\ ]+)" ckan_cookie_value=$2
RequestHeader set Authorization "%{ckan_cookie_value}e"
```

## Notes

- It is also recommended to disable access to the API via cookie, to help prevent CSRF:
  `ckan.auth.disable_cookie_auth_in_api = true`
- The configuration for API tokens can be configured in core:

```ini
api_token.nbytes = 60
api_token.jwt.decode.secret = string:YOUR_SUPER_SECRET_STRING
api_token.jwt.algorithm = HS256

# expire_api_token plugin (unit = 1 day in seconds, lifetime = 3 days)
expire_api_token.default_lifetime = 3
expire_api_token.default_unit = 86400
```
