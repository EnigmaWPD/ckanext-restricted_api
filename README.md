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

- Restrict the accessibility to the resources of a dataset.
- This way the package metadata is accesible but not the data itself (resource).
- The resource access restriction level can be individualy defined for every package.

Based on work by @espona (Lucia Espona Pernas) for ckanext-restricted (https://github.com/EnviDat/ckanext-restricted).

**Granting Access**

1. Users can request access to a dataset by calling an API endpoint from a frontend.
2. The package owner is emailed and can allow individual users to access the resource.
3. If access is granted, the user will be notified by email.

## Install

```bash
pip install ckanext-restricted-api
```

## Config

Optional variables can be set in your ckan.ini:

TBC

- **restricted_api.access_request_template**
  - Description: Path to access request template to render as html email.
  - Default: uses default template.
- **restricted_api.access_granted_template**
  - Description: Path to access granted template to render as html email.
  - Default: uses default template.

## Endpoints

TBC

**POST**

**GET**

## Notes

All information inside the restricted fields (except 'level') is hidden for users other than the ones who can edit the dataset.

We used this to keep a shared-secret key field for accessing remotely hosted resources (https://github.com/EnviDat/ckanext-envidat_theme/blob/4265ecfe90e10eb1f095e8e8d19fe43554ab6799/ckanext/envidat_theme/helpers.py#L28).

The allowed usernames are hidden partially to the non-editors, in our case was critical because they were very similar to the user emails.
