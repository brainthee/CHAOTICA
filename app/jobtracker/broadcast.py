"""Fan committed ScheduleActions out to open viewers over the channel layer.

Called from :func:`jobtracker.schedule_history.record` (and, transitively,
``revert``) after each commit. A phase-scoped change reaches the phase group, its
job group, and the global board; a job-scoped change reaches the job group and
global; an unscoped change reaches only global. Guarded so a missing/broken
channel layer never breaks the originating mutation.
"""
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from . import schedule_history


def _target_groups(action):
    groups = ["schedule_global"]
    if action.job_id:
        groups.append("schedule_job_{}".format(action.job_id))
    if action.phase_id:
        groups.append("schedule_phase_{}".format(action.phase_id))
    return groups


def broadcast_action(action):
    layer = get_channel_layer()
    if layer is None:
        return
    delta = schedule_history.build_delta(action)
    message = {"type": "schedule.delta", "delta": delta}
    send = async_to_sync(layer.group_send)
    for group in _target_groups(action):
        send(group, message)
