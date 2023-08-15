"""Util to send emails."""

import json
from logging import getLogger

from ckan.common import config
from ckan.lib import mailer
from ckan.lib.base import render
from ckan.plugins import toolkit

from ckanext.restricted_api.util import get_user_from_email

log = getLogger(__name__)


def restricted_notify_access_granted(previous_value, updated_resource):
    """Notify new allowed users to a restricted dataset."""

    def _safe_json_loads(json_string):
        try:
            return json.loads(json_string)
        except Exception:
            return {}

    previous_restricted = _safe_json_loads(previous_value)
    updated_restricted = _safe_json_loads(updated_resource.get("restricted", ""))

    # compare restricted users_allowed values
    updated_allowed_users = set(updated_restricted.get("allowed_users", "").split(","))
    if updated_allowed_users:
        previous_allowed_users = previous_restricted.get("allowed_users", "").split(",")
        for user_id in updated_allowed_users:
            if user_id not in previous_allowed_users:
                send_access_granted_email(user_id, updated_resource)


def send_access_granted_email(user_id, resource):
    """Send email access granted email to user."""
    log.debug("start function send_access_granted_email")

    if not user_id:
        log.warning("No user_id provided, skipping email...")
        return

    try:
        log.info(f"Getting user details with user_id: {user_id}")
        user = toolkit.get_action("user_show")(
            data_dict={
                "id": user_id,
            },
        )

    except Exception as e:
        log.error(str(e))
        log.warning(f"Could not find a user for ID: {user_id}")
        return {"message": f"could not find a user for id: {user_id}"}

    # Extract resource name
    resource_name = resource.get("name", resource["id"])

    # Create and send email
    body = _get_access_granted_mail_body(user.as_dict(), resource_name)
    subject = f"Access granted to resource: {resource_name}"
    log.debug(f"Sending resource access email to user: {str(user.email)}")
    mailer.mail_user(user, subject, body)


def _get_access_granted_mail_body(user: dict, resource_id):
    """Generate the mail body for the access granted email."""
    log.debug("Building access granted email from template")

    if display_name := user.get("fullname"):
        pass
    elif display_name := user.get("name"):
        pass
    else:
        display_name = user.get("email")
    extra_vars = {
        "site_title": config.get("ckan.site_title"),
        "site_url": config.get("ckan.site_url"),
        "display_name": display_name,
        "resource_name": resource_id,
    }
    # NOTE: This template is translated
    access_granted_template = config.get(
        "restricted_api.access_granted_template",
        "access_granted.txt",
    )
    return render(access_granted_template, extra_vars)


def send_access_request_email(
    resource_id: str, resource_admin: str, request_user_id: str
):
    """Send email to request access to a resource."""
    log.debug("start function send_access_request_email")

    # Get resource owner details
    resource_admin_user = get_user_from_email(resource_admin)
    log.debug(f"Resource admin details: {resource_admin_user}")
    resource_admin_id = resource_admin_user.get("id")
    try:
        log.info(f"Getting user details with user_id: {resource_admin_id}")
        resource_admin_obj = toolkit.get_action("user_show")(
            data_dict={
                "id": resource_admin_id,
            },
        )

    except Exception as e:
        log.error(str(e))
        log.warning(f"Could not find a user for ID: {resource_admin_id}")
        return {"message": f"could not find a user for id: {resource_admin_id}"}

    # Create and send email
    body = _get_access_granted_mail_body(
        resource_id, resource_admin_obj.as_dict(), request_user_id
    )
    subject = f"Access request for resource: {resource_id}"
    log.debug(f"Sending resource access email to user: {str(resource_admin_obj.email)}")
    mailer.mail_user(resource_admin_obj, subject, body)


def _get_access_request_mail_body(
    resource_id: str, resource_owner: dict, request_user_id: str
):
    """Generate the mail body for the access request email."""
    log.debug("Building access request email from template")

    if display_name := resource_owner.get("fullname"):
        pass
    elif display_name := resource_owner.get("name"):
        pass
    else:
        display_name = resource_owner.get("email")
    extra_vars = {
        "site_title": config.get("ckan.site_title"),
        "site_url": config.get("ckan.site_url"),
        "display_name": display_name,
        "resource_id": resource_id,
        "request_user_id": request_user_id,
    }
    # NOTE: This template is translated
    access_request_template = config.get(
        "restricted_api.access_request_template",
        "access_request.txt",
    )
    return render(access_request_template, extra_vars)
