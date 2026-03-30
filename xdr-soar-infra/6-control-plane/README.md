# Control Plane

This manifest group scaffolds the early SOAR control plane for `SOAR_K8S`.

Current implementation status:

- `soar-api`: minimal incident consumer/API
- internal incident cache exists
- optional Supabase REST persistence exists when configured

Current gaps:

- no playbook engine
- no approvals workflow
- no command dispatcher
- no incident state machine beyond basic record ingestion
