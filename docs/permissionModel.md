# Permission Models

There are two levels of permissions

## Global

Global permissions apply across the whole system. These affect what a user can do to functions that are global such as Services, Clients, Skills etc.

- Admin
  - Everything
- Manager
  - Clients
    - 
- User
  - Services
    - View
  - Skills/Categories
    - View lists
    - View/Edit own assigned
  - Qualifications
    - View/Edit own
  - Units
    - View

## Organisation Unit

Organisation Unit permissions define what role a member of the unit can do. It is explicit however; to have **any** view of any unit's functions you must be a member.



## Job/Phase

While not an explicit layer of permissions - business logic checks are carried out in Job/Phase actions to ensure certain functions are kept intact. For example; only the user assigned as TechQA can move a phase status beyond the TechQA stage.