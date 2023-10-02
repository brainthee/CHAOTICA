# CHAOTICA

[![Project Status: WIP – Initial development is in progress, but there has not yet been a stable, usable release suitable for the public.](https://www.repostatus.org/badges/latest/wip.svg)](https://www.repostatus.org/#wip) - **WARNING - THIS PROJECT IS IN EARLY STAGES. I DO NOT ADVISE YOU USE IT YET.**

CHAOTICA stands for: **C**entralised **H**ub for **A**ssigning **O**perational **T**asks, **I**nteractive **C**alendaring and **A**lerts. Thanks ChatGPT for the backronym!

It is a Django based engagement life-cycle management tool. Primaryily geared to security testing teams.

(Planned) Features:

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
- Service tracking with skills definable (e.g. service X must have skill Y)

## Roadmap

In time, this will outline what should be expected for version 1 and what will be added later on.

## Support

This project is maintained by @brainthee. Please understand that I can not provide individual support via email. I also believe that help is much more valuable if it’s shared publicly, so that more people can benefit from it. So please raise any problems on the project issue tracker.

## Installation

There are no released versions yet. Eventually you will be able to pull the latest image from DockerHub.

## Contributing

Pull requests are welcome. For major changes, please open an issue first
to discuss what you would like to change.

## Deployment

### CI/CD vars needed:

* `AWS_ACCESS_KEY_ID` -  AWS Access Key
* `AWS_SECRET_ACCESS_KEY` -  AWS Secret Key
* `AWS_DEFAULT_REGION` - Region for AWS
* `AWS_REPOSITORY_URL` - The URL to the repo
* `DOMAIN_NAME` - Root Domain name - Should already have a valid R53 zone
