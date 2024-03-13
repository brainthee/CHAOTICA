# Permission Model

Permissions in CHAOTICA are managed by both role-based and object based approaches.

The role-based permissions primarily cover higher level things such as "can you add clients" and are managed at the following levels:

- Site wide roles
- Organisational roles

There are then object level permissions which control at a lower level elements such as "who can edit this client". 

## Site Wide Roles

Site wide roles determine what a user can do across the site at a higher level. Currently the following roles exist:

- Admin
- Delivery Manager
- Service Delivery
- Sales Manager
- Sales Member
- User
- Anonymous - not directly used

### Global: Admin

As you would expect; this role has the greatest permission:

- Client
    - View/Add/Change/Delete
    - Assign Account Managers
- Service
    - View/Add/Change/Delete
- Skill Categories
    - View/Add/Change/Delete
- Skills
    - View/Add/Change/Delete
    - View Users with skill
- Organisational Units
    - View/Add/Change/Delete
    - Manage Members
    - View User's Schedules
- Certifications
    - View/Add/Change/Delete
    - View users
- Users
    - View/Add/Change/Delete
    - Impersonate User

### Global: Delivery Manager

- Client
    - View
- Service
    - View/Add/Change/Delete
- Skill Categories
    - View/Add/Change/Delete
- Skills
    - View/Add/Change/Delete
    - View Users with skill
- Organisational Units
    - View
    - View User's Schedules
- Certifications
    - View/Add/Change/Delete
    - View Users with certification
- Users
    - View

### Global: Service Delivery

- Client
    - View/Add/Change/Delete
    - Assign Account Managers
- Service
    - View
- Skill Categories
    - View
- Skills
    - View
    - View Users with skill
- Organisational Units
    - View
    - View User's Schedules
- Certifications
    - View
    - View Users with certification

### Global: Sales Manager

- Client
    - View/Add/Change/Delete
    - Assign Account Managers
- Service
    - View
- Skill Categories
    - View
- Skills
    - View
    - View Users with skill
- Organisational Units
    - View
- Certifications
    - View
    - View Users with certification

### Global: Sales Member

- Client
    - View/Add
- Service
    - View
- Skill Categories
    - View
- Skills
    - View
    - View Users with skill
- Organisational Units
    - View
- Certifications
    - View
    - View Users with certification

### Global: User

- Client
    - View
- Service
    - View
- Skill Categories
    - View
- Skills
    - View
    - View Users with skill
- Organisational Units
    - View
- Certifications
    - View
    - View Users with certification
  
## Organisation Roles

The following roles exist within an organisation unit. A user can have multiple roles:

- Manager
- Service Delivery
- Sales
- Consultant
- TQA'er
- PQA'er
- Scoper

### Manager

- Unit
    - Change/Delete
    - Manage Members
    - View User's Schedules
    - View Jobs
- Users
    - Approve All Leave Requests
    - View All Leave Requests
- Jobs
    - Scope Jobs
    - Signoff Scopes
    - Signoff Own Scopes
    - Schedule Phases

### Service Delivery

- Unit
    - View Jobs
    - Manage Members
    - View User's Schedules

### Sales

- Unit
    - View Jobs
    - Add Job

### Consultant

- Unit
    - View Jobs

### TQA

- Jobs
    - TQA Jobs

### PQA

- Jobs
    - PQA Jobs

### Scoper

- Jobs
    - Scope Jobs
    - Signoff Scopes
  
## Objects

Certain models have specific permissions. These are in addition to any permissions granted as part of site or organisational unit roles.

### Client

Users defined as Account Managers have full control over that specific client

### Service

Users defined as Service Leads 