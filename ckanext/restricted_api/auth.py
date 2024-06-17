"""Overrides for default auth checks."""

from logging import getLogger

import ckan.logic.auth as logic_auth
import ckan.plugins.toolkit as toolkit
import inspect

from ckanext.restricted_api.util import (
    check_user_resource_access,
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

    return check_user_resource_access(user_name, resource, pkg_dict)

