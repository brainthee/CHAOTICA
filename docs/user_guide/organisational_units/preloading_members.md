# Pre-loading & Importing Members

Normally a user only exists in CHAOTICA *after* they first log in (via SSO in
production), at which point an administrator still has to grant them a site role
and add them to a unit. Pre-loading collapses that into a single up-front action:
a unit manager can create the account, assign roles, and add the person to their
unit before they've ever signed in.

Because sign-in matches users by **email address**, a pre-loaded account is
adopted automatically the first time the person logs in (SSO or local) — they
land with the roles you assigned already in place.

Both features live on the [unit detail page](overview.md) and require the
`manage_members` permission on that unit.

## Pre-load a single member

1. Open the unit and click **Pre-load Member**.
2. Enter the person's **email address** and (optionally) their name.
3. Choose their **unit role(s)** — this defaults to the standard member role.
4. Optionally tick **Email the user** to let them know they have access.
5. Save.

If the email already belongs to an existing user, they're simply added to the
unit (their existing site role is left untouched).

### Site (global) roles

- **Unit managers** can only grant the default **User** site role. New accounts
  automatically receive it so they have baseline access on first login.
- Users who also hold the global **Manage Users** permission see an extra
  **Site Role** field and may grant elevated site roles (e.g. Manager, Admin).

## Bulk import from CSV

1. Open the unit and click **Import CSV**.
2. Click **Download Template CSV** to get a correctly-headed file.
3. Fill in one row per person and upload it.

The importer processes the whole file in a single transaction and reports how
many rows succeeded and which failed (and why).

### CSV columns

| Column | Required | Notes |
|---|---|---|
| `email` | Yes | The person's email address. |
| `first_name` | No | Given name. |
| `last_name` | No | Family name. |
| `site_role` | No | Site-wide role name (e.g. `User`, `Admin`). Only applied if you hold the **Manage Users** permission; ignored otherwise. |
| `unit_roles` | No | One or more unit role names separated by `;` or `,` (e.g. `Consultant;Scoper`). Defaults to the standard member role if left blank. |

Rows are skipped (and reported) when the email is missing, the domain isn't
allowed (see below), or a named unit/site role doesn't exist.

## Email domain allowlist

To stop typos or out-of-scope addresses being added, site administrators can
restrict which email domains may be added or self-register. Set
**Allowed signup email domains** on the [settings page](../../administration/chaotica_settings.md)
to a comma-separated list (e.g. `accenture.com, example.org`). Leave it blank to
allow any domain (the default).

The allowlist is enforced on pre-loading, CSV import, self-registration, and the
invite form.

## Related Topics

- [Organisational Units Overview](overview.md)
- [User Management](../team/user_management.md)
