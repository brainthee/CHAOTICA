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
| API | Django REST Framework |
| Auth | DRF SessionAuthentication |
| Permissions | Custom DRF permission classes wrapping Guardian |

---

## Phase 0: Project Setup & API Foundation (6-8 weeks)

### 0a: Vue.js project scaffolding (1 week)

- [ ] Init Vue 3 project with Vite in `frontend/` directory
- [ ] Install Vue Router, Pinia, PrimeVue, Vee-Validate
- [ ] Configure Vite proxy to Django dev server for API calls
- [ ] Set up ESLint + TypeScript
- [ ] PrimeVue theme configuration — choose base theme, configure design tokens
- [ ] Set up directory structure (`stores/`, `composables/`, `components/`, `views/`)

### 0b: DRF API layer — core models (3-4 weeks)

Expand existing DRF setup (`app/jobtracker/views/api.py`, `app/jobtracker/serializers.py`) to full CRUD.

**For each model: read serializer (nested + computed fields), write serializer (with validation from forms.py), list serializer (lightweight for tables).**

- [ ] Job, Phase, TimeSlot serializers + ViewSets (core workflow)
- [ ] Client, Service, Framework serializers + ViewSets (job configuration)
- [ ] OrganisationalUnit, OrganisationalUnitMember serializers + ViewSets (org structure)
- [ ] User, UserSkill, UserQualification, UserJobLevel serializers + ViewSets (people)
- [ ] Note serializer + ViewSet (generic relation, attached to Jobs/Phases)
- [ ] Notification, NotificationSubscription serializers + ViewSets (alerts)
- [ ] Report, ReportField, ReportFilter serializers + ViewSets (reporting)
- [ ] LeaveRequest, Holiday serializers + ViewSets (availability)
- [ ] Migrate validation logic from `app/jobtracker/forms.py` (3,058 lines) to serializer validation
- [ ] API URL routing configuration

### 0c: DRF permissions & auth (2-3 weeks)

- [ ] DRF SessionAuthentication configuration (same domain, no JWT needed)
- [ ] Custom DRF permission classes wrapping Guardian's `get_objects_for_user()`
- [ ] `/api/me/` endpoint — current user + permission flags (replaces `{% if perms.* %}`)
- [ ] Queryset filtering in ViewSets based on user permissions
- [ ] CSRF handling via DRF SessionAuth
- [ ] Replicate permission logic from `app/jobtracker/mixins.py` (UnitPermissionRequiredMixin, JobPermissionRequiredMixin)

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

- [ ] API endpoint: `/api/dashboard/` returning aggregated stats (migrate logic from `app/dashboard/views.py` — 57+ context variables)
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
- [ ] FSM workflow transitions — `/api/jobs/{slug}/transition/` endpoints + UI buttons
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

- [ ] FullCalendar Vue 3 component (`@fullcalendar/vue3`) with resource timeline
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
- [ ] Real-time notification indicator (polling initially, WebSocket later if needed)
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
- [ ] Django handles only `/api/`, `/admin/`, `/oauth2/` routes
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
│   │   ├── serializers.py        # Full CRUD serializers
│   │   ├── views/api.py          # Full CRUD ViewSets
│   │   └── permissions.py        # DRF permission classes (Guardian wrapper)
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
| Existing API endpoints | 5 (read-only, DataTables-focused) |
| Guardian permission checks | 26 in views + 564 in templates |
| Vendor JS libraries | 40+ (FullCalendar, DataTables, ECharts, Gantt, Leaflet, TinyMCE) |
