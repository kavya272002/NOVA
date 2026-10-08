"""Business-rule exceptions.

Every exception carries an HTTP-style status code and a machine-readable code so the
UI can show a precise message. ``persist`` marks *attempts* that must still be written
to the audit trail (e.g. an unauthorized approval) even though the transaction that
raised them is otherwise rolled back.
"""


class GovernanceError(Exception):
    status = 400
    code = "ERROR"
    persist = False

    def __init__(self, message, **extra):
        super().__init__(message)
        self.message = message
        self.extra = extra

    def to_dict(self):
        d = {"error": self.message, "code": self.code}
        d.update(self.extra)
        return d


class NotFound(GovernanceError):
    status, code = 404, "NOT_FOUND"


class AccessDenied(GovernanceError):
    status, code, persist = 403, "ACCESS_DENIED", True


class OutOfSequence(GovernanceError):
    status, code, persist = 409, "OUT_OF_SEQUENCE", True


class InvalidState(GovernanceError):
    status, code = 409, "INVALID_STATE"


class LockedCampaign(GovernanceError):
    status, code, persist = 409, "CAMPAIGN_LOCKED", True


class DuplicateRequest(GovernanceError):
    status, code, persist = 409, "DUPLICATE_REQUEST", True


class GovernanceViolation(GovernanceError):
    status, code, persist = 409, "GOVERNANCE_VIOLATION", True


class RuleConfigError(GovernanceError):
    status, code = 422, "RULE_CONFIG"


class MissingData(GovernanceError):
    status, code = 422, "MISSING_DATA"
