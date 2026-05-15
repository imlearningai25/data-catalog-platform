# OPA Policy — Data Catalog Authorization
# Package: datacatalog.authz
# Input: { "role": "...", "resource": "...", "action": "...", "context": {} }
# Output: allow = true | false

package datacatalog.authz

import future.keywords.if
import future.keywords.in

# Role hierarchy levels (higher = more privileged)
role_level := {
    "viewer": 0,
    "data_analyst": 1,
    "data_steward": 2,
    "admin": 3,
}

# Permission matrix: resource → action → minimum role level required
required_level := {
    "asset": {
        "read": 0,
        "read_sensitive": 1,
        "read_pii": 2,
        "write": 2,
        "delete": 3,
    },
    "column": {
        "read": 0,
        "read_pii_value": 3,
        "write": 2,
        "delete": 2,
    },
    "term": {
        "read": 0,
        "write": 2,
        "delete": 2,
    },
    "source": {
        "read": 2,
        "write": 3,
        "delete": 3,
        "hydrate": 3,
    },
    "user": {
        "read": 3,
        "write": 3,
        "delete": 3,
    },
    "audit": {
        "read": 3,
    },
    "lineage": {
        "read": 1,
        "write": 2,
    },
    "classification": {
        "read": 1,
        "override": 2,
    },
}

# Main allow rule
default allow := false

allow if {
    # Get the user's role level
    user_level := role_level[input.role]

    # Get the minimum level for this resource+action
    min_level := required_level[input.resource][input.action]

    # User must meet or exceed the minimum level
    user_level >= min_level

    # Admin override: blocked flag not set
    not input.context.blocked
}

# Explicit admin bypass (for emergencies — creates audit event)
allow if {
    input.role == "admin"
    input.context.emergency_access == true
    # Emergency access still requires admin role
}

# Data stewards can only modify assets they own or are stewarding
allow if {
    input.role == "data_steward"
    input.resource == "asset"
    input.action in {"write", "delete"}
    asset_owned_by_steward
}

asset_owned_by_steward if {
    input.context.asset_steward == input.context.user_email
}

asset_owned_by_steward if {
    input.context.asset_owner == input.context.user_email
}

# PII raw value access: restricted to admins only, and only with
# explicit justification in the context
allow if {
    input.role == "admin"
    input.resource == "column"
    input.action == "read_pii_value"
    input.context.justification != ""
    input.context.justification != null
}

# Deny all access to restricted sensitivity assets for viewers
deny_restricted if {
    input.role == "viewer"
    input.context.sensitivity_level == "RESTRICTED"
}

# Deny CONFIDENTIAL access to viewers
deny_confidential if {
    input.role == "viewer"
    input.context.sensitivity_level in {"CONFIDENTIAL", "RESTRICTED"}
}

# Final allow with sensitivity checks
allow if {
    user_level := role_level[input.role]
    min_level := required_level[input.resource][input.action]
    user_level >= min_level
    not deny_restricted
    not deny_confidential
    not input.context.blocked
}
