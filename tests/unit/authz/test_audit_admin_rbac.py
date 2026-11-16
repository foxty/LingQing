from apps.shared.authz.ta_permissions import TenantAppPermissions
from apps.shared.authz.ta_rbac import DEFAULT_ROLE_PERMISSIONS


def test_admin_role_includes_audit_manage():
    admin = DEFAULT_ROLE_PERMISSIONS["admin"]
    assert TenantAppPermissions.AUDIT_READ in admin
    assert TenantAppPermissions.AUDIT_MANAGE in admin