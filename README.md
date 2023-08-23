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

> Requires CKAN >= 2.10. For <2.10, use ckanext-restricted-api==1.0.0

- Restrict the accessibility to the resources of a dataset.
- This way the package metadata is accesible but not the data itself (resource).
- The resource access restriction level can be individualy defined for every package.

Based on work by @espona (Lucia Espona Pernas) for ckanext-restricted (https://github.com/EnviDat/ckanext-restricted).

## Install

```bash
pip install ckanext-restricted-api
```

## Config

Optional variables can be set in your ckan.ini:

- **restricted_api.access_request_template**
  - Description: Path to access request template to render as html email.
  - Default: uses default template.
- **restricted_api.access_granted_template**
  - Description: Path to access granted template to render as html email.
  - Default: uses default template.
- **ckanext.restricted_api.omit_resources_on_pkg_list**
  - Description: on current_package_list_with_resources
    omit resources completely, or process them all to restrict fields (this may not be performant).
  - Default: True (to maximise performance).

## The Restricted Dict

- This plugin works by storing information in the `extra` field of the `resource` table in CKAN.
- By default, CKAN extras values are extracted into the package/resource JSONs returned by the API.
- The key `restricted` is stored, with a value containing a nested dictionary of:

  - level: a string containing the restriction level, with options:
    - `public` any user
    - `registered` only registered users
    - `only_allowed_users` only users specified in the `allowed_users` key.
    - `any_organization` any user that is a member in an organisation.
    - `same_organization` only users of the same organisation the dataset is within.
  - allowed_users: a comma separated string containing specified allowed users,
    to be used with `only_allowed_users`.

Example:

```json
"restricted": '{"level": "same_organization", "allowed_users": ""}'

"only_allowed_users": '{"level": "same_organization", "allowed_users": "user1,user2,user3"}'
```

## Granting Access

1. Users can request access to a dataset by calling an API endpoint from a frontend.
2. The package owner is emailed and can allow individual users to access the resource.
   a. Access can be granted by updating the restricted dict (via the API / frontend).
3. If access is granted, the user will be notified by email automatically.

## Endpoints

**POST**

**GET**

## Notes

Users who do not have restricted access have two fields redacted:

- `url`: to download the dataset
- `restricted`: to see the restriction information

Downloading of the restricted resource is also not possible via the CKAN API.

However, it should be noted, if resources are hosted in public S3 storage, then this obfuscation does not prevent direct download of the data.
