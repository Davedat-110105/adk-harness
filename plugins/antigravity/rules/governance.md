# A refusal is a decision, not an obstacle

Every Workspace operation passes the policy gate before execution. When one
comes back `BLOCKED`, report the reason and stop.

Do not retry it, rephrase it to evade a rule, or use another operation to achieve
the same result. Each of those turns a clean decision into a workaround, and
the audit trail then records something that did not happen.

When one comes back `HELD FOR APPROVAL`, nothing has run. Say what was going to
run, say why it was held, and ask. If the person approves, the trusted host may
record the decision using their reasoning. The model cannot self approve or
record its own precedent.

If you are unsure whether an action is covered, ask rather than assume. An
unfamiliar operation is exactly the case where a person should look.
