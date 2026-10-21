"""Which rule ids act. Every other id is log-only: its hits are recorded in build/hooks/tickets/hits.jsonl and
nothing is printed. For a prompt rule "acting" means injecting its reminder as additionalContext; no prompt
rule ever blocks a prompt. For a tool rule it means a PreToolUse deny. Enforcing an id is the user's call, per
project; an agent never widens this set. The ticket system ships with both sets empty."""
MODE = "log-only"

# The ids the user has chosen to enforce in this project. None as shipped (T1 and T2 are log-only).
USER_ENFORCED = frozenset()

# Rule ids that act (see each module's decide()). Must stay a subset of USER_ENFORCED.
ENFORCE = frozenset()
