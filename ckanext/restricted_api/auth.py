"""Overrides for default auth checks."""

from logging import getLogger

import ckan.logic.auth as logic_auth
import ckan.plugins.toolkit as toolkit
import inspect

from ckanext.restricted_api.util import (
    get_restricted_dict,
    get_user_organisations,
    get_username_from_context,
    get_restricted_logic_package_dict,
    HAS_PRE_EVALUATED_RESTRICTED_RESOURCE_DICT
)

log = getLogger(__name__)


def check_pre_evaluated_resource_show(context, resource):
    # TODO: NM: don't like the tenuous link in looking for the `restricted` key on the dict...
    if context.get(HAS_PRE_EVALUATED_RESTRICTED_RESOURCE_DICT, False) and isinstance(resource, dict):
        log.debug("was already evaluated")
        return {"success": resource.get("restricted", False) == "redacted"}


@toolkit.auth_allow_anonymous_access
def restricted_resource_show(context, data_dict=None):
    """Ensure user who can edit the package can see the resource."""
    log.debug(f"start function restricted_resource_show from {inspect.currentframe().f_back.f_code.co_name}")

    resource = data_dict.get("resource", context.get("resource", {}))

    # If our context indicated that we've actually already run this restricted_resource_show check on the given
    #   resource prior to this call, (within `restricted_package_show` or `restricted_resource_search`), we can just
    #   use that previous result.
    if result := check_pre_evaluated_resource_show(context, resource):
        return result

    if not resource:
        resource = logic_auth.get_resource_object(context, data_dict)
    if type(resource) is not dict:
        resource = resource.as_dict()

    # Get username from context
    user_name = get_username_from_context(context)
    # NM: More appropriate place for the package is the `context` not the `data_dict`
    pkg_dict = get_restricted_logic_package_dict(context)

    if not pkg_dict:
        log.debug('get package')
        model = context["model"]
        package = model.Package.get(resource.get("package_id"))
        pkg_dict = get_restricted_logic_package_dict(context, package)

    return _restricted_check_user_resource_access(user_name, resource, pkg_dict)


def _restricted_check_user_resource_access(user_name, resource_dict, restricted_logic_package_dict):
    """Check resource access using restricted info dict."""
    restricted_dict = get_restricted_dict(resource_dict)

    restricted_level = restricted_dict.get("level", "public")
    allowed_users = restricted_dict.get("allowed_users", [])

    # Public resources (DEFAULT)
    if not restricted_level or restricted_level == "public":
        return {"success": True}

    # Registered users only
    if not user_name:
        log.info(
            "Unauthenticated user attempted to access restricted resource ID: "
            f"{resource_dict.get('id')}"
        )
        return {
            "success": False,
            "msg": "Resource access restricted to registered users",
        }
    if restricted_level == "registered":
        return {"success": True}

    # Since we have a user, check if it is in the allowed list
    if user_name in allowed_users:
        return {"success": True}
    elif restricted_level == "only_allowed_users":
        log.debug(
            f"{user_name} attempted and failed to access restricted "
            f"resource ID: {resource_dict.get('id')}"
        )
        return {
            "success": False,
            "msg": "Resource access restricted to allowed users only",
        }

    # Get organization list
    user_organization_dict = get_user_organisations(user_name)

    # Any Organization Members (Trusted Users)
    if not user_organization_dict:
        return {
            "success": False,
            "msg": "Resource access restricted to members of an organization",
        }
    if restricted_level == "any_organization":
        return {"success": True}

    # Same Organization Members
    pkg_organization_id = restricted_logic_package_dict.get("owner_org", "")
    if restricted_level == "same_organization":
        if pkg_organization_id in user_organization_dict.keys():
            return {"success": True}

    return {
        "success": False,
        "msg": (
            "Resource access restricted to same "
            f"organization ({pkg_organization_id}) members"
        ),
    }
