# Well-Architected — Playbook concept (source notes)

Source: <https://wa.aws.amazon.com/wellarchitected/2020-07-02T19-33-23/wat.concept.playbook.en.html>
Retrieved 2026-10-15. This file is a local summary for playbook authoring; it
contains no real credentials or account data.

## What a playbook is (Well-Architected definition)

> Playbooks are the predefined steps to perform to identify an issue. The
> results from any process step are used to determine the next steps to take
> until the issue is identified or escalated.

Playbooks enable **consistent and prompt responses to failure scenarios** by
documenting the investigation process. Each step helps isolate the source of
the issue until it can be identified and addressed.

Related concept: **Runbook** — the execution record of a playbook run.

## Where to start

1. **Frequently occurring issues** — reduces negative impact on business/operations.
2. **Issues with significant potential harmful impact** — mitigates risk.

## What to include (Well-Architected checklist — this playbook implements all)

### Requirements to be able to execute
- Required permissions
- Required tools and configurations
- Required network connectivity and access

### Constraints on execution
- Conflicts with other business or operations activities

### Process steps and expected results
- Process steps
- Expected results
- Follow-on steps based on results from process execution

### Escalation processes
- To whom to escalate if unable to identify the source
- After what period of time to escalate
- Third parties involved and under what circumstances
- Necessary support information for third-party escalation (serials, contacts, contracts)
- Decision makers and when to contact/notify

## Implementation in code + automatic trigger

- Implement playbooks in code where appropriate (identify steps → expected
  outcomes → code). AWS examples: **Systems Manager Run Command**, **Systems
  Manager Automation**, **Lambda**.
- Trigger automatically where appropriate: identify monitoring tests for the
  triggering events, then implement them. AWS examples: **CloudWatch Events
  (EventBridge)**, **CloudWatch Events rules** (including CloudTrail API-call
  rules).

This playbook's §5 codifies this with SSM Automation / Run Command / Lambda
and EventBridge/CloudWatch triggers.

## Keep this playbook general

Per the operator's request: this playbook is general-purpose AWS management.
Domain-specific deep dives (e.g. a full VPC migration, an RDS restore playbook)
should be separate playbooks that reuse this one's CLI bootstrap (§2).
