# Control Plane

This manifest group scaffolds the early SOAR control plane for `SOAR_K8S`.

Current implementation status:

- `soar-api`: minimal incident consumer/API
- `command-dispatcher`: command lifecycle worker
- internal incident cache exists
- optional Supabase REST persistence exists when configured
- minimal playbook, command, and approval API surfaces exist
- incident-to-playbook matching exists
- approval decision and command status transition endpoints exist
- audit log surface exists
- optional persistence targets now cover incidents, playbooks, commands, approvals, and audit logs
- approved or auto-queued commands can now be published to `commands.issue`
- command lifecycle events can now be emitted to `commands.lifecycle`

Current gaps:

- no real playbook engine
- no approval workflow beyond in-memory state transitions
- no device ACK/result reconciliation yet
- no incident state machine beyond basic record ingestion
