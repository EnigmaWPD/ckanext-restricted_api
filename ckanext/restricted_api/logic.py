"""Logic for plugin actions."""

from logging import getLogger

from ckan.common import _
from ckan.logic import (
    NotAuthorized,
    NotFound,
    get_or_bust,
    side_effect_free,
)
from ckan.logic.action.get import (
    current_package_list_with_resources,
    package_search,
    package_show,
    resource_search,
    resource_view_list,
)
from ckan.plugins import toolkit

from ckanext.restricted_api.auth import restricted_resource_show
from ckanext.restricted_api.mailer import send_access_request_email
from ckanext.restricted_api.util import (
    check_user_resource_access,
    get_user_id_from_context,
    get_username_from_context,
)

log = getLogger(__name__)


@side_effect_free
def restricted_resource_view_list(context, data_dict):
    """Add restriction to resource_view_list."""
    model = context["model"]
    id = get_or_bust(data_dict, "id")
    resource = model.Resource.get(id)
    if not resource:
        raise NotFound
    authorized = restricted_resource_show(
        context, {"id": resource.get("id"), "resource": resource}
    ).get("success", False)
    if not authorized:
        return []
    else:
        return resource_view_list(context, data_dict)


@side_effect_free
def restricted_current_package_list(context, data_dict):
    """Add restriction to current_package_list_with_resources."""
    current_packages = current_package_list_with_resources(context, data_dict)

    omit_resources = bool(
        toolkit.config.get("ckanext.restricted_api.omit_resources_on_pkg_list", True)
    )

    if omit_resources:
        # Remove 'resources' array from each package
        for package in current_packages:
            package["resources"] = ["redacted"]

    else:
        for package in current_packages:
            package["resources"] = _restricted_resource_list_hide_fields(
                context, package.get("resources", [])
            )

    return current_packages


@side_effect_free
def restricted_package_show(context, data_dict):
    """Add restriction to package_show."""
    try:
        package_metadata = package_show(context, data_dict)
    except NotAuthorized:
        # Skip dataset (user has no access to view)
        return {}

    # Ensure user who can edit can see the resource
    try:
        if toolkit.check_access("package_update", context, package_metadata):
            return package_metadata
    except NotAuthorized:
        # Continue to restriction
        pass

    if isinstance(package_metadata, dict):
        restricted_package_metadata = dict(package_metadata)
    else:
        restricted_package_metadata = dict(package_metadata.for_json())

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

    log.debug(f"action.restricted_check_access: user_name = {str(user_name)}")

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
    """Hide URLs and restricted field info (if restricted resource."""
    restricted_resources_list = []
    for resource in resource_list:
        # Create a shallow copy of the resource dictionary
        restricted_resource = dict(resource)

        # Hide url for unauthorized users
        if not restricted_resource_show(
            context, {"id": resource.get("id"), "resource": resource}
        ).get("success", False):
            restricted_resource["url"] = "redacted"
            restricted_resource["restricted"] = "redacted"

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
    user_id = get_user_id_from_context(context)

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

    send_access_request_email(resource_id, resource_admin, user_id)
