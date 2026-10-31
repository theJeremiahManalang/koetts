# Operational references

This directory contains hosted configuration and operations references.
Human developer setup and GCP diagrams live in [root resources](../../resources/README.md).
The [hosted plan](../plans/hosted-service-plan.md) owns intended scope; [status](../STATUS.md)
distinguishes implemented offline behavior from live acceptance.

- [Infrastructure configuration](hosted-infrastructure.md): Terraform inputs,
  dedicated identities, regional placement, ADC and signing-secret ownership.
- [Rollout and rollback](hosted-rollout.md): evidence, API replacement, staged
  frontend migration, compatibility gates and dated preflight observations.
- [Cost controls](hosted-cost-controls.md): allowances, production pause,
  operator CLI, billing attribution and reconciliation.
- [Artifact collection](hosted-artifact-collection.md): reference-aware deletion,
  maintenance fencing and interrupted-collector recovery.
