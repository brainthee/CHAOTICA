# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Support for defining initial table ordering via css class on `TableHeader` of `table.datatable`:
  - `default-sort` to mark the default sort column
  - `sort-desc` to set the default sort direction to descending
- Easter egg: fake "web shell" honeypot at commonly-scanned URLs (`FAKE_HONEYPOT_ENABLED`, on by default). Looks vulnerable, is completely inert, and rickrolls on the second command.
- Easter egg: hidden "entropy meter" footer glyph (`ENTROPY_METER_ENABLED`, off by default) showing an operational chaos level scoped like the dashboard alarms, with a factor breakdown and recent late-delivery trend.

### Fixed
- Default table sorting by Delivery Date (Ascending / Soonest First) #83
- Rage Quit easter-egg game now targets the vis-timeline scheduler (`.vis-item`) instead of the removed FullCalendar (`.fc-event`), so it works again.
