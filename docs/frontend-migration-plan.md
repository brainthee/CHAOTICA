# Frontend Migration: Vue.js SPA (Full Rewrite)

## Overview

Migrate CHAOTICA from server-rendered Django templates (365 templates, jQuery, Bootstrap 5/Phoenix) to a Vue.js 3 SPA with Django REST Framework API backend.

### Goals
- **Faster UI** — single page load, then all interactions via API (no full page reloads)
- **Theme-swappable** — change UI themes without rewriting components (PrimeVue design tokens)
- **Disconnected frontend** — UI independent of Django backend

### Estimated Effort: 34-46 weeks

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend framework | Vue 3 (Composition API) |
| Build tool | Vite |
| Component library | PrimeVue (theme-swappable via design tokens) |
| Routing | Vue Router 4 |
| State management | Pinia |
| Form validation | Vee-Validate + Zod |
| HTTP client | Axios or native fetch |
| Charts | vue-echarts (ECharts wrapper) |
| Calendar | @fullcalendar/vue3 |
| Tables | PrimeVue DataTable |
| Rich text | TinyMCE Vue wrapper or TipTap |
| Maps | vue-leaflet |
| API | Django REST Framework, `/api/v1/` ([REST API (v1)](development/api_v1.md)) |
| Auth | Session (same-origin SPA) or OAuth2 + PKCE (separate origin) |
| Permissions | `jobtracker/policy.py` `PolicyContext`, surfaced as `capabilities` blocks |

---

## Phase 0: Project Setup & API Foundation (6-8 weeks)

### 0a: Vue.js project scaffolding (1 week)

- [ ] Init Vue 3 project with Vite in `frontend/` directory
- [ ] Install Vue Router, Pinia, PrimeVue, Vee-Validate
- [ ] Configure Vite proxy to Django dev server for API calls
- [ ] Set up ESLint + TypeScript
- [ ] PrimeVue theme configuration — choose base theme, configure design tokens
- [ ] Set up directory structure (`stores/`, `composables/`, `components/`, `views/`)

### 0b: API layer — reads ✅ done (2026-10), writes to do

The SPA builds on the versioned `/api/v1/`, not the legacy `/api/` DataTables
feeds, which are frozen and mostly removed.

**Done (read-only):**

- dashboard queues and stats, alarms, notifications;
- jobs and phases plus every tab (team, sales, support team, notes, activity,
  feedback, schedule), with `workflow` and `capabilities` blocks;
- the scheduler: windowed schedules, rows, history, deltas;
- clients, contacts, frameworks, users and profiles, org units;
- skills, the skill matrix, services (coverage and metrics), qualifications;
- search and ID jump.

Template views and the API share selectors (`jobtracker/selectors/`), so the
two cannot drift. The main UI already reads from v1 in several places: the
scheduler, the job and client lists, search and notifications.

**To do (writes):**

- [ ] Write endpoints, for each model, with validation moved from `forms.py` into shared services. Clients post workflow transitions **by name** (from the `workflow` block).
- [ ] Scheduler writes (create, move, delete slots; revert) over v1. Today they still use page endpoints plus the `ws/schedule/` socket.
- [ ] Reporting, notification subscriptions, leave requests.

### 0c: Permissions & auth ✅ done (2026-10)

- `PolicyContext` (`jobtracker/policy.py`) is the single permission facade:
  `can`, `scope` and `capabilities`, memoised per request. The SPA reads
  `capabilities` from `/api/v1/me/` and from each detail response, instead of
  re-implementing `{% if perms.* %}`.
- **Auth.** A same-origin SPA uses the session cookie plus CSRF. A SPA on
  another origin uses OAuth2 authorization code + PKCE, registered as a
  [Connected App](administration/connected_apps.md). Realtime uses `ws/me/`,
  with a single-use ticket from `/api/v1/realtime/ticket/` when the cookie
  isn't available.
- Middleware handles API callers properly:
  - maintenance and setup return JSON 503s;
  - times are in UTC;
  - audit records the right actor and impersonator;
  - throttling and CORS are restricted to registered origins.

---

## Phase 1: SPA Shell & Auth (2-3 weeks)

- [ ] Vue Router with route guards (redirect to login if unauthenticated)
- [ ] Login page (POST to Django auth endpoint / `/api/auth/login/`)
- [ ] App shell: top navbar, sidebar/dual navigation, breadcrumbs
- [ ] PrimeVue layout components (Menubar, Sidebar, Breadcrumb)
- [ ] Dark/light mode toggle (PrimeVue built-in theme switching)
- [ ] Global error handling (API errors → PrimeVue Toast notifications)
- [ ] Loading states / skeleton screens for perceived performance
- [ ] Base API client (Axios instance with session cookie + CSRF header)

---

## Phase 2: Dashboard (2-3 weeks)

- [x] API endpoints: `/api/v1/me/dashboard/` (queues + stats), `/api/v1/me/alarms/`, queue lists via `/jobs/?queue=` / `/phases/?queue=`
- [ ] Stats cards with vue-echarts
- [ ] Job/phase lists with status badges
- [ ] Permission-based tab/section visibility (from `/api/me/` permission flags)
- [ ] Quick-action buttons

---

## Phase 3: Core CRUD Pages (8-10 weeks)

### 3a: Clients (2 weeks)

- [ ] Client list — PrimeVue DataTable with server-side pagination, sorting, filtering
- [ ] Client detail page
- [ ] Client create/edit forms (PrimeVue form components + Vee-Validate)
- [ ] Account manager assignment UI
- [ ] Status badges

### 3b: Organisational Units (2 weeks)

- [ ] Unit list and detail views
- [ ] Member management (add/remove/roles)
- [ ] Permission-based action buttons

### 3c: Jobs (4-6 weeks) — largest module

- [ ] Job list with advanced filtering
- [ ] Job detail with tabbed sub-views (overview, phases, team, schedule, notes, history)
- [ ] Job create/edit forms
- [ ] FSM workflow transitions — a write endpoint taking the transition name; buttons render from the `workflow` block (already in v1)
- [ ] Team assignment modals (PrimeVue Dialog)
- [ ] Framework/billing code assignment
- [ ] Note CRUD (generic relation)
- [ ] Activity/history timeline

---

## Phase 4: Phases & Scheduling (6-8 weeks)

### 4a: Phase management (3-4 weeks)

- [ ] Phase list/detail within job context
- [ ] Phase CRUD forms (scoping, service selection)
- [ ] Phase workflow transitions (FSM)
- [ ] Delivery status tracking
- [ ] Scoping hours/days display

### 4b: Scheduler (3-4 weeks)

- [ ] Timeline component (the current UI uses vis-timeline, fed by `/api/v1/schedule/` + `/schedule/resources/`)
- [ ] TimeSlot CRUD via API
- [ ] Constraint validation UI:
  - [ ] Framework closed/over-allocated warnings
  - [ ] User availability checks (leave, existing bookings)
  - [ ] Qualification/skill checks
  - [ ] Phase over-scoped warnings
- [ ] Utilisation display
- [ ] Gantt view (evaluate Vue Gantt libraries vs DHTMLX Vue wrapper)
- [ ] Scheduler filter panel

---

## Phase 5: Supporting Features (6-8 weeks)

### 5a: Reporting (2-3 weeks)

- [ ] Report wizard (PrimeVue Stepper — multi-step form)
- [ ] Results display with data table
- [ ] Chart visualizations
- [ ] Export options (CSV, Excel, PDF)

### 5b: Notifications (1-2 weeks)

- [ ] Notification rules management
- [ ] Subscription preferences
- [ ] Real-time notification indicator (`ws/me/` pushes the unread count; already used by the current UI)
- [ ] Notification list/detail views

### 5c: User management (2-3 weeks)

- [ ] User profile and settings
- [ ] Skills and qualifications management
- [ ] Leave request management
- [ ] People manager views (team overview)

### 5d: Admin & misc (1 week)

- [ ] Settings pages
- [ ] Help/documentation integration
- [ ] Error pages (404, 403, 500)

---

## Phase 6: Integration, Testing & Cutover (4-6 weeks)

### 6a: Testing (2-3 weeks)

- [ ] Vue component tests (Vitest + Vue Test Utils)
- [ ] API integration tests (DRF test client)
- [ ] E2E tests for critical workflows (Playwright or Cypress)
- [ ] Permission matrix testing (all role combinations)

### 6b: Performance (1 week)

- [ ] Route-based code splitting (lazy-load each major section)
- [ ] API response caching (Pinia + stale-while-revalidate)
- [ ] Optimistic updates for common actions
- [ ] Bundle size analysis and optimization

### 6c: Cutover (1-2 weeks)

- [ ] Django serves built Vue SPA at all frontend routes
- [ ] Django handles only `/api/v1/`, `/o/` (OAuth2), `/oauth2/` (ADFS), `/ws/` and `/admin/` routes
- [ ] `TemplateView` serves `index.html` for all non-API routes (Vue Router handles client-side)
- [ ] Redirect old Django template URLs if bookmarked
- [ ] Remove Django template dependencies (crispy-forms, widget-tweaks, etc.)
- [ ] Update Docker/deployment configs for frontend build step
- [ ] Update documentation

---

## Theme Swappability

PrimeVue provides theme swapping without component code changes:

- **Design tokens** — colors, spacing, borders as CSS custom properties
- **Preset themes** — Aura, Lara, Nora built-in; community themes available
- **Theme designer** — visual tool to create custom themes
- **Runtime switching** — `PrimeVue.changeTheme()` without rebuild
- To swap themes: change PrimeVue preset or provide custom design tokens. Zero component changes.

---

## Directory Structure

```
CHAOTICA/
├── app/                          # Django backend (API only after migration)
│   ├── chaotica/settings.py      # Add DRF config, CORS, SPA serving
│   ├── jobtracker/
│   │   ├── api/v1/               # Versioned API (serializers/, views/, filters, fields)
│   │   ├── selectors/            # Query logic shared by templates and the API
│   │   ├── policy.py             # PolicyContext — permissions facade
│   │   └── workflow.py           # Job/phase transition table
│   └── ...
├── frontend/                     # Vue.js SPA
│   ├── src/
│   │   ├── main.js
│   │   ├── App.vue
│   │   ├── router/index.js
│   │   ├── stores/               # Pinia stores (auth, jobs, clients, etc.)
│   │   ├── composables/          # Shared logic (usePermissions, useApi, etc.)
│   │   ├── components/           # Reusable components (layout/, common/)
│   │   └── views/                # Page components (Dashboard, jobs/, clients/, scheduler/)
│   ├── vite.config.js
│   └── package.json
└── ...
```

---

## Current State Reference

| Metric | Current Value |
|--------|--------------|
| Django templates | 365 (153 partials, 23 modals) |
| Models requiring API | 69 across 6 apps |
| FK/M2M relationships | 66+ in jobtracker alone |
| Custom computed methods | 50+ (profit, utilisation, scheduling) |
| Form definitions | 3,484 lines, 48 form classes |
| View logic | 6,328 lines, 79 CBVs |
| API endpoints | `/api/v1/`: ~85 paths, read-mostly (see `docs/api/openapi-v1.yaml`) |
| Guardian permission checks | 26 in views + 564 in templates |
| Vendor JS libraries | 40+ (FullCalendar, DataTables, ECharts, Gantt, Leaflet, TinyMCE) |
