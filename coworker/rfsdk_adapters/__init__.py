"""rfsdk port adapters and the governed dispatch layer (OW-F-014).

Imported only on the OPENWORKER_EXECUTOR=temporal path; with the env unset, neither this
package nor rfsdk_kernel enters sys.modules (tests/test_rfsdk_optin.py).
"""
from .governed import ANCHOR_UNAVAILABLE, GovernedDispatch, dispatch_caller, read_fabric_anchor
from .sqlite_ports import (
    SqliteApprovalStore,
    SqliteChangeBus,
    SqliteEvidenceStore,
    TenantPolicy,
)

__all__ = [
    "ANCHOR_UNAVAILABLE",
    "GovernedDispatch",
    "SqliteApprovalStore",
    "SqliteChangeBus",
    "SqliteEvidenceStore",
    "TenantPolicy",
    "dispatch_caller",
    "read_fabric_anchor",
]
