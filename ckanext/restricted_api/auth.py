"""Overrides for default auth checks."""

from logging import getLogger

import ckan.logic as logic
import ckan.logic.auth as logic_auth
import ckan.plugins.toolkit as toolkit

from ckanext.restricted_api.util import get_restricted_dict

log = getLogger(__name__)


@toolkit.auth_allow_anonymous_access
def restricted_resource_show(context, data_dict=None):
    """Ensure user who can edit the package can see the resource."""
    log.debug("start function restricted_resource_show")

    resource = data_dict.get("resource", context.get("resource", {}))
    if not resource:
        resource = logic_auth.get_resource_object(context, data_dict)
    if type(resource) is not dict:
        resource = resource.as_dict()

    if (user := context.get("user", "")) != "":
        log.debug("User ID extracted from context user key")
        user_id = user
    elif user := context.get("auth_user_obj", None):
        log.debug("User ID extracted from context auth_user_obj key")
        user_id = user.id
    else:
        return {
            "message": "API token is invalid or missing from Authorization header",
        }

    try:
        log.info(f"Getting user details with user_id: {user_id}")
        user = toolkit.get_action("user_show")(
            data_dict={
                "id": user_id,
            },
        )
        # Get user_name
        user_name = user.name

    except Exception as e:
        log.error(str(e))
        log.warning(f"Could not find a user for ID: {user_id}")
        return {"message": f"could not find a user for id: {user_id}"}

    package = data_dict.get("package", {})
    if not package:
        model = context["model"]
        package = model.Package.get(resource.get("package_id"))
        package = package.as_dict()

    return _restricted_check_user_resource_access(user_name, resource, package)


def _restricted_check_user_resource_access(user, resource_dict, package_dict):
    """Check resource access using restricted info dict."""
    restricted_dict = get_restricted_dict(resource_dict)

    restricted_level = restricted_dict.get("level", "public")
    allowed_users = restricted_dict.get("allowed_users", [])

    # Public resources (DEFAULT)
    if not restricted_level or restricted_level == "public":
        return {"success": True}

    # Registered user
    if not user:
        return {
            "success": False,
            "msg": "Resource access restricted to registered users",
        }
    else:
        if restricted_level == "registered" or not restricted_level:
            return {"success": True}

    # Since we have a user, check if it is in the allowed list
    if user in allowed_users:
        return {"success": True}
    elif restricted_level == "only_allowed_users":
        return {
            "success": False,
            "msg": "Resource access restricted to allowed users only",
        }

    # Get organization list
    user_organization_dict = {}

    context = {"user": user}
    data_dict = {"permission": "read"}

    for org in logic.get_action("organization_list_for_user")(context, data_dict):
        name = org.get("name", "")
        id = org.get("id", "")
        if name and id:
            user_organization_dict[id] = name

    # Any Organization Members (Trusted Users)
    if not user_organization_dict:
        return {
            "success": False,
            "msg": "Resource access restricted to members of an organization",
        }

    if restricted_level == "any_organization":
        return {"success": True}

    pkg_organization_id = package_dict.get("owner_org", "")

    # Same Organization Members
    if restricted_level == "same_organization":
        if pkg_organization_id in user_organization_dict.keys():
            return {"success": True}

    return {
        "success": False,
        "msg": (
            "Resource access restricted to same " "organization ({}) members"
        ).format(pkg_organization_id),
    }
