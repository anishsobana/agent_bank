class BankError(Exception):
    """Business-rule violation (insufficient funds, unknown card...) returned to the agent as a tool error."""
