"""Helper functions for the plugin."""


import json
import re
import ipaddress
from logging import getLogger

import ckan.logic as logic
import ckan.model as model
from ckan.model import User
from ckan.plugins import toolkit
import ckan.plugins as p
from ckan.lib import app_globals

log = getLogger(__name__)


RESTRICTED_LOGIC_PACKAGE_DICT_KEY = "restricted_logic_package_dict"
RESTRICTED_API_EXTRACTED_USER_OBJ_FROM_CONTEXT_KEY = "restricted_api_extracted_user_obj_from_context"
HAS_PRE_EVALUATED_RESTRICTED_RESOURCE_DICT = "has_pre_evaluated_restricted_resource_show"


def get_all_view_plugins():
    '''
    NM: Returns all enabled resource view plugins
    '''
    return p.PluginImplementations(p.IResourceView)


def get_all_view_plugin_names():
    '''
    NM
    :return:
    '''
    return [plugin.info().get('name') for plugin in get_all_view_plugins()]


def package_to_restricted_logic_dict(package):
    '''
    NM: model.Package.as_dict() is good and everything, but it always evaluates the resources of the package. This can
    be super-duper wasteful if we're not interested in that bit of it, which we're not going to be for the actions
    defined in this extension.

    :param package:
    :return:
    '''
    if isinstance(package, model.Package):
        # this will actually contain more than we really need, but won't try and fetch any relationships.
        #   we're really only interested in the `id` and `owner_org`
        return model.domain_object.DomainObject.as_dict(package)

    return package


def get_restricted_logic_package_dict(context, package_if_not_in_context=None):
    '''
    NM
    :param context:
    :param package_if_not_in_context:
    :return:
    '''
    if (not context.get(RESTRICTED_LOGIC_PACKAGE_DICT_KEY, None)) and \
            (pkg := context.get("package", package_if_not_in_context)):
        context[RESTRICTED_LOGIC_PACKAGE_DICT_KEY] = package_to_restricted_logic_dict(pkg)

    return context.get(RESTRICTED_LOGIC_PACKAGE_DICT_KEY, {})


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


def is_valid_ip(ip_str):
    """Check if string is a valid IP address.

    Required as sometimes an IP is passed in the user context,
    instead of a user ID (if the user is unauthenticated).
    """
    # NM: the original implementation did not account for ipv6 addresses
    try:
        ipaddress.ip_address(ip_str)
        return True
    except ValueError:
        return False


def get_user_id_from_context(context, username: bool = False, save_to_context=True):
    """Get user id or username from context."""
    # NM: rewrote this somewhat

    # we've been here before, regurgitate our last extracted user
    if save_to_context and RESTRICTED_API_EXTRACTED_USER_OBJ_FROM_CONTEXT_KEY in context:
        if isinstance(context[RESTRICTED_API_EXTRACTED_USER_OBJ_FROM_CONTEXT_KEY], User):
            if username:
                return context[RESTRICTED_API_EXTRACTED_USER_OBJ_FROM_CONTEXT_KEY].name
            else:
                return context[RESTRICTED_API_EXTRACTED_USER_OBJ_FROM_CONTEXT_KEY].id

        # if context[RESTRICTED_API_EXTRACTED_USER_OBJ_FROM_CONTEXT_KEY] is not a user, then it was an anonymous
        #   user/IP address (str) or an undefined user (None)
        return context[RESTRICTED_API_EXTRACTED_USER_OBJ_FROM_CONTEXT_KEY]

    # otherwise continue as normal
    if (user := context.get("user", "")) != "":
        if is_valid_ip(user):
            log.debug(f"Context has IP: {user}")
            # NM: this should quit early rather than falling through - we know there is no CKAN user we can extract
            #   from this!
            if save_to_context:
                context[RESTRICTED_API_EXTRACTED_USER_OBJ_FROM_CONTEXT_KEY] = user
            return user

        log.debug("User ID extracted from context user key")
        # FYI, the `user` value in the context can either be a username or a user id, which is why the following
        #   below if/else is needed to make sure we're returning exactly the value we want
        user_id = user

        # try checking to see if the current request userobj can be used to pick out the id/name
        if toolkit.g and toolkit.g.userobj and (toolkit.g.userobj.name == user_id or toolkit.g.userobj.id == user_id):
            log.debug("Using toolkit.g.userobj")
            if username:
                user_id = toolkit.g.userobj.name
            else:
                user_id = toolkit.g.userobj.id
            if save_to_context:
                context[RESTRICTED_API_EXTRACTED_USER_OBJ_FROM_CONTEXT_KEY] = toolkit.g.userobj

        # otherwise we've gotta ask the DB
        else:
            log.debug("Getting user from DB")
            # we are forgoing a call to `user_show` as calling it doesn't really tell us anything helpful - deleted
            #   users are still returned by it, and it would realistically only throw an exception if the user did not
            #   exist in the database (ObjectNotFound), or if the caller did not have permissions to query `user_show`,
            #   which is not the job of a utility function to determine (and by CKAN default, everyone has permission
            #   for this anyway)
            user = User.get(user_id)

            if save_to_context:
                context[RESTRICTED_API_EXTRACTED_USER_OBJ_FROM_CONTEXT_KEY] = user if user else user_id

            if user:
                if username:
                    user_id = user.name
                else:
                    user_id = user.id
            # else user_id remains as whatever it was

    elif user := context.get("auth_user_obj", None):
        log.debug("User ID extracted from context auth_user_obj key")
        if username:
            user_id = user.name
        else:
            user_id = user.id

        if save_to_context:
            context[RESTRICTED_API_EXTRACTED_USER_OBJ_FROM_CONTEXT_KEY] = user
    else:
        log.debug("User not present in context")
        if save_to_context:
            context[RESTRICTED_API_EXTRACTED_USER_OBJ_FROM_CONTEXT_KEY] = None
        return None

    return user_id


def get_username_from_context(context, save_to_context=True):
    """Get username from context."""
    return get_user_id_from_context(context, username=True, save_to_context=save_to_context)


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
    ckanext_scheming_exists = 'ckanext-scheming' in app_globals.get_globals_key("ckan.plugins")
    if ckanext_scheming_exists:
        restricted_dict = {"level": "public", "allowed_users": []}

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
                allowed_users = restricted.get("allowed_users", [])
                if not isinstance(allowed_users, list):
                    allowed_users = allowed_users.split(",")
                restricted_dict = {
                    "level": restricted_level,
                    "allowed_users": allowed_users,
                }

        return restricted_dict

    # @see https://github.com/olivierdalang/ckanext-restricted/commit/89693f5e4a2a4dedf2cada289d1bf46bd7991069
    restricted_level = resource_dict.get('restricted_level', 'public')
    allowed_users = resource_dict.get('restricted_allowed_users', '')
    if not isinstance(allowed_users, list):
        allowed_users = allowed_users.split(',')
    return {
        'level': restricted_level,
        'allowed_users': allowed_users}


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
            "Resource access restricted to same "
            "organization ({pkg_organization_id}) members"
        ),
    }
