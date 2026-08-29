# Integration boundary

There is one supported coding integration: the official Google Antigravity SDK
through `adk_harness.integrations.AntigravityIntegration`. It is discovered
lazily so a package import remains safe when the native runtime is unavailable.

```python
import asyncio

from adk_harness import AntigravityIntegration

result = asyncio.run(AntigravityIntegration().discover())
print(result["available"], result.get("detail", ""))
```

Workspace applications are built with `adk_harness.build_workspace_app` and
official ADK Workspace toolsets. They expose only the selected services and
operations, and every operation passes the policy gate independently.

The old generic adapter protocol and multi-vendor extension cookbook are
retired. Code written for those APIs must follow the breaking migration note;
new adapters are not part of this package. Cloud onboarding and remote task
execution are planned for later milestones.
