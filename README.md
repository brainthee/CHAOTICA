<p align="center"> <img src="https://raw.githubusercontent.com/brainthee/CHAOTICA/main/media/logo_nobg.png"/></p>

[![Project Status: Active – The project has reached a stable, usable state and is being actively developed.](https://www.repostatus.org/badges/latest/active.svg)](https://www.repostatus.org/#active)

CHAOTICA stands for: **C**entralised **H**ub for **A**ssigning **O**perational **T**asks, **I**nteractive **C**alendaring and **A**lerts. Thanks ChatGPT for the backronym!

It is a Django based engagement life-cycle management tool. Primarily geared to security testing teams.

<img src="https://raw.githubusercontent.com/brainthee/CHAOTICA/main/media/screenshots/dashboard.png"/>

(Planned) Features:

- Workflow tracking of engagements (jobs) from birth to death
- Email/Teams alerts on status changes of jobs/phases
- Full process driven conditionals on status changes (e.g. can't submit to delivered if QA not done. Can't submit to QA if report link field empty etc)
- Stats
- Scheduling functionality
- API for users to use
- Organisational Unit concepts. Allows groups/units to operate independently but allows 'overlords' oversight and stats across teams
- Team concepts - Allows grouping/membership of users (E.g. Client onboarding, Qualification approved people) scheduling/engagements can be enforced on member selection. 
- Skill tracking
- Service tracking with skills definable (e.g. service X must have skill Y)
- "other" schedule tracking. E.g. Annual Leave, Internal development, shadowing etc.

## Documentation

Latest documentation can be found at [https://docs.chaotica.app/en/latest/](https://docs.chaotica.app/en/latest/)

## Roadmap

In time, this will outline what should be expected for version 1 and what will be added later on.

- Combine all scheduling functionality in to the core scheduler (currently delivery is handled separately). This is dependant on figuring out a neat UI to handle delivery and non-delivery timeslots.

## Support

This project is maintained by @brainthee. Please understand that I can not provide individual support via email. I also believe that help is much more valuable if it’s shared publicly, so that more people can benefit from it. So please raise any problems on the project issue tracker.

## Installation

There are no released versions yet. Eventually you will be able to pull the latest image from DockerHub.

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## Authors and Acknowledgements

* Adrian Lewis (@brainthee)

Some contributions by @brainthee are graciously provided on behalf of Accenture.