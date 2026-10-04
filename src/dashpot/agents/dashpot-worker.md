---
# dashpot-managed-agent: dashpot-worker
# Installed by `dashpot integrate opencode`, which rewrites this file when it
# differs from the copy Dashpot ships; `--remove` deletes it.
# The deny removes OpenCode's session-move tool from this agent, so a worker
# cannot move its lead by mistake. It is no security boundary: a shell can
# still move a session through OpenCode's HTTP API.
# No body follows, so OpenCode's default system prompt applies.
description: The worker agent the dashpot-execute-issues skill launches each worker as. Use it only for such a worker. It cannot move any session, its own or its lead's.
mode: subagent
permissions:
  - action: "*session_move"
    resource: "*"
    effect: deny
---
