"""Logic for plugin actions."""

from logging import getLogger
import inspect

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


# TODO: should be chained action...
@side_effect_free
def restricted_package_show(context, data_dict):
    """Add restriction to package_show."""
    log.debug("from restricted_package_show")
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

    # This is a break from the original implementation - if we've been told to ignore the
    #   resources of this package, we don't bother with checking/modifying their representations,
    #   we just outright remove that key from the result
    if not context.get("omit_resources", False):
        restricted_package_metadata["resources"] = _restricted_resource_list_hide_fields(
            context, restricted_package_metadata.get("resources", [])
        )
    else:
        del restricted_package_metadata["resources"]

    return restricted_package_metadata


@side_effect_free
def restricted_resource_search(context, data_dict):
    """Add restriction to resource_search."""
    log.debug("from restricted_resource_search")
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


# TODO: this should be a chained action!
@side_effect_free
@toolkit.chained_action
def restricted_package_search(original_action, context, data_dict):
    """Add restriction to package_search."""
    log.debug(f"from restricted_package_search {inspect.currentframe().f_back.f_code.co_name}")
    package_search_result = original_action(context, data_dict)

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
