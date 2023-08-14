"""Helper functions for the plugin."""


import json
from logging import getLogger

import ckan.logic as logic
from ckan.model import User

log = getLogger(__name__)


def get_user_from_email(email: str):
    """Get the CKAN user with the given email address.

    Returns:
        dict: A CKAN user dict.
    """
    # make case insensitive
    email = email.lower()
    log.debug(f"Getting user id for email: {email}")

    # Workaround as action user_list requires sysadmin priviledge
    # to return emails (email_hash is returned otherwise, with no matches)
    # action user_show also doesn't return the reset_key...
    # by_email returns .first() item
    users = User.by_email(email)

    if users:
        # as_dict() method on CKAN User object
        user = users[0]
        log.debug(f"Returning user id ({user.id}) for email {email}.")
        return user

    log.warning(f"No matching users found for email: {email}")
    return None


def get_username_from_context(context):
    """Get username or user id from context."""
    if (user := context.get("user", "")) != "":
        log.debug("User ID extracted from context user key")
        # User ID
        user_name = user
    elif user := context.get("auth_user_obj", None):
        log.debug("User ID extracted from context auth_user_obj key")
        # User Name
        user_name = user.name

    return user_name


def get_restricted_dict(resource_dict):
    """Get the resource restriction info."""
    restricted_dict = {"level": "public", "allowed_users": []}

    # the ckan plugins ckanext-scheming and ckanext-composite
    # change the structure of the resource dict and the nature of how
    # to access our restricted field values
    if resource_dict:
        # the dict might exist as a child inside the extras dict
        extras = resource_dict.get("extras", {})
        # or the dict might exist as a direct descendant of the resource dict
        restricted = resource_dict.get("restricted", extras.get("restricted", {}))
        if not isinstance(restricted, dict):
            # if the restricted property does exist, but not as a dict,
            # we may need to parse it as a JSON string to gain access to the values.
            # as is the case when making composite fields
            try:
                restricted = json.loads(restricted)
            except ValueError:
                restricted = {}

        if restricted:
            restricted_level = restricted.get("level", "public")
            allowed_users = restricted.get("allowed_users", "")
            if not isinstance(allowed_users, list):
                allowed_users = allowed_users.split(",")
            restricted_dict = {
                "level": restricted_level,
                "allowed_users": allowed_users,
            }

    return restricted_dict


def check_user_resource_access(user, resource_dict, package_dict):
    """Chec if user has access to restricted resource."""
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
