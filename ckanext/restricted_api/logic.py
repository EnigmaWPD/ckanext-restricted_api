"""Logic for plugin actions."""

import json
from logging import getLogger

import ckan.authz as authz
from ckan.common import _
from ckan.logic import (
    NotFound,
    get_or_bust,
    side_effect_free,
)
from ckan.logic.action.get import (
    package_search,
    package_show,
    resource_search,
    resource_view_list,
)
from ckan.plugins import toolkit

from ckanext.resticted_api.util import (
    check_user_resource_access,
    get_restricted_dict,
    get_username_from_context,
)
from ckanext.restricted_api import auth
from ckanext.restricted_api.mailer import send_access_request_email

log = getLogger(__name__)


@side_effect_free
def restricted_resource_view_list(context, data_dict):
    """Add restriction to resource_view_list."""
    model = context["model"]
    id = get_or_bust(data_dict, "id")
    resource = model.Resource.get(id)
    if not resource:
        raise NotFound
    authorized = auth.restricted_resource_show(
        context, {"id": resource.get("id"), "resource": resource}
    ).get("success", False)
    if not authorized:
        return []
    else:
        return resource_view_list(context, data_dict)


@side_effect_free
def restricted_package_show(context, data_dict):
    """Add restriction to package_show."""
    package_metadata = package_show(context, data_dict)

    # Ensure user who can edit can see the resource
    if authz.is_authorized("package_update", context, package_metadata).get(
        "success", False
    ):
        return package_metadata

    # Custom authorization
    if isinstance(package_metadata, dict):
        restricted_package_metadata = dict(package_metadata)
    else:
        restricted_package_metadata = dict(package_metadata.for_json())

    # restricted_package_metadata['resources'] = _restricted_resource_list_url(
    #     context, restricted_package_metadata.get('resources', []))
    restricted_package_metadata["resources"] = _restricted_resource_list_hide_fields(
        context, restricted_package_metadata.get("resources", [])
    )

    return restricted_package_metadata


@side_effect_free
def restricted_resource_search(context, data_dict):
    """Add restriction to resource_search."""
    resource_search_result = resource_search(context, data_dict)

    restricted_resource_search_result = {}

    for key, value in resource_search_result.items():
        if key == "results":
            # restricted_resource_search_result[key] = \
            #     _restricted_resource_list_url(context, value)
            restricted_resource_search_result[
                key
            ] = _restricted_resource_list_hide_fields(context, value)
        else:
            restricted_resource_search_result[key] = value

    return restricted_resource_search_result


@side_effect_free
def restricted_package_search(context, data_dict):
    """Add restriction to package_search."""
    package_search_result = package_search(context, data_dict)

    restricted_package_search_result = {}

    package_show_context = context.copy()
    package_show_context["with_capacity"] = False

    for key, value in package_search_result.items():
        if key == "results":
            restricted_package_search_result_list = []
            for package in value:
                restricted_package_search_result_list.append(
                    restricted_package_show(
                        package_show_context, {"id": package.get("id")}
                    )
                )
            restricted_package_search_result[
                key
            ] = restricted_package_search_result_list
        else:
            restricted_package_search_result[key] = value

    return restricted_package_search_result


@side_effect_free
def restricted_check_access(context, data_dict):
    """Check access for a restricted resource."""
    package_id = data_dict.get("package_id", False)
    resource_id = data_dict.get("resource_id", False)

    user_name = get_username_from_context(context)

    if not package_id:
        raise toolkit.ValidationError("Missing package_id")
    if not resource_id:
        raise toolkit.ValidationError("Missing resource_id")

    log.debug("action.restricted_check_access: user_name = " + str(user_name))

    log.debug("checking package " + str(package_id))
    package_dict = toolkit.get_action("package_show")(
        dict(context, return_type="dict"), {"id": package_id}
    )
    log.debug("checking resource")
    resource_dict = toolkit.get_action("resource_show")(
        dict(context, return_type="dict"), {"id": resource_id}
    )

    return check_user_resource_access(user_name, resource_dict, package_dict)


def _restricted_resource_list_hide_fields(context, resource_list):
    """Hide fields if resource is restricted."""
    restricted_resources_list = []
    for resource in resource_list:
        # copy original resource
        restricted_resource = dict(resource)

        # get the restricted fields
        restricted_dict = get_restricted_dict(restricted_resource)

        # hide fields to unauthorized users
        auth.restricted_resource_show(
            context, {"id": resource.get("id"), "resource": resource}
        ).get("success", False)

        # hide other fields in restricted to everyone but dataset owner(s)
        if not authz.is_authorized(
            "package_update", context, {"id": resource.get("package_id")}
        ).get("success"):
            user_name = get_username_from_context(context)

            # hide partially other allowed user_names (keep own)
            allowed_users = []
            for user in restricted_dict.get("allowed_users"):
                if len(user.strip()) > 0:
                    if user_name == user:
                        allowed_users.append(user_name)
                    else:
                        allowed_users.append(user[0:3] + "*****" + user[-2:])

            new_restricted = json.dumps(
                {
                    "level": restricted_dict.get("level"),
                    "allowed_users": ",".join(allowed_users),
                }
            )
            extras_restricted = resource.get("extras", {}).get("restricted", {})
            if extras_restricted:
                restricted_resource["extras"]["restricted"] = new_restricted

            field_restricted_field = resource.get("restricted", {})
            if field_restricted_field:
                restricted_resource["restricted"] = new_restricted

        restricted_resources_list += [restricted_resource]
    return restricted_resources_list


def restricted_request_access(
    context,  #: Context,
    data_dict,  #: DataDict,
):
    """Send access request email to resource admin/maintainer."""
    log.debug(f"start function restricted_request_access, params: {data_dict}")

    # Check if parameters are present
    if not (resource_id := data_dict.get("resource_id")):
        raise toolkit.ValidationError({"resource_id": "missing resource_id"})

    # Get current user (for authentication only)
    if (user := context.get("user", "")) != "":
        log.debug("User ID extracted from context user key")
        request_user_id = user
    elif user := context.get("auth_user_obj", None):
        log.debug("User ID extracted from context auth_user_obj key")
        request_user_id = user.id
    else:
        return {
            "message": "API token is invalid or missing from Authorization header",
        }

    package_id = data_dict.get("package_id")
    # Get package associated with resource
    try:
        package = toolkit.get_action("package_show")(context, {"id": package_id})
    except toolkit.ObjectNotFound:
        toolkit.abort(404, _("Package not found"))
    except Exception:
        toolkit.abort(404, _("Exception retrieving package to send mail"))

    # Get resource maintainer
    resource_admin = package.get("maintainer").get("email")

    send_access_request_email(resource_id, resource_admin, request_user_id)
