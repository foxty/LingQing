"""Sandbox-related filesystem paths (no EnvConfig; safe for sandbox-controller image)."""

from __future__ import annotations

import os


def get_tenant_bash_workspace_dir(data_root: str, tenant_id: int, user_id: int) -> str:
    """Persistent bash workspace: {data_root}/tenants/tenant_{id}/workspace/user_{user_id}/."""
    root_abs = os.path.abspath(data_root)
    user_part = f"user_{user_id}"
    workspace_path = os.path.abspath(os.path.join(root_abs, "tenants", f"tenant_{tenant_id}", "workspace", user_part))
    if workspace_path != root_abs and not workspace_path.startswith(f"{root_abs}{os.sep}"):
        raise ValueError("Invalid workspace path resolution.")
    return workspace_path


def get_skill_packages_dir(data_root: str) -> str:
    """Shared skill package cache root: {data_root}/skill-packages/."""
    root_abs = os.path.abspath(data_root)
    packages_path = os.path.abspath(os.path.join(root_abs, "skill-packages"))
    if packages_path != root_abs and not packages_path.startswith(f"{root_abs}{os.sep}"):
        raise ValueError("Invalid skill packages path resolution.")
    return packages_path


def get_tenant_skills_dir(data_root: str, tenant_id: int) -> str:
    """Tenant-scoped skills directory: {data_root}/tenants/tenant_{id}/skills/."""
    root_abs = os.path.abspath(data_root)
    path = os.path.abspath(os.path.join(root_abs, "tenants", f"tenant_{tenant_id}", "skills"))
    if path != root_abs and not path.startswith(f"{root_abs}{os.sep}"):
        raise ValueError("Invalid tenant skills path resolution.")
    return path


def get_tenant_skill_packages_dir(data_root: str, tenant_id: int) -> str:
    """Tenant-scoped skill package cache: {data_root}/tenants/tenant_{id}/skill-packages/."""
    root_abs = os.path.abspath(data_root)
    path = os.path.abspath(os.path.join(root_abs, "tenants", f"tenant_{tenant_id}", "skill-packages"))
    if path != root_abs and not path.startswith(f"{root_abs}{os.sep}"):
        raise ValueError("Invalid tenant skill packages path resolution.")
    return path


def get_personal_skills_dir(data_root: str, tenant_id: int, user_id: int) -> str:
    """Personal skills directory: {data_root}/tenants/tenant_{id}/workspace/user_{uid}/skills/."""
    root_abs = os.path.abspath(data_root)
    path = os.path.abspath(
        os.path.join(root_abs, "tenants", f"tenant_{tenant_id}", "workspace", f"user_{user_id}", "skills")
    )
    if path != root_abs and not path.startswith(f"{root_abs}{os.sep}"):
        raise ValueError("Invalid personal skills path resolution.")
    return path
