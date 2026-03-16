# Qualification Administration

This guide covers setting up and managing the qualification system. These tasks are typically performed by administrators or team leads.

## Awarding Bodies

Awarding bodies are the organisations that issue qualifications. Each qualification belongs to exactly one awarding body.

### Creating an Awarding Body

Navigate to **Operations > Qualifications** and use the admin interface or the add form to create a new awarding body.

**Fields:**

| Field | Description | Required |
|-------|-------------|----------|
| **Name** | Full name of the awarding body (e.g. "CREST", "Offensive Security") | Yes |
| **Description** | Brief description of the organisation | No |
| **URL** | Website URL for the awarding body | No |
| **Logo** | Logo image file | No |

!!! example
    - **CREST** — Council of Registered Ethical Security Testers
    - **Offensive Security** — Provider of OSCP, OSCE, and related certifications
    - **EC-Council** — International Council of E-Commerce Consultants (CEH, CHFI)
    - **ISC2** — International Information System Security Certification Consortium (CISSP, CCSP)

## Qualifications

Qualifications are the specific certifications or credentials issued by awarding bodies.

### Creating a Qualification

**Fields:**

| Field | Description | Required |
|-------|-------------|----------|
| **Name** | Full qualification name (e.g. "Certified Ethical Hacker") | Yes |
| **Short Name** | Abbreviated form (e.g. "CEH") | No |
| **Awarding Body** | The issuing organisation | Yes |
| **Description** | Detailed description of the qualification | No |
| **Tags** | Categories for filtering and organisation | No |
| **Validity Period** | Number of days the qualification is valid (leave empty for no expiry) | No |
| **Verification Required** | Whether manager verification is needed for awarded records | No (default: off) |
| **URL** | Link to the qualification's official page | No |
| **Guidance URL** | Link to internal guidance or study resources | No |

### Validity Period

The validity period determines how long a qualification lasts from the date it is awarded. When a user sets their awarded date, the lapse date is automatically calculated.

**Common validity periods:**

| Qualification | Typical Validity | Days |
|--------------|-----------------|------|
| CREST CRT | 3 years | 1095 |
| OSCP | No expiry | *(leave empty)* |
| CEH | 3 years | 1095 |
| CISSP | 3 years | 1095 |
| ISO 27001 Lead Auditor | 3 years | 1095 |

!!! tip
    If a qualification does not expire, leave the validity period empty. The system will show "Does not expire" and no lapse tracking will occur.

### Verification Required

When **Verification Required** is enabled on a qualification:

- Awarded records show a verification status indicator (checkmark or question mark)
- Managers can verify/unverify records from the Team Qualifications page
- Unverified counts appear in the manager's team dashboard
- The unverified alert banner only counts qualifications with this flag enabled

**When to enable verification:**

- Qualifications that are critical for compliance (e.g. CHECK team member status)
- Qualifications required for specific client engagements
- Qualifications where proof of award needs to be confirmed

**When to leave it off:**

- Nice-to-have or self-improvement qualifications
- Qualifications where the organisation has no formal verification process
- Low-risk certifications

!!! note "Default: Off"
    Verification is off by default. Enable it selectively for qualifications where manager oversight adds value.

## Qualification Tags

Tags allow you to categorise qualifications for easier browsing and filtering on the catalogue page.

**Example tags:**

- Penetration Testing
- Governance & Compliance
- Cloud Security
- Network Security
- Application Security
- Management

Tags are managed via the Django admin interface and can be assigned to qualifications when creating or editing them.

## Automatic Expiry Job

A daily cron job (`task_check_qualification_expiry`) runs automatically to check for expired qualifications. Any **Awarded** qualification whose lapse date has passed is automatically moved to **Lapsed** status.

This job is configured in the application settings and requires no manual intervention.

!!! warning
    The expiry job only affects records with a lapse date set. Qualifications without a validity period (and therefore no lapse date) will never automatically lapse.

## Related Topics

- [Qualifications Overview](overview.md) — User guide for managing qualifications
- [User Management](../team/user_management.md) — Managing user accounts and team structure
- [Application Settings](../../administration/chaotica_settings.md) — System-wide configuration
