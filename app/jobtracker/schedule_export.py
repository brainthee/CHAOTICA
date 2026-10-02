import io
import json
import math
from collections import defaultdict
from datetime import timedelta
from django.db.models import Q
from django.http import HttpResponse
from constance import config

from .enums import TimeSlotDeliveryRole

# CHAOTICA / Phoenix theme
PHX_PRIMARY = "#3874ff"
PHX_GRAY_100 = "#eff2f6"
PHX_GRAY_200 = "#e3e6ed"
PHX_BORDER = "#cbd0dd"
PHX_INK = "#141824"
PHX_SECONDARY = "#525b75"


def _next_day(d):
    return d + timedelta(days=1)


def _est_lines(text, width_chars):
    """Estimate how many wrapped lines a string needs at a given column width.

    Excel Online doesn't auto-fit wrapped rows (LibreOffice does), so we size
    rows ourselves from this estimate.
    """
    if not text:
        return 1
    total = 0
    for segment in str(text).split("\n"):
        total += max(1, math.ceil(len(segment) / max(1, width_chars)))
    return max(1, total)


# Row-height sizing (points). ~15pt per wrapped line, capped so a busy cell
# doesn't produce an enormous row.
_LINE_PT = 15
_MAX_ROW_PT = 75


def _row_height(max_lines):
    return min(_MAX_ROW_PT, max(_LINE_PT, max_lines * _LINE_PT))


# Grid date-column width (in characters) — kept in sync with the line estimate.
GRID_COL_WIDTH = 18
SUMMARY_COL_WIDTH = 16


def _fmt_date(d):
    return d.strftime("%d %b %Y") if d else ""


def _schedule_colours():
    """Live scheduler colours from Constance config (matches the on-screen scheduler)."""
    return {
        "SCHEDULE_COLOR_PHASE_CONFIRMED_AWAY": config.SCHEDULE_COLOR_PHASE_CONFIRMED_AWAY,
        "SCHEDULE_COLOR_PHASE_CONFIRMED": config.SCHEDULE_COLOR_PHASE_CONFIRMED,
        "SCHEDULE_COLOR_PHASE_AWAY": config.SCHEDULE_COLOR_PHASE_AWAY,
        "SCHEDULE_COLOR_PHASE": config.SCHEDULE_COLOR_PHASE,
        "SCHEDULE_COLOR_PROJECT": config.SCHEDULE_COLOR_PROJECT,
        "SCHEDULE_COLOR_INTERNAL": config.SCHEDULE_COLOR_INTERNAL,
    }


def phase_header_rows(phase):
    """Build (label, value) header rows describing a single phase."""
    job = phase.job
    return [
        ("Client", str(job.client) if job.client else ""),
        ("Job", "{}: {}".format(job.id, job.title)),
        ("Phase", "{}: {}".format(phase.get_id(), phase.title)),
        ("Service", str(phase.service) if phase.service else ""),
        ("Status", phase.get_status_display()),
        ("Start Date", _fmt_date(phase.start_date)),
        ("Delivery Date", _fmt_date(phase.delivery_date)),
        ("Project Lead", phase.project_lead.get_full_name() if phase.project_lead else ""),
        ("Report Author", phase.report_author.get_full_name() if phase.report_author else ""),
        ("Scoped Days", phase.get_total_scoped_days()),
        ("Number of Reports", phase.number_of_reports),
        ("Testing Onsite", "Yes" if phase.is_testing_onsite else "No"),
    ]


def job_header_rows(job):
    """Build (label, value) header rows describing a whole job."""
    phases = list(job.phases.all())
    starts = [p.start_date for p in phases if p.start_date]
    ends = [p.delivery_date for p in phases if p.delivery_date]
    return [
        ("Client", str(job.client) if job.client else ""),
        ("Job", "{}: {}".format(job.id, job.title)),
        ("Status", job.get_status_display()),
        ("Account Manager", job.account_manager.get_full_name() if job.account_manager else ""),
        ("Framework", str(job.associated_framework) if job.associated_framework else ""),
        ("Phases", str(len(phases))),
        ("Earliest Start", _fmt_date(min(starts)) if starts else ""),
        ("Latest Delivery", _fmt_date(max(ends)) if ends else ""),
    ]


def build_team_xlsx(job, phase=None):
    """Build a themed single-sheet Team allocation export for a job or phase.

    One row per team member: assigned roles, date range, a day column per
    delivery-role capacity, plus total/confirmed/tentative days. Consumes
    ``get_user_schedule_breakdown`` so it always matches the on-screen Team tab.
    """
    import xlsxwriter
    from .views.scheduler import (
        get_user_schedule_breakdown,
        get_user_phase_breakdown,
        TEAM_CAPACITY_ROLES,
    )

    user_breakdown = get_user_schedule_breakdown(job, phase)
    # Job-level export expands each member into per-phase sub-rows; the per-phase
    # roles (Lead / Author / …) sit against those rows, so the member row keeps
    # only the job-wide roles (AM / Deputy AM / Scoping).
    if phase is None:
        from .utils import job_assigned_role_map
        phase_breakdown = get_user_phase_breakdown(job)
        job_roles = job_assigned_role_map(job)
        for entry in user_breakdown:
            entry["assigned_roles"] = job_roles.get(entry["user"].pk, [])
    else:
        phase_breakdown = {}
    hours_in_day = phase.get_hours_in_day() if phase else job.get_hours_in_day()

    if phase:
        header_rows = phase_header_rows(phase)
        title = "Team — {}: {}".format(phase.get_id(), phase.title)
        filename = "team-{}".format(phase.slug)
    else:
        header_rows = job_header_rows(job)
        title = "Team — {}: {}".format(job.id, job.title)
        filename = "team-{}".format(job.slug)

    def _days(hours):
        return round(float(hours) / float(hours_in_day), 2) if hours_in_day else 0.0

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"remove_timezone": True})

    title_fmt = workbook.add_format({
        "bold": True, "font_size": 16, "font_color": "#FFFFFF",
        "bg_color": PHX_PRIMARY, "valign": "vcenter", "indent": 1,
    })
    hdr_label_fmt = workbook.add_format({
        "bold": True, "bg_color": PHX_GRAY_100, "font_color": PHX_INK,
        "border": 1, "border_color": PHX_BORDER, "valign": "vcenter",
    })
    hdr_value_fmt = workbook.add_format({
        "border": 1, "border_color": PHX_BORDER, "valign": "vcenter", "text_wrap": True,
    })
    col_hdr_fmt = workbook.add_format({
        "bold": True, "bg_color": PHX_PRIMARY, "font_color": "#FFFFFF",
        "border": 1, "border_color": PHX_BORDER,
        "align": "center", "valign": "vcenter", "text_wrap": True,
    })
    member_fmt = workbook.add_format({
        "bold": True, "bg_color": PHX_GRAY_100, "font_color": PHX_INK,
        "border": 1, "border_color": PHX_BORDER, "valign": "vcenter",
    })
    cell_fmt = workbook.add_format({
        "border": 1, "border_color": PHX_BORDER, "valign": "vcenter", "text_wrap": True,
    })
    num_fmt = workbook.add_format({
        "border": 1, "border_color": PHX_BORDER, "valign": "vcenter", "align": "center",
    })
    total_fmt = workbook.add_format({
        "bold": True, "border": 1, "border_color": PHX_BORDER,
        "valign": "vcenter", "align": "center", "bg_color": PHX_GRAY_100,
    })
    phase_label_fmt = workbook.add_format({
        "italic": True, "font_color": PHX_SECONDARY, "indent": 2,
        "border": 1, "border_color": PHX_BORDER, "valign": "vcenter", "text_wrap": True,
    })
    phase_num_fmt = workbook.add_format({
        "font_color": PHX_SECONDARY, "border": 1, "border_color": PHX_BORDER,
        "valign": "vcenter", "align": "center",
    })

    ws = workbook.add_worksheet("Team")
    ws.hide_gridlines(2)

    r = 0
    last_col = 4 + len(TEAM_CAPACITY_ROLES) + 2  # member..end + capacities + total/conf/tent
    ws.merge_range(r, 0, r, last_col, title, title_fmt)
    ws.set_row(r, 26)
    r += 2

    for label, value in header_rows:
        ws.write(r, 0, label, hdr_label_fmt)
        ws.merge_range(r, 1, r, last_col, value, hdr_value_fmt)
        r += 1
    r += 1

    # Table header
    columns = ["Team Member", "Assigned Roles", "Start", "End"]
    columns += [label for _id, label in TEAM_CAPACITY_ROLES]
    columns += ["Total Days", "Confirmed Days", "Tentative Days"]
    header_row = r
    for col, name in enumerate(columns):
        ws.write(header_row, col, name, col_hdr_fmt)
    ws.set_column(0, 0, 24)
    ws.set_column(1, 1, 26)
    ws.set_column(2, 3, 13)
    ws.set_column(4, last_col, SUMMARY_COL_WIDTH)
    ws.freeze_panes(header_row + 1, 0)
    r = header_row + 1

    capacity_ids = [role_id for role_id, _label in TEAM_CAPACITY_ROLES]
    role_names = dict(TimeSlotDeliveryRole.CHOICES)

    for entry in user_breakdown:
        by_name = {role["role_name"]: role for role in entry.get("roles", [])}
        ws.write(r, 0, entry["user"].get_full_name(), member_fmt)
        ws.write(r, 1, ", ".join(entry.get("assigned_roles", [])), cell_fmt)
        ws.write(r, 2, _fmt_date(entry["start"].date()) if entry.get("start") else "", num_fmt)
        ws.write(r, 3, _fmt_date(entry["end"].date()) if entry.get("end") else "", num_fmt)
        col = 4
        for role_id in capacity_ids:
            cell = by_name.get(role_names.get(role_id))
            ws.write(r, col, float(cell["days"]) if cell else 0.0, num_fmt)
            col += 1
        ws.write(r, col, float(entry["total_days"]), total_fmt)
        ws.write(r, col + 1, _days(entry.get("total_confirmed", 0)), num_fmt)
        ws.write(r, col + 2, _days(entry.get("total_tentative", 0)), num_fmt)
        max_lines = _est_lines(", ".join(entry.get("assigned_roles", [])), 26)
        ws.set_row(r, _row_height(max_lines))
        r += 1

        # Per-phase sub-rows (job-level export only).
        for prow in phase_breakdown.get(entry["user"].pk, []):
            prow_by_name = {role["role_name"]: role for role in prow.get("roles", [])}
            phase = prow["phase"]
            ws.write(r, 0, "{}: {}".format(phase.get_id(), phase.title), phase_label_fmt)
            ws.write(r, 1, ", ".join(prow.get("assigned_roles", [])), phase_num_fmt)
            ws.write(r, 2, "", phase_num_fmt)
            ws.write(r, 3, "", phase_num_fmt)
            col = 4
            for role_id in capacity_ids:
                cell = prow_by_name.get(role_names.get(role_id))
                ws.write(r, col, float(cell["days"]) if cell else 0.0, phase_num_fmt)
                col += 1
            ws.write(r, col, float(prow["total_days"]), phase_num_fmt)
            ws.write(r, col + 1, _days(prow.get("total_confirmed", 0)), phase_num_fmt)
            ws.write(r, col + 2, _days(prow.get("total_tentative", 0)), phase_num_fmt)
            ws.set_row(r, _row_height(_est_lines(phase.title, 24)))
            r += 1

    workbook.close()
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="{}.xlsx"'.format(filename)
    return response


def build_schedule_xlsx(timeslots, filename, title=None, header_rows=None):
    """
    Build a themed three-sheet XLSX schedule export.

    "Overview"  a client-ready cover sheet: title, key stats and a colour key.
    "Schedule"  a grid of resources (rows) x dates (columns). Booked cells carry
                the phase + delivery type in the same colours as the on-screen
                scheduler; days a resource is committed elsewhere (other work,
                leave, internal) are marked Unavailable so gaps read as free.
    "Summary"   one row per phase with the full hours breakdown and team.

    ``title``       optional heading shown on the Overview sheet.
    ``header_rows`` optional list of (label, value) tuples shown as key stats.
    """
    import xlsxwriter
    from .models import TimeSlot, OrganisationalUnitMember
    from chaotica_utils.models import Holiday

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"remove_timezone": True})
    colours = _schedule_colours()

    # --- Shared formats ---
    title_fmt = workbook.add_format({
        "bold": True, "font_size": 16, "font_color": "#FFFFFF",
        "bg_color": PHX_PRIMARY, "valign": "vcenter", "indent": 1,
    })
    section_fmt = workbook.add_format({
        "bold": True, "font_size": 11, "font_color": PHX_PRIMARY, "valign": "vcenter",
    })
    hdr_label_fmt = workbook.add_format({
        "bold": True, "bg_color": PHX_GRAY_100, "font_color": PHX_INK,
        "border": 1, "border_color": PHX_BORDER, "valign": "vcenter",
    })
    hdr_value_fmt = workbook.add_format({
        "border": 1, "border_color": PHX_BORDER, "valign": "vcenter", "text_wrap": True,
    })
    grid_hdr_fmt = workbook.add_format({
        "bold": True, "bg_color": PHX_PRIMARY, "font_color": "#FFFFFF",
        "border": 1, "border_color": PHX_BORDER,
        "align": "center", "valign": "vcenter", "text_wrap": True,
    })
    date_fmt = workbook.add_format({
        "bold": True, "bg_color": PHX_PRIMARY, "font_color": "#FFFFFF",
        "border": 1, "border_color": PHX_BORDER, "align": "center", "num_format": "ddd dd/mm/yy",
    })
    weekend_date_fmt = workbook.add_format({
        "bold": True, "bg_color": "#7ba0ff", "font_color": "#FFFFFF",
        "border": 1, "border_color": PHX_BORDER, "align": "center", "num_format": "ddd dd/mm/yy",
    })
    resource_fmt = workbook.add_format({
        "bold": True, "bg_color": PHX_GRAY_100, "font_color": PHX_INK,
        "border": 1, "border_color": PHX_BORDER, "valign": "vcenter",
    })
    empty_fmt = workbook.add_format({"border": 1, "border_color": PHX_BORDER})
    weekend_empty_fmt = workbook.add_format({
        "border": 1, "border_color": PHX_BORDER, "bg_color": "#eef2fb",
    })
    unavail_fmt = workbook.add_format({
        "border": 1, "border_color": PHX_BORDER, "bg_color": PHX_GRAY_200,
        "font_color": PHX_SECONDARY, "italic": True,
        "align": "center", "valign": "vcenter", "text_wrap": True,
    })
    summary_header_fmt = workbook.add_format({
        "bold": True, "bg_color": PHX_PRIMARY, "font_color": "#FFFFFF",
        "border": 1, "border_color": PHX_BORDER, "align": "center", "text_wrap": True,
    })
    summary_cell_fmt = workbook.add_format({
        "border": 1, "border_color": PHX_BORDER, "text_wrap": True,
        "align": "center", "valign": "vcenter",
    })

    # Cache of coloured booked-cell formats keyed by (bg, fg)
    booked_formats = {}

    def booked_fmt(bg, fg):
        key = (bg, fg)
        if key not in booked_formats:
            booked_formats[key] = workbook.add_format({
                "border": 1, "border_color": PHX_BORDER, "text_wrap": True,
                "align": "center", "valign": "vcenter",
                "bg_color": bg, "font_color": "#FFFFFF" if fg == "white" else "#000000",
            })
        return booked_formats[key]

    # --- Build data structures ---
    slots_list = list(timeslots.select_related("user", "phase", "phase__service", "phase__job"))
    exported_pks = {s.pk for s in slots_list}

    users = {}
    min_date = None
    max_date = None
    for slot in slots_list:
        if slot.user:
            users[slot.user.pk] = slot.user
        start_d = slot.start.date()
        end_d = slot.end.date()
        if min_date is None or start_d < min_date:
            min_date = start_d
        if max_date is None or end_d > max_date:
            max_date = end_d

    # Continuous range so days with no bookings still appear as columns.
    sorted_dates = []
    if min_date and max_date:
        d = min_date
        while d <= max_date:
            sorted_dates.append(d)
            d = _next_day(d)
    sorted_users = sorted(users.values(), key=lambda u: (u.last_name, u.first_name))

    # Booked cells: (user_pk, date) -> label, and -> (bg, fg)
    cell_map = defaultdict(str)
    cell_colour = {}
    for slot in slots_list:
        if not slot.user or not slot.phase:
            continue
        role = slot.get_deliveryRole_display()
        phase_label = "{}: {}".format(slot.phase.get_id(), slot.phase.title[:24])
        label = "{} ({})".format(phase_label, role) if role and role != "None" else phase_label
        bg = slot.get_schedule_slot_colour(schedule_colours=colours)
        fg = slot.get_schedule_slot_text_colour(bg)
        d = slot.start.date()
        end_d = slot.end.date()
        while d <= end_d:
            key = (slot.user.pk, d)
            if cell_map[key] and label not in cell_map[key]:
                cell_map[key] += " / " + label
            elif not cell_map[key]:
                cell_map[key] = label
                cell_colour[key] = (bg, fg)
            d = _next_day(d)

    # Unavailable days: any day a resource can't take new client work — their
    # non-working days (weekends/bank holidays per the org calendar) plus days
    # they're already committed elsewhere. Always generic ("Unavailable") so the
    # export never names other work/leave and behaves the same everywhere.
    busy_days = set()
    user_pks = list(users.keys())
    if sorted_users and sorted_dates:
        # Per-user working weekdays (org unit calendar, else the org default).
        default_working = set(json.loads(config.DEFAULT_WORKING_DAYS))
        user_working = {}
        memberships = (
            OrganisationalUnitMember.objects.filter(member_id__in=user_pks)
            .select_related("unit")
            .order_by("member_id", "id")
        )
        for m in memberships:
            if m.member_id not in user_working and m.unit and m.unit.businessHours_days:
                user_working[m.member_id] = set(m.unit.businessHours_days)
        for pk in user_pks:
            user_working.setdefault(pk, set(default_working))

        # Per-user bank holidays (their country + global) across the range.
        countries = {str(u.country) for u in sorted_users if u.country}
        holidays = Holiday.objects.filter(
            Q(country__in=countries) | Q(country__isnull=True),
            date__range=(min_date, max_date),
        ).values("country", "date")
        holidays_by_country = defaultdict(set)
        global_holidays = set()
        for h in holidays:
            if not h["country"]:
                global_holidays.add(h["date"])
            else:
                holidays_by_country[str(h["country"])].add(h["date"])
        user_holidays = {}
        for u in sorted_users:
            hs = set(holidays_by_country.get(str(u.country), set())) if u.country else set()
            hs |= global_holidays
            user_holidays[u.pk] = hs

        # Non-working days (consistent for everyone).
        for u in sorted_users:
            working = user_working.get(u.pk, default_working)
            hols = user_holidays.get(u.pk, set())
            for d in sorted_dates:
                key = (u.pk, d)
                if key in cell_map:
                    continue
                if (d.weekday() + 1) not in working or d in hols:
                    busy_days.add(key)

        # Days committed to other work.
        other_slots = (
            TimeSlot.objects.filter(
                user_id__in=user_pks,
                start__date__lte=max_date,
                end__date__gte=min_date,
            )
            .exclude(pk__in=exported_pks)
        )
        for slot in other_slots:
            d = max(slot.start.date(), min_date)
            end_d = min(slot.end.date(), max_date)
            while d <= end_d:
                key = (slot.user_id, d)
                if key not in cell_map:
                    busy_days.add(key)
                d = _next_day(d)

    # =========================================================
    # Sheet 1: Overview (cover)
    # =========================================================
    ov = workbook.add_worksheet("Overview")
    ov.hide_gridlines(2)
    ov.set_column(0, 0, 20)
    ov.set_column(1, 1, 36)
    ov.set_column(2, 2, 3)

    r = 0
    ov.merge_range(r, 0, r, 3, title or "Schedule", title_fmt)
    ov.set_row(r, 26)
    r += 2

    if header_rows:
        for label, value in header_rows:
            ov.write(r, 0, label, hdr_label_fmt)
            ov.merge_range(r, 1, r, 3, value, hdr_value_fmt)
            r += 1
        r += 1

    # Colour key (mirrors the on-screen scheduler legend)
    ov.write(r, 0, "Key", section_fmt)
    r += 1
    legend = [
        (colours["SCHEDULE_COLOR_PHASE_CONFIRMED"], "Confirmed delivery"),
        (colours["SCHEDULE_COLOR_PHASE"], "Tentative delivery"),
        (colours["SCHEDULE_COLOR_PHASE_CONFIRMED_AWAY"], "Confirmed — onsite"),
        (colours["SCHEDULE_COLOR_PHASE_AWAY"], "Tentative — onsite"),
        (PHX_GRAY_200, "Unavailable (non-working or committed)"),
        (None, "Blank — available"),
    ]
    label_fmt = workbook.add_format({"valign": "vcenter", "font_color": PHX_INK})
    for swatch, desc in legend:
        if swatch:
            sw_fmt = workbook.add_format({
                "bg_color": swatch, "border": 1, "border_color": PHX_BORDER,
            })
        else:
            sw_fmt = workbook.add_format({"border": 1, "border_color": PHX_BORDER})
        ov.write_blank(r, 0, None, sw_fmt)
        ov.write(r, 1, desc, label_fmt)
        r += 1

    # =========================================================
    # Sheet 2: Schedule (grid)
    # =========================================================
    ws = workbook.add_worksheet("Schedule")
    ws.set_column(0, 0, 24)
    ws.write(0, 0, "Resource", grid_hdr_fmt)
    for col, d in enumerate(sorted_dates, start=1):
        fmt = weekend_date_fmt if d.weekday() >= 5 else date_fmt
        ws.write_datetime(0, col, d, fmt)
        ws.set_column(col, col, GRID_COL_WIDTH)
    ws.freeze_panes(1, 1)

    for i, user in enumerate(sorted_users):
        row = 1 + i
        ws.write(row, 0, user.get_full_name(), resource_fmt)
        max_lines = 1
        for col, d in enumerate(sorted_dates, start=1):
            key = (user.pk, d)
            if key in cell_map:
                bg, fg = cell_colour.get(key, (PHX_PRIMARY, "white"))
                ws.write(row, col, cell_map[key], booked_fmt(bg, fg))
                max_lines = max(max_lines, _est_lines(cell_map[key], GRID_COL_WIDTH))
            elif key in busy_days:
                ws.write(row, col, "Unavailable", unavail_fmt)
            else:
                fmt = weekend_empty_fmt if d.weekday() >= 5 else empty_fmt
                ws.write_blank(row, col, None, fmt)
        ws.set_row(row, _row_height(max_lines))

    # =========================================================
    # Sheet 3: Summary
    # =========================================================
    ws2 = workbook.add_worksheet("Phase Summary")
    ws2.freeze_panes(1, 0)
    summary_cols = [
        "Phase ID", "Job", "Phase", "Status", "Service",
        "Start Date", "Delivery Date",
        "Delivery Days", "Reporting Days", "Mgmt Days", "QA Days",
        "Oversight Days", "Debrief Days", "Contingency Days", "Other Days",
        "Lead", "Author",
    ]
    for col, name in enumerate(summary_cols):
        ws2.write(0, col, name, summary_header_fmt)
        ws2.set_column(col, col, SUMMARY_COL_WIDTH)

    phases_seen = {}
    for slot in slots_list:
        if slot.phase and slot.phase.pk not in phases_seen:
            phases_seen[slot.phase.pk] = slot.phase

    def _days(phase, role):
        return float(phase.get_total_scoped_days_by_type(role))

    for row, phase in enumerate(phases_seen.values(), start=1):
        job = phase.job
        values = [
            phase.get_id(),
            "{}: {}".format(job.id, job.title) if job else "",
            str(phase.title),
            phase.get_status_display(),
            str(phase.service) if phase.service else "",
            _fmt_date(phase.start_date),
            _fmt_date(phase.delivery_date),
            _days(phase, TimeSlotDeliveryRole.DELIVERY),
            _days(phase, TimeSlotDeliveryRole.REPORTING),
            _days(phase, TimeSlotDeliveryRole.MANAGEMENT),
            _days(phase, TimeSlotDeliveryRole.QA),
            _days(phase, TimeSlotDeliveryRole.OVERSIGHT),
            _days(phase, TimeSlotDeliveryRole.DEBRIEF),
            _days(phase, TimeSlotDeliveryRole.CONTINGENCY),
            _days(phase, TimeSlotDeliveryRole.OTHER),
            phase.project_lead.get_full_name() if phase.project_lead else "",
            phase.report_author.get_full_name() if phase.report_author else "",
        ]
        for col, value in enumerate(values):
            ws2.write(row, col, value, summary_cell_fmt)
        # Size the row for the widest wrapping text column (job / phase / service).
        max_lines = max(
            _est_lines(values[1], SUMMARY_COL_WIDTH),
            _est_lines(phase.title, SUMMARY_COL_WIDTH),
            _est_lines(str(phase.service) if phase.service else "", SUMMARY_COL_WIDTH),
        )
        ws2.set_row(row, _row_height(max_lines))

    workbook.close()
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="{}.xlsx"'.format(filename)
    return response


# The global scheduler export spans the whole loaded buffer (3x the visible
# window), so a 1-year zoom asks for ~3 years. Cap it so a hand-crafted URL
# can't request an unbounded grid.
SCHEDULER_EXPORT_MAX_DAYS = 1200


def build_scheduler_xlsx(
    members, users, dataset, start_date, end_date,
    filename, title=None, header_rows=None, selected_phases=None,
):
    """Build an internal XLSX of the global scheduler's current view.

    Unlike :func:`build_schedule_xlsx` (client-facing: other work masked as
    "Unavailable"), this mirrors what the viewer sees on screen — every filtered
    resource (including those with nothing booked), every slot type with its
    real title and scheduler colour, holidays and comments.

    ``members``  ordered resource rows from ``scheduler_member_rows``.
    ``users``    ``{pk: User}`` for those rows.
    ``dataset``  the ``collect_schedule_slots`` result for the window.
    ``selected_phases`` jobs/phases picked in the filter; slots outside them
                 are muted, matching the on-screen background styling.

    Sheets: "Overview" (filters + key), "Schedule" (resources x dates grid),
    "Bookings" (one row per slot) and "Resources" (availability/utilisation).
    """
    import xlsxwriter
    from django.utils import timezone
    from .models import OrganisationalUnitMember

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"remove_timezone": True})
    colours = _schedule_colours()
    selected_phases = selected_phases or []

    title_fmt = workbook.add_format({
        "bold": True, "font_size": 16, "font_color": "#FFFFFF",
        "bg_color": PHX_PRIMARY, "valign": "vcenter", "indent": 1,
    })
    section_fmt = workbook.add_format({
        "bold": True, "font_size": 11, "font_color": PHX_PRIMARY, "valign": "vcenter",
    })
    hdr_label_fmt = workbook.add_format({
        "bold": True, "bg_color": PHX_GRAY_100, "font_color": PHX_INK,
        "border": 1, "border_color": PHX_BORDER, "valign": "vcenter",
    })
    hdr_value_fmt = workbook.add_format({
        "border": 1, "border_color": PHX_BORDER, "valign": "vcenter", "text_wrap": True,
    })
    grid_hdr_fmt = workbook.add_format({
        "bold": True, "bg_color": PHX_PRIMARY, "font_color": "#FFFFFF",
        "border": 1, "border_color": PHX_BORDER,
        "align": "center", "valign": "vcenter", "text_wrap": True,
    })
    date_fmt = workbook.add_format({
        "bold": True, "bg_color": PHX_PRIMARY, "font_color": "#FFFFFF",
        "border": 1, "border_color": PHX_BORDER, "align": "center", "num_format": "ddd dd/mm/yy",
    })
    weekend_date_fmt = workbook.add_format({
        "bold": True, "bg_color": "#7ba0ff", "font_color": "#FFFFFF",
        "border": 1, "border_color": PHX_BORDER, "align": "center", "num_format": "ddd dd/mm/yy",
    })
    resource_fmt = workbook.add_format({
        "bold": True, "bg_color": PHX_GRAY_100, "font_color": PHX_INK,
        "border": 1, "border_color": PHX_BORDER, "valign": "vcenter",
    })
    resource_meta_fmt = workbook.add_format({
        "bg_color": PHX_GRAY_100, "font_color": PHX_SECONDARY,
        "border": 1, "border_color": PHX_BORDER, "valign": "vcenter",
    })
    pct_fmt = workbook.add_format({
        "bg_color": PHX_GRAY_100, "border": 1, "border_color": PHX_BORDER,
        "valign": "vcenter", "align": "center", "num_format": "0%",
    })
    empty_fmt = workbook.add_format({"border": 1, "border_color": PHX_BORDER})
    nonworking_fmt = workbook.add_format({
        "border": 1, "border_color": PHX_BORDER, "bg_color": "#eef2fb",
    })
    holiday_fmt = workbook.add_format({
        "border": 1, "border_color": PHX_BORDER, "bg_color": PHX_GRAY_200,
        "font_color": PHX_SECONDARY, "italic": True,
        "align": "center", "valign": "vcenter", "text_wrap": True,
    })
    muted_fmt = workbook.add_format({
        "border": 1, "border_color": PHX_BORDER, "bg_color": PHX_GRAY_100,
        "font_color": PHX_SECONDARY, "align": "center", "valign": "vcenter",
        "text_wrap": True,
    })
    list_hdr_fmt = workbook.add_format({
        "bold": True, "bg_color": PHX_PRIMARY, "font_color": "#FFFFFF",
        "border": 1, "border_color": PHX_BORDER, "text_wrap": True,
    })
    list_cell_fmt = workbook.add_format({
        "border": 1, "border_color": PHX_BORDER, "valign": "vcenter", "text_wrap": True,
    })
    list_dt_fmt = workbook.add_format({
        "border": 1, "border_color": PHX_BORDER, "valign": "vcenter",
        "num_format": "ddd dd/mm/yy hh:mm",
    })
    list_pct_fmt = workbook.add_format({
        "border": 1, "border_color": PHX_BORDER, "valign": "vcenter",
        "align": "center", "num_format": "0%",
    })

    # Booked-cell formats keyed by (bg, fg, tentative). Tentative work gets a
    # dashed border, echoing the on-screen dashed "ghost" styling.
    booked_formats = {}

    def booked_fmt(bg, fg, tentative):
        key = (bg, fg, tentative)
        if key not in booked_formats:
            booked_formats[key] = workbook.add_format({
                "border": 3 if tentative else 1,
                "border_color": PHX_INK if tentative else PHX_BORDER,
                "text_wrap": True, "align": "center", "valign": "vcenter",
                "bg_color": bg, "font_color": "#FFFFFF" if fg == "white" else "#000000",
            })
        return booked_formats[key]

    # Continuous run of dates across the window.
    sorted_dates = []
    d = start_date
    while d <= end_date:
        sorted_dates.append(d)
        d = _next_day(d)

    # Working weekdays per user (first org membership, else the org default) —
    # the same rule the scheduler's availability shading uses.
    default_working = set(json.loads(config.DEFAULT_WORKING_DAYS))
    user_working = {}
    for m in (
        OrganisationalUnitMember.objects.filter(member_id__in=list(users))
        .select_related("unit")
        .order_by("member_id", "pk")
    ):
        if m.member_id not in user_working and m.unit and m.unit.businessHours_days:
            user_working[m.member_id] = set(m.unit.businessHours_days)

    # Holidays per user: their country's plus global (country-less) ones.
    holidays_by_country = defaultdict(dict)
    global_holidays = {}
    for hol in dataset["holidays"]:
        if hol.country:
            holidays_by_country[str(hol.country)][hol.date] = str(hol)
        else:
            global_holidays[hol.date] = str(hol)

    def user_holidays(user):
        hols = dict(global_holidays)
        if user.country:
            hols.update(holidays_by_country.get(str(user.country), {}))
        return hols

    def is_muted(slot):
        if not selected_phases:
            return False
        phase = slot.phase_or_none if slot.is_delivery() else None
        return bool(phase) and phase not in selected_phases and phase.job not in selected_phases

    # Booked cells: (user_pk, date) -> [labels], first slot decides the colour.
    slots = [s for s in dataset["timeslots"] if s.user_id in users]
    cell_labels = defaultdict(list)
    cell_style = {}
    for slot in slots:
        label = slot.get_schedule_title()
        if slot.is_delivery() and slot.deliveryRole != TimeSlotDeliveryRole.NA:
            label = "{} [{}]".format(label, slot.get_deliveryRole_display())
        bg = slot.get_schedule_slot_colour(schedule_colours=colours)
        style = (
            "muted" if is_muted(slot)
            else (bg, slot.get_schedule_slot_text_colour(bg), not slot.is_confirmed())
        )
        day = max(timezone.localtime(slot.start).date(), start_date)
        last = min(timezone.localtime(slot.end).date(), end_date)
        while day <= last:
            key = (slot.user_id, day)
            if label not in cell_labels[key]:
                cell_labels[key].append(label)
            cell_style.setdefault(key, style)
            day = _next_day(day)

    # Comments become Excel cell notes on each day they cover.
    cell_notes = defaultdict(list)
    for comment in dataset["comments"]:
        if comment.user_id not in users:
            continue
        day = max(timezone.localtime(comment.start).date(), start_date)
        last = min(timezone.localtime(comment.end).date(), end_date)
        while day <= last:
            cell_notes[(comment.user_id, day)].append(comment.comment)
            day = _next_day(day)

    # =========================================================
    # Sheet 1: Overview
    # =========================================================
    ov = workbook.add_worksheet("Overview")
    ov.hide_gridlines(2)
    ov.set_column(0, 0, 22)
    ov.set_column(1, 1, 60)

    r = 0
    ov.merge_range(r, 0, r, 1, title or "Schedule", title_fmt)
    ov.set_row(r, 26)
    r += 2
    for label, value in header_rows or []:
        ov.write(r, 0, label, hdr_label_fmt)
        ov.write(r, 1, value, hdr_value_fmt)
        ov.set_row(r, _row_height(_est_lines(value, 60)))
        r += 1
    r += 1

    ov.write(r, 0, "Key", section_fmt)
    r += 1
    legend = [
        (colours["SCHEDULE_COLOR_PHASE_CONFIRMED"], "Confirmed delivery"),
        (colours["SCHEDULE_COLOR_PHASE"], "Tentative delivery (dashed border)"),
        (colours["SCHEDULE_COLOR_PHASE_CONFIRMED_AWAY"], "Confirmed — onsite"),
        (colours["SCHEDULE_COLOR_PHASE_AWAY"], "Tentative — onsite"),
        (colours["SCHEDULE_COLOR_PROJECT"], "Internal project"),
        (colours["SCHEDULE_COLOR_INTERNAL"], "Internal / leave / other"),
        (PHX_GRAY_100, "Outside the filtered jobs/phases"),
        (PHX_GRAY_200, "Public holiday"),
        ("#eef2fb", "Non-working day"),
        (None, "Blank — available"),
    ]
    label_fmt = workbook.add_format({"valign": "vcenter", "font_color": PHX_INK})
    for swatch, desc in legend:
        sw = {"border": 1, "border_color": PHX_BORDER}
        if swatch:
            sw["bg_color"] = swatch
        ov.write_blank(r, 0, None, workbook.add_format(sw))
        ov.write(r, 1, desc, label_fmt)
        r += 1
    note_fmt = workbook.add_format({"italic": True, "font_color": PHX_SECONDARY})
    ov.write(r + 1, 0, "Comments are attached as cell notes on the Schedule sheet.", note_fmt)

    # =========================================================
    # Sheet 2: Schedule (grid)
    # =========================================================
    ws = workbook.add_worksheet("Schedule")
    meta_cols = ["Resource", "Org Unit", "Job Level", "Availability", "Utilisation"]
    first_date_col = len(meta_cols)
    for col, name in enumerate(meta_cols):
        ws.write(0, col, name, grid_hdr_fmt)
    ws.set_column(0, 0, 24)
    ws.set_column(1, 2, 16)
    ws.set_column(3, 4, 11)
    for i, day in enumerate(sorted_dates):
        col = first_date_col + i
        ws.write_datetime(0, col, day, weekend_date_fmt if day.weekday() >= 5 else date_fmt)
        ws.set_column(col, col, GRID_COL_WIDTH)
    ws.freeze_panes(1, first_date_col)

    for row, member in enumerate(members, start=1):
        user = users[member["id"]]
        ws.write(row, 0, member["title"], resource_fmt)
        ws.write(row, 1, member.get("org_unit", ""), resource_meta_fmt)
        ws.write(row, 2, member.get("job_level", ""), resource_meta_fmt)
        ws.write(row, 3, (member.get("availability") or 0) / 100.0, pct_fmt)
        ws.write(row, 4, (member.get("util") or 0) / 100.0, pct_fmt)
        working = user_working.get(user.pk, default_working)
        hols = user_holidays(user)
        max_lines = 1
        for i, day in enumerate(sorted_dates):
            col = first_date_col + i
            key = (user.pk, day)
            if key in cell_labels:
                text = " / ".join(cell_labels[key])
                style = cell_style[key]
                fmt = muted_fmt if style == "muted" else booked_fmt(*style)
                ws.write(row, col, text, fmt)
                max_lines = max(max_lines, _est_lines(text, GRID_COL_WIDTH))
            elif day in hols:
                ws.write(row, col, hols[day], holiday_fmt)
            elif (day.weekday() + 1) not in working:
                ws.write_blank(row, col, None, nonworking_fmt)
            else:
                ws.write_blank(row, col, None, empty_fmt)
            if key in cell_notes:
                ws.write_comment(row, col, "\n".join(cell_notes[key]))
        ws.set_row(row, _row_height(max_lines))

    # =========================================================
    # Sheet 3: Bookings (flat list — pivot/filter friendly)
    # =========================================================
    bk = workbook.add_worksheet("Bookings")
    bk_cols = [
        ("Resource", 24), ("Type", 16), ("Title", 40), ("Client", 22),
        ("Job", 30), ("Phase / Project", 30), ("Delivery Role", 14),
        ("Status", 12), ("Onsite", 8), ("Start", 18), ("End", 18),
    ]
    for col, (name, width) in enumerate(bk_cols):
        bk.write(0, col, name, list_hdr_fmt)
        bk.set_column(col, col, width)
    bk.freeze_panes(1, 0)
    bk.autofilter(0, 0, max(1, len(slots)), len(bk_cols) - 1)

    order = {m["id"]: i for i, m in enumerate(members)}
    for row, slot in enumerate(
        sorted(slots, key=lambda s: (order.get(s.user_id, 0), s.start)), start=1
    ):
        phase = slot.phase_or_none if slot.is_delivery() else None
        job = phase.job if phase else None
        if phase:
            target = "{}: {}".format(phase.get_id(), phase.title)
        elif slot.is_project() and slot.project:
            target = "{}: {}".format(slot.project.id, slot.project.title)
        else:
            target = ""
        values = [
            users[slot.user_id].get_full_name(),
            slot.slot_type.name,
            slot.get_schedule_title(),
            str(job.client) if job and job.client else "",
            "{}: {}".format(job.id, job.title) if job else "",
            target,
            slot.get_deliveryRole_display() if slot.is_delivery() else "",
            "Confirmed" if slot.is_confirmed() else "Tentative",
            "Yes" if slot.is_onsite else "",
        ]
        for col, value in enumerate(values):
            bk.write(row, col, value, list_cell_fmt)
        bk.write_datetime(row, 9, timezone.localtime(slot.start), list_dt_fmt)
        bk.write_datetime(row, 10, timezone.localtime(slot.end), list_dt_fmt)

    # =========================================================
    # Sheet 4: Resources
    # =========================================================
    rs = workbook.add_worksheet("Resources")
    rs_cols = [
        ("Resource", 24), ("Email", 30), ("Org Unit", 20), ("Job Level", 18),
        ("Roles", 20), ("Availability", 12), ("Utilisation", 12),
    ]
    for col, (name, width) in enumerate(rs_cols):
        rs.write(0, col, name, list_hdr_fmt)
        rs.set_column(col, col, width)
    rs.freeze_panes(1, 0)
    for row, member in enumerate(members, start=1):
        user = users[member["id"]]
        rs.write(row, 0, member["title"], list_cell_fmt)
        rs.write(row, 1, user.email, list_cell_fmt)
        rs.write(row, 2, member.get("org_unit", ""), list_cell_fmt)
        rs.write(row, 3, member.get("job_level", ""), list_cell_fmt)
        rs.write(row, 4, ", ".join(member.get("roles", [])), list_cell_fmt)
        rs.write(row, 5, (member.get("availability") or 0) / 100.0, list_pct_fmt)
        rs.write(row, 6, (member.get("util") or 0) / 100.0, list_pct_fmt)

    workbook.close()
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="{}.xlsx"'.format(filename)
    return response
