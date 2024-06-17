"""Logic for plugin actions."""

from logging import getLogger

import inspect
import ckan.authz as authz
from ckan.common import _, request
from ckan.logic import (
    NotFound,
    side_effect_free,
)
from ckan.logic.action.get import (
    resource_search,
)
from ckan.plugins import toolkit
import ckan.model as model
from ckanext.restricted_api.auth import restricted_resource_show
from ckanext.restricted_api.mailer import send_access_request_email
from ckanext.restricted_api.util import (
    get_user_id_from_context,
    get_username_from_context,
    get_restricted_logic_package_dict,
    package_to_restricted_logic_dict,
    get_all_view_plugin_names
)
import ckan.lib.dictization.model_dictize as model_dictize

log = getLogger(__name__)

# we don't need to include dashboard.datasets or user.read, as the "package_update" check in restricted_package_show
#   will skip over the redaction of resources anyway
LITE_RESOURCES_FOR_ENDPOINTS = [
    'dataset.search',       # i.e. the /dataset/ list page
    'group.read',           # the /group/<group_id> page which lists that group's datasets
    'organization.read',    # the /organization/<organization_id> page which lists that organization's datasets
]


@toolkit.side_effect_free
# TODO: NM: Really, this shouldn't be needed. the check_access on resource_view_list is just a passthrough to the auth
#   on resource_show. The problem with that is that the dataset.read endpoint isn't equipped as it is to handle
#   errors thrown because of a failed auth on resource_show (since in normal operation, you wouldn't expect this to
#   fail, if the user had permission to view the dataset).
#
#   Addition to the above after some thought - CKAN's `resource_view_list` is inefficient as it is; It's most often
#   called in contexts where a Resource object has already been determined, but `resource_view_list` will make no
#   attempt to check if any Resource has already been evaluated, and do another DB get for it.
#   Because of this, this version of the function completely replaces the original `resource_view_list` (see
#   this extension's plugin.py), in order to see if it can't get the resource object from the context first
def restricted_resource_view_list(context, data_dict):
    """
    Add restriction to resource_view_list.
    """
    log.debug("start restricted_resource_view_list ")
    _model = context['model']
    _session = context.get('session', _model.Session)
    _id = toolkit.get_or_bust(data_dict, 'id')

    if (resource := context.get('resource', {})) and resource.get("id") == _id:
        log.debug("already have resource dict")
        # NM: Was on the fence about performing an early check here to
        #   :py:func:`ckanext.restricted_api.auth.check_pre_evaluated_resource_show`, as it would skip over 2-3
        #   intermediary function calls if we did so, however, I think this is an encroachment of the auth function's
        #   responsibilities, and would double up on logic needing to handle any case where a resource was not
        #   restricted for the current user, but their access to `resource_view_list`, for whatever reason, was.
    else:
        log.debug("get resource")
        resource = _model.Resource.get(_id)
        if not resource:
            raise NotFound

    context['resource'] = resource
    # NM: see commentary above - this check_access will pass through to the auth function `(restricted)_resource_show`
    toolkit.check_access('resource_view_list', context, data_dict)

    # NM: I'm using our own `get_all_view_plugins` rather than get_allowed_view_plugins, because that's synonymous with
    #   what the original `resource_view_list` function was using:
    #   resource_views = [
    #         resource_view for resource_view
    #         in q.order_by(_model.ResourceView.order).all()
    #         if datapreview.get_view_plugin(resource_view.view_type)       <--- this
    #     ]
    if not (all_view_plugin_names := context.get('all_view_plugin_names', None)):
        # We'll save it to the context too, why not
        context['all_view_plugin_names'] = all_view_plugin_names = get_all_view_plugin_names()

    ## only show views when there is the correct plugin enabled
    # NM: moved this filter condition to the query level
    q = _session.query(_model.ResourceView).filter(
        _model.ResourceView.resource_id == _id, _model.ResourceView.view_type.in_(all_view_plugin_names))

    # NM: further performance improvement here: if we're only interested in the count of resource views (indicated
    #   by a `context` flag), then don't waste time fetching and dictizing stuff.
    if context.get("for_resource_view_count", False):
        log.debug("on;y for count!")
        return q.count()

    resource_views = q.order_by(_model.ResourceView.order).all()
    # NM: `resource_view_dictize` is also another one which doesn't attempt to evaluate the resource from the context
    #   it too does a Resource.get()...
    return model_dictize.resource_view_list_dictize(resource_views, context)


'''
@side_effect_free
def restricted_resource_view_list(context, data_dict):
    """Add restriction to resource_view_list."""
    model = context["model"]
    id = get_or_bust(data_dict, "id")
    resource = model.Resource.get(id)
    if not resource:
        raise NotFound
    # TODO: NM: this is horribly inefficient, because the worst case scenario is that:
    #   1) we've already evaluated the access check in the resource outside this function call
    #   2) this access check here returns successful, which means that the else block will execute, running the
    #       access check again!
    #   That's at least twice the same access check is being run, and this isn't even making an effort to look for
    #   and supply the package to restricted_resource_show!
    authorized = restricted_resource_show(
        context, {"id": resource.get("id"), "resource": resource}
    ).get("success", False)
    if not authorized:
        return []
    else:
        return resource_view_list(context, data_dict)
'''


@toolkit.chained_action
@side_effect_free
# NM: honestly, do we even really need this...?
def restricted_package_show(original_action, context, data_dict):
    """Add restriction to package_show."""
    log.debug(f"start function restricted_package_show from {inspect.currentframe().f_back.f_code.co_name}")
    package_metadata = original_action(context, data_dict)
    #log.debug(f"context is {context}")

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

    # NM: This is a break from the original implementation - if we've been told to ignore the
    #   resources of this package, we don't bother with checking/modifying their representations,
    #   we just outright remove that key from the result
    if not context.get("omit_resources", False):
        if context.get("lite_resources", False):
            log.debug('lite resources')
            # we've been asked to only return minimal information on the resources, data of which is not subject
            #   to permission checks
            restricted_package_metadata["resources"] = [
                {
                    'created': res['created'],
                    'last_modified': res['last_modified'],
                    'metadata_modified': res['metadata_modified'],
                    'format': res['format'],
                    'id': res['id'],
                    'package_id': res['package_id'],
                    'mimetype': res['mimetype'],
                    'name': res['name'],
                    'state': res['state']
                }
                for res in restricted_package_metadata.get("resources", [])
            ]
        else:
            log.debug("full thing")
            # log.debug(f"here {restricted_package_metadata.get('resources', [])}")
            # the full thing, with restricted resource fields being redacted
            restricted_package_metadata["resources"] = _restricted_resource_list_hide_fields(
                context,
                restricted_package_metadata.get("resources", []),
                get_restricted_logic_package_dict(context)
            )
    else:
        log.debug('omitting resources')
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


@side_effect_free
@toolkit.chained_action
def restricted_package_search(original_action, context, data_dict):
    """Add restriction to package_search."""
    log.debug(f"from restricted_package_search {request.path} {request.endpoint}")
    package_search_result = original_action(context, data_dict)

    restricted_package_search_result = {}

    package_show_context = context.copy()
    package_show_context["with_capacity"] = False

    # NM: Not massively happy about this, but it beats overriding each of the blueprint functions individually
    # Since we know that these blueprint pages don't render information on any resources, we can improve performance
    #   by stripping the resource information out
    if request and request.endpoint in LITE_RESOURCES_FOR_ENDPOINTS:
        log.debug("change to lite resources")
        package_show_context["lite_resources"] = True

    for key, value in package_search_result.items():
        if key == "results":
            restricted_package_search_result_list = []
            for package in value:
                restricted_package_search_result_list.append(
                    toolkit.get_action('package_show')(
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
    """Check access for a restricted resource.

    NM: removed the need to supply package_id, as only resource_id should be enough.
    """
    resource_id = data_dict.get("resource_id", False)

    user_name = get_username_from_context(context)

    if not resource_id:
        raise toolkit.ValidationError("Missing resource_id")

    log.debug(f"action.restricted_check_access: user_name = {str(user_name)}")

    # NM: removed the check on package_show, as the call to the action `resource_show` calls `package_show` anyway.
    try:
        toolkit.get_action("resource_show")(
            # NM: pass through the package_dict rather than make this do model.Package.get
            #   We also want use lite_resources, as `action.get.resource_show` from CKAN will trigger a `package_show`,
            #   and we're not interested in evaluating the restriction of all the resources.
            #   We can't outright omit_resources as `resource_show` does a check to see if the `resource_id` is in the
            #   fetched package's `resources` list.
            dict(context, return_type="dict", lite_resources=True), {"id": resource_id}
        )
    except toolkit.NotAuthorized as e:
        # NM: you don't need to manually call the check auth function... resource_show will do that for you!
        #   we still want to return the same format of result that it would have done though.
        return {
            'success': False,
            'msg': e.message
        }

    return {'success': True}


# TODO: NM: I think I can ditch this function... perhaps I can use the read schema, or IResourceController to
#  process these?
def _restricted_resource_list_hide_fields(context, resource_list, owning_package_dict=None):
    """
    Hide URLs and restricted field info (if restricted resource).

    NM: modified so it's more efficient. It now accepts an owning_package_dict which the caller is explicitly saying is
    parent package of ALL the supplied resources in the list. Technically, one could use the 'package' in the `context`,
    but taking this function as execution-context agnostic, this is too much of an assumption for my liking

    Of course, there's nothing that says the resources can come from a mixed set of packages, but there is an
    improvement for that too (see below)
    """
    log.debug(f"start function _restricted_resource_list_hide_fields from {inspect.currentframe().f_back.f_code.co_name}")
    _up = {"url": "redacted", "restricted": "redacted"}

    _copied_context = dict(context)

    def _do(res_dict, pkg_dict):
        '''
        :param res_dict: A resource dictionary, that will be modified in place
        :param pkg_dict: The resource's owning package dict
        '''
        # reuse the same _copied_context, but just overwrite this value with each new pkg_dict
        _copied_context["package"] = pkg_dict
        if not restricted_resource_show(
            context, {"id": res_dict.get("id"), "resource": res_dict}
        ).get("success", False):
            res_dict.update(_up)

    if owning_package_dict:
        # we'll change the implementation, so we're modifying the resource_list in place and not expending
        #   effort on storing and adding to a new list.
        for resource in resource_list:
            _do(resource, owning_package_dict)
    else:
        packages = {}

        for resource in resource_list:
            # we'll keep our own little cache of packages within this function call
            if not (pkg := packages.get(p_id := resource.get('package_id'), None)):
                pkg = package_to_restricted_logic_dict(model.Package.get(p_id))
                packages[p_id] = pkg

            _do(resource, pkg)

    return resource_list


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
