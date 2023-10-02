# CHAOTICA

CHAOTICA stands for: **C**entralised **H**ub for **A**ssigning **O**perational **T**asks, **I**nteractive **C**alendaring and **A**lerts. Thanks ChatGPT for the backronym!

An engagement life-cycle management tool

Features:

- Workflow tracking of engagements (jobs) from birth to death
- Email/Teams alerts on status changes of jobs/phases
- Full process driven conditionals on status changes (e.g. can't submit to delivered if QA not done. Can't submit to QA if report link field empty etc)
- Tracking and conversion of scoping elements
- Stats
- Scheduling functionality. System works if this isn't used. 
- API for users to use
- Organisational Unit concepts. Allows groups/units to operate independently but allows 'overlords' oversight and stats across teams
- Team concepts - Allows grouping/membership of users (E.g. Amazon onboarded, NCSC approved people) scheduling/engagements can be enforced on member selection. 
- Skill tracking
- Import and Export of info to support data migration



## CI/CD vars needed:

* `AWS_ACCESS_KEY_ID` -  AWS Access Key
* `AWS_SECRET_ACCESS_KEY` -  AWS Secret Key
* `AWS_DEFAULT_REGION` - Region for AWS
* `AWS_REPOSITORY_URL` - The URL to the repo
* `DOMAIN_NAME` - Root Domain name - Should already have a valid R53 zone