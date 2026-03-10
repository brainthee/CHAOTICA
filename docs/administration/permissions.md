# Permission Model

Permissions in CHAOTICA are managed through a layered approach combining role-based and object-level access control.

| Layer | Mechanism | Scope | Defined in |
|---|---|---|---|
| **Global Roles** | Django Groups | Site-wide | `chaotica_utils.enums.GlobalRoles` |
| **Organisational Unit Roles** | Django Guardian (object-level) | Per unit and its jobs | `chaotica_utils.enums.UnitRoles` |
| **Object-Level Permissions** | Django Guardian (per object) | Individual clients, services, etc. | Model `Meta.permissions` |
| **Job Guest Access** | Django Guardian | Per job | `jobtracker.enums.JobGuestPermissions` |

## How Permissions Are Enforced

- **Global permissions** are assigned to Django Groups (prefixed with `GLOBAL_GROUP_PREFIX` from settings). When a user is assigned a global role, they are added to the corresponding group.
- **Unit permissions** are assigned per-object via [Django Guardian](https://django-guardian.readthedocs.io/). When a user's unit membership or roles change, `OrganisationalUnit.sync_permissions()` reconciles their guardian permissions against what their roles grant.
- **Views** use decorators such as `@permission_required`, `@unit_permission_required_or_403`, and `@job_permission_required_or_403` to check access.

---

## Global Roles

Global roles determine what a user can do across the entire site. They are stored as Django Groups and managed via the `GlobalRoles` class in `chaotica_utils/enums.py`.

Every user is assigned exactly one global role. The **default role** for new users is `USER`.

| Constant | Value | Display Name | Colour |
|---|---|---|---|
| `ANON` | 0 | Anonymous | light |
| `ADMIN` | 1 | Admin | danger (red) |
| `DELIVERY_MGR` | 2 | Manager | warning (yellow) |
| `SERVICE_DELIVERY` | 3 | Service Delivery | success (green) |
| `SALES_MGR` | 4 | Sales Manager | info (blue) |
| `SALES_MEMBER` | 5 | Sales Member | info (blue) |
| `USER` | 6 | User | secondary (grey) |

### Global: Admin

Full system access including user management, impersonation, site settings, and activity logs.

| Area | Permissions |
|---|---|
| Clients | View, Add, Change, Delete, Assign Account Managers |
| Framework Agreements | View, Add, Change, Delete |
| Contacts | View, Add, Change, Delete |
| Services | View, Add, Change, Delete |
| Teams | View, Add, Change, Delete |
| Skill Categories | View, Add, Change, Delete |
| Skills | View, Add, Change, Delete, View Users |
| Organisational Units | View, Add, Change, Delete, Manage Members, View User Schedules |
| Qualifications | View, Add, Change, Delete, View Users |
| Workflow Tasks | View, Add, Change, Delete |
| Leave | Manage Leave |
| Billing Codes | View, Add, Change, Delete |
| Users | Manage User, Impersonate Users, Manage Site Settings, View Activity Logs |

### Global: Manager (Delivery Manager)

Focused on delivery operations — full service and team management, skills, qualifications, billing, and leave management. Read-only access to clients.

| Area | Permissions |
|---|---|
| Clients | View |
| Framework Agreements | View |
| Contacts | View |
| Services | View, Add, Change, Delete |
| Teams | View, Add, Change, Delete |
| Skill Categories | View, Add, Change, Delete |
| Skills | View, Add, Change, Delete, View Users |
| Organisational Units | View, View User Schedules |
| Qualifications | View, Add, Change, Delete, View Users |
| Workflow Tasks | View |
| Leave | Manage Leave |
| Billing Codes | View, Add, Change, Delete |
| Users | Manage User |

### Global: Service Delivery

Client and framework management with service delivery focus. Read-only access to services, skills, and qualifications.

| Area | Permissions |
|---|---|
| Clients | View, Add, Change, Delete, Assign Account Managers |
| Framework Agreements | View, Add, Change, Delete |
| Contacts | View |
| Services | View |
| Teams | View, Add |
| Skill Categories | View |
| Skills | View, View Users |
| Organisational Units | View, View User Schedules |
| Qualifications | View, View Users |
| Workflow Tasks | View |
| Leave | Manage Leave |
| Billing Codes | View, Add |

### Global: Sales Manager

Client and commercial management with full billing code access.

| Area | Permissions |
|---|---|
| Clients | View, Add, Change, Delete, Assign Account Managers |
| Framework Agreements | View, Add, Change, Delete |
| Contacts | View, Add, Change, Delete |
| Services | View |
| Teams | View, Add |
| Skill Categories | View |
| Skills | View, View Users |
| Organisational Units | View |
| Qualifications | View, View Users |
| Billing Codes | View, Add, Change, Delete |

### Global: Sales Member

Client creation and contact management. Limited to viewing most other areas.

| Area | Permissions |
|---|---|
| Clients | View, Add |
| Framework Agreements | View, Add |
| Contacts | View, Add, Change, Delete |
| Services | View |
| Teams | View, Add |
| Skill Categories | View |
| Skills | View, View Users |
| Organisational Units | View |
| Qualifications | View, View Users |
| Billing Codes | View, Add |

### Global: User

Baseline read-only access. All authenticated users receive this role by default.

| Area | Permissions |
|---|---|
| Clients | View |
| Framework Agreements | View |
| Contacts | View |
| Services | View |
| Teams | View, Add |
| Skill Categories | View |
| Skills | View, View Users |
| Organisational Units | View |
| Qualifications | View, View Users |
| Billing Codes | View |

---

## Organisational Unit Roles

Unit roles grant permissions scoped to a specific organisational unit and its jobs. They are enforced via Django Guardian object-level permissions against the `OrganisationalUnit` instance.

A user can hold **multiple roles** within a unit. Their effective permissions are the union of all assigned roles. Roles are defined as `OrganisationalUnitRole` model instances, seeded from defaults in `UnitRoles.DEFAULTS` (`chaotica_utils/enums.py`).

When a membership or role changes, `OrganisationalUnit.sync_permissions()` automatically adds or removes guardian permissions to match.

### Role Definitions

| Constant | Value | Display Name | Colour | Default | Manager |
|---|---|---|---|---|---|
| `PENDING` | 1 | Pending Approval | secondary | No | No |
| `CONSULTANT` | 2 | Consultant | primary | **Yes** | No |
| `SALES` | 3 | Sales | success | No | No |
| `SERVICE_DELIVERY` | 4 | Service Delivery | info | No | No |
| `MANAGER` | 5 | Manager | danger | No | **Yes** |
| `TQA` | 6 | Tech QA'er | info | No | No |
| `PQA` | 7 | Pres QA'er | info | No | No |
| `SCOPER` | 8 | Scoper | info | No | No |
| `SUPERSCOPER` | 9 | Super Scoper | info | No | No |
| `SCHEDULER` | 10 | Scheduler | info | No | No |

**Default Role**: Consultant — automatically assigned when a user joins a unit.

**Manager Role**: Manager — grants `manage_role` flag, allowing the user to manage other members.

### Notification Pool Roles

These roles do not grant operational permissions. They control which users are included in notification pools for specific activities.

| Constant | Value | Display Name | Permission |
|---|---|---|---|
| `POOL_SCHEDULER` | 11 | Scheduling Pool | `notification_pool_scheduling` |
| `POOL_SCOPER` | 12 | Scoping Pool | `notification_pool_scoping` |
| `POOL_TQA` | 13 | TQA Pool | `notification_pool_tqa` |
| `POOL_PQA` | 14 | PQA Pool | `notification_pool_pqa` |

### Pending

No permissions. The user's membership is awaiting approval.

### Consultant

The default role for delivery consultants. Grants basic job access and delivery capability.

| Permission | Description |
|---|---|
| `can_view_jobs` | Can view jobs |
| `view_job_schedule` | View a job's schedule |
| `can_update_job` | Can update jobs |
| `can_add_note_job` | Can add a note to jobs |
| `view_users_schedule` | View member schedules |
| `view_organisationalunit` | View the organisational unit |
| `can_deliver_job` | Can deliver a job |

### Sales

Job viewing and creation with point-of-contact assignment.

| Permission | Description |
|---|---|
| `view_organisationalunit` | View the organisational unit |
| `can_view_jobs` | Can view jobs |
| `view_job_schedule` | View a job's schedule |
| `can_update_job` | Can update jobs |
| `can_add_note_job` | Can add a note to jobs |
| `view_users_schedule` | View member schedules |
| `can_add_job` | Can add jobs |
| `can_assign_poc_job` | Can assign a Point of Contact to jobs |

### Service Delivery

Scheduling, member management, and leave oversight.

| Permission | Description |
|---|---|
| `view_organisationalunit` | View the organisational unit |
| `can_view_jobs` | Can view jobs |
| `view_job_schedule` | View a job's schedule |
| `can_update_job` | Can update jobs |
| `can_add_note_job` | Can add a note to jobs |
| `view_users_schedule` | View member schedules |
| `can_refire_notifications_job` | Can refire notifications for jobs |
| `can_schedule_job` | Can schedule phases |
| `manage_members` | Assign members |
| `can_approve_leave_requests` | Can approve leave requests |
| `can_view_all_leave_requests` | Can view all leave for members of the unit |

### Manager

Full unit management — the most privileged unit-level role. Includes scoping signoff, job lifecycle control, scheduling, and leave management.

| Permission | Description |
|---|---|
| `can_view_jobs` | Can view jobs |
| `view_job_schedule` | View a job's schedule |
| `can_update_job` | Can update jobs |
| `can_add_note_job` | Can add a note to jobs |
| `can_refire_notifications_job` | Can refire notifications for jobs |
| `view_users_schedule` | View member schedules |
| `view_organisationalunit` | View the organisational unit |
| `change_organisationalunit` | Change the organisational unit |
| `delete_organisationalunit` | Delete the organisational unit |
| `manage_members` | Assign members |
| `can_scope_jobs` | Can scope jobs |
| `can_assign_poc_job` | Can assign a Point of Contact to jobs |
| `can_signoff_scopes` | Can signoff scopes |
| `can_signoff_own_scopes` | Can signoff own scopes |
| `can_add_job` | Can add jobs |
| `can_delete_job` | Can delete jobs |
| `can_add_phases` | Can add phases |
| `can_delete_phases` | Can delete phases |
| `can_schedule_job` | Can schedule phases |
| `can_approve_leave_requests` | Can approve leave requests |
| `can_view_all_leave_requests` | Can view all leave for members of the unit |

### TQA (Tech QA'er)

| Permission | Description |
|---|---|
| `can_tqa_jobs` | Can TQA jobs |

### PQA (Pres QA'er)

| Permission | Description |
|---|---|
| `can_pqa_jobs` | Can PQA jobs |

### Scoper

Can scope jobs and manage phases. Can sign off other people's scopes but **not** their own.

| Permission | Description |
|---|---|
| `can_scope_jobs` | Can scope jobs |
| `can_signoff_scopes` | Can signoff scopes |
| `can_add_phases` | Can add phases |
| `can_delete_phases` | Can delete phases |

### Super Scoper

Can scope jobs and sign off scopes — including their own. Does **not** have phase add/delete permissions (unlike Scoper).

| Permission | Description |
|---|---|
| `can_scope_jobs` | Can scope jobs |
| `can_signoff_scopes` | Can signoff scopes |
| `can_signoff_own_scopes` | Can signoff own scopes |

### Scheduler

Dedicated scheduling access without broader job management.

| Permission | Description |
|---|---|
| `can_schedule_job` | Can schedule phases |
| `view_job_schedule` | View a job's schedule |
| `view_users_schedule` | View member schedules |

---

## All Unit-Level Permissions

These custom permissions are defined on the `OrganisationalUnit` model's `Meta.permissions` and are assigned via Django Guardian.

### Job Management

| Codename | Description |
|---|---|
| `can_view_jobs` | Can view jobs |
| `can_add_job` | Can add jobs |
| `can_update_job` | Can update jobs |
| `can_delete_job` | Can delete jobs |
| `can_add_note_job` | Can add a note to jobs |
| `can_assign_poc_job` | Can assign a Point of Contact to jobs |
| `can_manage_framework_job` | Can manage framework agreements for jobs |
| `can_refire_notifications_job` | Can refire notifications for jobs |
| `can_deliver_job` | Can deliver a job |

### Phase Management

| Codename | Description |
|---|---|
| `can_add_phases` | Can add phases |
| `can_delete_phases` | Can delete phases |
| `can_schedule_job` | Can schedule phases |
| `view_job_schedule` | View a job's schedule |

### Scoping

| Codename | Description |
|---|---|
| `can_scope_jobs` | Can scope jobs |
| `can_signoff_scopes` | Can signoff scopes |
| `can_signoff_own_scopes` | Can signoff own scopes |

### Quality Assurance

| Codename | Description |
|---|---|
| `can_tqa_jobs` | Can perform Technical QA |
| `can_pqa_jobs` | Can perform Presentation QA |
| `can_deliver_jobs` | Can deliver jobs |
| `can_conduct_review` | Can conduct reviews |
| `can_view_all_reviews` | Can view all reviews |

### Unit & Member Management

| Codename | Description |
|---|---|
| `manage_members` | Assign members to the unit |
| `view_users_schedule` | View member schedules |

### Leave Management

| Codename | Description |
|---|---|
| `can_view_all_leave_requests` | Can view all leave for members of the unit |
| `can_approve_leave_requests` | Can approve leave requests |

### Notification Pools

| Codename | Description |
|---|---|
| `notification_pool_scoping` | Scoping pool |
| `notification_pool_scheduling` | Scheduling pool |
| `notification_pool_tqa` | TQA pool |
| `notification_pool_pqa` | PQA pool |

---

## Object-Level Permissions

Certain models define additional permissions that are assigned directly to users for specific object instances via Django Guardian.

### Client

| Codename | Description | Assigned to |
|---|---|---|
| `assign_account_managers_client` | Assign Account Managers | Global roles: Admin, Service Delivery, Sales Manager |

Users designated as **Account Managers** on a client receive full control over that specific client object.

### Service

| Codename | Description | Assigned to |
|---|---|---|
| `assign_to_phase` | Assign service to a phase | (Used during phase setup) |
| `change_service` | Change service details | Service Owners (via Guardian) |
| `delete_service` | Delete service | Service Owners (via Guardian) |

When a user is set as the **owner** of a service, they are granted `change_service` and `delete_service` guardian permissions on that specific service instance.

### User

| Codename | Description |
|---|---|
| `manage_user` | Can manage the user |
| `manage_leave` | Manage leave |
| `impersonate_users` | Can impersonate other users |
| `manage_site_settings` | Can change site settings |
| `view_activity_logs` | Can review the activity logs |

---

## Job Guest Permissions

Users added as **guests** on a job receive a limited set of guardian permissions, defined in `JobGuestPermissions.ALLOWED` (`jobtracker/enums.py`):

| Permission | Description |
|---|---|
| `view_job_schedule` | View the job's schedule |
| `can_update_job` | Update the job |
| `can_add_note_job` | Add notes to the job |
| `can_view_jobs` | View the job |

---

## Phase-Level Assignments

Phases do not define their own permissions model. Access is inherited from the parent job's organisational unit. However, phases track key stakeholder assignments:

| Field | Role |
|---|---|
| `project_lead` | Person leading the phase delivery |
| `report_author` | Person writing the report |
| `techqa_by` | Technical QA reviewer |
| `presqa_by` | Presentation QA reviewer |

These assignments drive workflow transitions (e.g. who can move a phase into TQA or PQA status) and notification routing.

---

## Job Support Team Roles

Jobs can have a support team with defined roles, stored in the `JobSupportTeamRole` model (`jobtracker/models/job.py`). These track allocation and billing but do not directly grant permissions.

| Constant | Value | Display Name |
|---|---|---|
| `OTHER` | 0 | Other |
| `COMMERCIAL` | 1 | Commercial |
| `QA` | 1 | QA |
| `SCOPE` | 2 | Scope |

!!! warning
    `COMMERCIAL` and `QA` share the same integer value (1) in `JobSupportRole`.

---

## Permission Synchronisation

### Global Roles

Global permissions are stored as standard Django Group permissions. Each global role maps to a Group with a configurable prefix (`GLOBAL_GROUP_PREFIX`). The `Group.sync_global_permissions()` method ensures group permissions match the `GlobalRoles.PERMISSIONS` definitions.

### Unit Roles

Unit permissions use Django Guardian for object-level access. The `OrganisationalUnitRole` model stores a `ManyToManyField` to `Permission`, seeded from `UnitRoles.PERMISSIONS` via `sync_default_permissions()`.

When a user's membership changes (join, leave, role change), `OrganisationalUnit.sync_permissions()`:

1. Collects the user's current guardian permissions on the unit
2. Computes expected permissions from all their assigned roles
3. Adds any missing permissions
4. Removes any revoked permissions

This ensures permissions always reflect the user's current roles.

### Customising Role Permissions

Unit role permissions can be customised beyond their defaults. Since `OrganisationalUnitRole.permissions` is a standard `ManyToManyField`, administrators can add or remove individual permissions from any role via the Django admin. The `sync_default_permissions()` method only runs when explicitly called to reset a role to its defaults.
