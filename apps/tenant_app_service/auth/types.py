"""Auth-related shared type aliases for tenant app auth module."""

from typing import Literal

LoginMethod = Literal["native", "wecom", "dingtalk", "feishu", "oidc", "saml"]
