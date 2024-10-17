# Lifecycle

!!! Warning
    This page will be populated with more documentation soon.

A job has a `status` which follows a strict workflow. Much of the functionality within CHAOTICA for a job is tied to it's status.

The raw state diagram is below and shows the allowed transitions between states.

```dot
digraph {
        subgraph cluster_jobtracker_Job_status {
                graph [label="jobtracker.Job.status"]
                "jobtracker.Job.status.10" [label=Deleted shape=doublecircle]
                "jobtracker.Job.status.3" [label="Additional Scoping Required" shape=circle]
                "jobtracker.Job.status.1" [label="Pending Scoping" shape=circle]
                "jobtracker.Job.status.5" [label="Scoping Complete" shape=circle]
                "jobtracker.Job.status.9" [label=Lost shape=circle]
                "jobtracker.Job.status.2" [label=Scoping shape=circle]
                "jobtracker.Job.status.0" [label=Draft shape=circle]
                "jobtracker.Job.status.7" [label="In Progress" shape=circle]
                "jobtracker.Job.status.8" [label=Completed shape=circle]
                "jobtracker.Job.status.6" [label="Pending Start" shape=circle]
                "jobtracker.Job.status.4" [label="Pending Scope Signoff" shape=circle]
                "jobtracker.Job.status.11" [label=Archived shape=circle]
                "jobtracker.Job.status.11" -> "jobtracker.Job.status.10" [label=to_delete]
                "jobtracker.Job.status.3" -> "jobtracker.Job.status.4" [label=to_scope_pending_signoff]
                "jobtracker.Job.status.2" -> "jobtracker.Job.status.3" [label=to_additional_scope_req]
                "jobtracker.Job.status.9" -> "jobtracker.Job.status.10" [label=to_delete]
                "jobtracker.Job.status.0" -> "jobtracker.Job.status.1" [label=to_pending_scope]
                "jobtracker.Job.status.0" -> "jobtracker.Job.status.9" [label=to_lost]
                "jobtracker.Job.status.3" -> "jobtracker.Job.status.9" [label=to_lost]
                "jobtracker.Job.status.4" -> "jobtracker.Job.status.10" [label=to_delete]
                "jobtracker.Job.status.0" -> "jobtracker.Job.status.10" [label=to_delete]
                "jobtracker.Job.status.3" -> "jobtracker.Job.status.10" [label=to_delete]
                "jobtracker.Job.status.8" -> "jobtracker.Job.status.10" [label=to_delete]
                "jobtracker.Job.status.9" -> "jobtracker.Job.status.11" [label=to_archive]
                "jobtracker.Job.status.1" -> "jobtracker.Job.status.9" [label=to_lost]
                "jobtracker.Job.status.5" -> "jobtracker.Job.status.9" [label=to_lost]
                "jobtracker.Job.status.6" -> "jobtracker.Job.status.10" [label=to_delete]
                "jobtracker.Job.status.1" -> "jobtracker.Job.status.10" [label=to_delete]
                "jobtracker.Job.status.7" -> "jobtracker.Job.status.10" [label=to_delete]
                "jobtracker.Job.status.8" -> "jobtracker.Job.status.11" [label=to_archive]
                "jobtracker.Job.status.6" -> "jobtracker.Job.status.9" [label=to_lost]
                "jobtracker.Job.status.7" -> "jobtracker.Job.status.8" [label=to_complete]
                "jobtracker.Job.status.5" -> "jobtracker.Job.status.10" [label=to_delete]
                "jobtracker.Job.status.2" -> "jobtracker.Job.status.4" [label=to_scope_pending_signoff]
                "jobtracker.Job.status.2" -> "jobtracker.Job.status.9" [label=to_lost]
                "jobtracker.Job.status.4" -> "jobtracker.Job.status.5" [label=to_scope_complete]
                "jobtracker.Job.status.1" -> "jobtracker.Job.status.2" [label=to_scoping]
                "jobtracker.Job.status.5" -> "jobtracker.Job.status.2" [label=to_scoping]
                "jobtracker.Job.status.6" -> "jobtracker.Job.status.7" [label=to_in_progress]
                "jobtracker.Job.status.5" -> "jobtracker.Job.status.7" [label=to_in_progress]
                "jobtracker.Job.status.5" -> "jobtracker.Job.status.6" [label=to_pending_start]
                "jobtracker.Job.status.2" -> "jobtracker.Job.status.10" [label=to_delete]
        }
}
```