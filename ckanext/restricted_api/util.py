"""Helper functions for the plugin."""


import json
import re
from logging import getLogger

import ckan.logic as logic
from ckan.model import User
from ckan.plugins import toolkit

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
    user = User.by_email(email)

    if user:
        log.debug(f"Returning user id ({user.id}) for email {email}.")
        return user

    log.warning(f"No matching users found for email: {email}")
    return None


def is_valid_ip(ip_str):
    """Check if string is a valid IP address.

    Required as sometimes an IP is passed in the user context,
    instead of a user ID (if the user is unauthenticated).
    """
    pattern = r"^(\d{1,3}\.){3}\d{1,3}$"
    if re.match(pattern, ip_str):
        octets = ip_str.split(".")
        if all(0 <= int(octet) <= 255 for octet in octets):
            return True
    return False


def get_user_id_from_context(context, username: bool = False):
    """Get user id or username from context."""
    if (user := context.get("user", "")) != "":
        if is_valid_ip(user):
            log.debug(f"Unauthenticated access attempted from IP: {user}")
        log.debug("User ID extracted from context user key")
        user_id = user
    elif user := context.get("auth_user_obj", None):
        # Handle AnonymousUser in CKAN 2.10
        if user.name == "":
            log.debug("User not present in context")
            return None
        log.debug("User ID extracted from context auth_user_obj key")
        if username:
            user_id = user.name
        else:
            user_id = user.id
    else:
        log.debug("User not present in context")
        return None

    try:
        log.info(f"Getting user details with user_id: {user_id}")
        user = toolkit.get_action("user_show")(
            data_dict={
                "id": user_id,
            },
        )
    except Exception:
        log.warning(f"Could not find a user for ID: {user_id}")

    return user_id


def get_username_from_context(context):
    """Get username from context."""
    return get_user_id_from_context(context, username=True)


def get_user_organisations(user_name) -> dict:
    """Get a dict of a users organizations.

    Returns:
        dict: id:name format
    """
    user_organization_dict = {}

    context = {"user": user_name}
    data_dict = {"permission": "read"}

    for org in logic.get_action("organization_list_for_user")(context, data_dict):
        name = org.get("name", "")
        id = org.get("id", "")
        if name and id:
            user_organization_dict[id] = name

    return user_organization_dict


def get_restricted_dict(resource_dict):
    """Get the resource restriction info.

    The ckan plugin ckanext-scheming changes the structure of the resource
    dict and the nature of how to access our restricted field values.
    """
    restricted_dict = {"level": "public", "allowed_users": ""}

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
    allowed_users = restricted_dict.get("allowed_users", "")

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
            "Resource access restricted to same "
            "organization ({pkg_organization_id}) members"
        ),
    }
