# Changelog

## 2026-10-14 - Permission hardening

Security fixes from the permissions review:

- **Site-data import** (Settings → Import) now requires `manage_site_settings`. It
  was reachable by any logged-in user, and the user CSV importer could set
  `is_superuser` / `is_staff` / `is_active`; those columns are no longer accepted,
  and manager columns no longer create accounts.
- **Impersonation** is superuser-only (previously any `is_staff` user) and every
  session start and stop is audited.
- **Workflow checklists** require the `workflowtask` model permissions.
- **Scheduler**: slot create/edit re-verifies the unit of the phase, project or
  user actually submitted, so bookings can't be made in another unit's jobs.
- **Scheduled reports** may only run as yourself or people you manage (report
  admins: anyone), and only email internal addresses.
- **Job guests**: being booked on a job grants view, schedule and notes;
  `can_update_job` is limited to phase leads, authors and QA reviewers.
- **Org units**:
    - deactivation revokes unit permissions immediately;
    - only `manage_user` holders can re-enable a disabled account via pre-load;
    - you can't pre-load yourself;
    - roles carrying unit-admin rights can only be granted by someone holding
      those rights.
- **Role codenames**: three typos that silently dropped grants are fixed:
    - qualification visibility for all global roles;
    - Manage User for Delivery Managers;
    - the Consultant delivery queue.

    Unknown codenames are now logged, and a test catches them.
- **Access scoping**:
    - unit leave approvers only cover current members and can't approve their own
      leave;
    - user calendar feeds follow the scheduler visibility rule;
    - following a job/phase/unit needs view access;
    - nobody can be their own manager.

See [Permission Model](../administration/permissions.md).
