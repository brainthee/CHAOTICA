# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Support for defining initial table ordering via css class on `TableHeader` of `table.datatable`:
  - `default-sort` to mark the default sort column
  - `sort-desc` to set the default sort direction to descending

### Fixed
- Default table sorting by Delivery Date (Ascending / Soonest First) #83
