"""
MIGRATED TO TEMPORAL — this file replaces the old SlaScheduler tests.

The background polling scheduler (SlaScheduler / sla_scheduler.py) has been
removed as part of the Temporal migration. SLA enforcement is now handled by
Temporal's durable workflow timer (workflow.wait_condition with a 60-second
timeout inside SlaWorkflow).

The equivalent test coverage lives in:
  tests/test_temporal_activities.py  — unit tests for all Temporal activities
    including escalate_ticket_activity and notify_manager_activity.

This file is intentionally left as a placeholder so CI does not flag a missing
module import. No tests are defined here.
"""
