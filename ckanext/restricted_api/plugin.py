"""Init plugin with CKAN interfaces."""

from logging import getLogger

from ckan.plugins import SingletonPlugin, implements, interfaces, toolkit

from ckanext.restricted_api.auth import restricted_resource_show
from ckanext.restricted_api.logic import (
    restricted_check_access,
    restricted_current_package_list,
    restricted_package_search,
    restricted_package_show,
    restricted_request_access,
    restricted_resource_search,
    restricted_resource_view_list,
)
from ckanext.restricted_api.mailer import restricted_notify_access_granted

log = getLogger(__name__)


class RestrictedAPIPlugin(SingletonPlugin):
    """RestrictedPlugin.

    Plugin for restricting datasets via the CKAN API.
    """

    implements(interfaces.IConfigurer)
    implements(interfaces.IActions)
    implements(interfaces.IAuthFunctions)
    implements(interfaces.IResourceController, inherit=True)

    # IConfigurer
    def update_config(self, config):
        """Update CKAN with plugin specific config."""
        toolkit.add_template_directory(config, "templates")

    # IActions
    def get_actions(self):
        """Actions to be accessible via the API."""
        return {
            "resource_view_list": restricted_resource_view_list,
            "package_show": restricted_package_show,
            "current_package_list_with_resources": restricted_current_package_list,
            "resource_search": restricted_resource_search,
            "package_search": restricted_package_search,
            "restricted_check_access": restricted_check_access,
            "restricted_request_access": restricted_request_access,
        }

    # IAuthFunctions
    def get_auth_functions(self):
        """Overrides for default auth checks."""
        return {
            "resource_show": restricted_resource_show,
        }

    # IResourceController
    def before_resource_update(self, context, current, resource):
        """Hook before updating a resource."""
        context["__restricted_previous_value"] = current.get("restricted")

    def after_resource_update(self, context, resource):
        """Hook after updating a resource."""
        previous_value = context.get("__restricted_previous_value")
        restricted_notify_access_granted(previous_value, resource)
