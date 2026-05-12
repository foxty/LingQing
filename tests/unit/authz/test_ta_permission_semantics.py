from apps.shared.authz.authz_permission_ta import TenantAppPermissions, ta_permission_implies


def test_manage_implies_write_and_read_for_same_resource():
    assert ta_permission_implies(TenantAppPermissions.DOCUMENTS_MANAGE, TenantAppPermissions.DOCUMENTS_WRITE)
    assert ta_permission_implies(TenantAppPermissions.DOCUMENTS_MANAGE, TenantAppPermissions.DOCUMENTS_READ)


def test_write_implies_read_for_same_resource():
    assert ta_permission_implies(TenantAppPermissions.DATA_SOURCES_WRITE, TenantAppPermissions.DATA_SOURCES_READ)


def test_cross_resource_does_not_imply():
    assert not ta_permission_implies(TenantAppPermissions.DOCUMENTS_MANAGE, TenantAppPermissions.REPORTS_READ)


def test_legacy_non_rwm_permissions_use_exact_match():
    assert ta_permission_implies(TenantAppPermissions.CHAT_ACCESS, TenantAppPermissions.CHAT_ACCESS)
    assert not ta_permission_implies(TenantAppPermissions.CHAT_ACCESS, TenantAppPermissions.CHAT_READ)
