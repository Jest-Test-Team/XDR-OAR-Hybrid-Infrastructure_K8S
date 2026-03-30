# Control Plane

This manifest group scaffolds the early SOAR control plane for `SOAR_K8S`.

Current implementation status:

- `soar-api`: minimal incident consumer/API
- internal incident cache exists
- optional Supabase REST persistence exists when configured
- minimal playbook, command, and approval API surfaces exist

Current gaps:

- no real playbook engine
- no approval workflow beyond record storage
- no command dispatcher beyond record creation
- no incident state machine beyond basic record ingestion
