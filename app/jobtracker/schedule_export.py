import io
import math
from collections import defaultdict
from datetime import timedelta
from django.http import HttpResponse
from constance import config

from .enums import DefaultTimeSlotTypes, TimeSlotDeliveryRole

# CHAOTICA / Phoenix theme
PHX_PRIMARY = "#3874ff"
PHX_GRAY_100 = "#eff2f6"
PHX_GRAY_200 = "#e3e6ed"
PHX_BORDER = "#cbd0dd"
PHX_INK = "#141824"
PHX_SECONDARY = "#525b75"

# Days off that are safe to surface to a client (non-sensitive)
_LEAVE_TYPES = {
    DefaultTimeSlotTypes.LEAVE,
    DefaultTimeSlotTypes.SICK,
    DefaultTimeSlotTypes.BANK_HOL,
}


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
    from .models import TimeSlot

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
        "border": 1, "border_color": PHX_BORDER, "align": "center", "num_format": "ddd dd/mm",
    })
    weekend_date_fmt = workbook.add_format({
        "bold": True, "bg_color": "#7ba0ff", "font_color": "#FFFFFF",
        "border": 1, "border_color": PHX_BORDER, "align": "center", "num_format": "ddd dd/mm",
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
    leave_fmt = workbook.add_format({
        "border": 1, "border_color": PHX_BORDER, "bg_color": "#ffe9a8",
        "font_color": PHX_INK, "italic": True,
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

    # Unavailable days: resources' *other* commitments across the range.
    # category: "leave" (safe to name) or "busy" (generic, keeps other clients private)
    busy_map = {}
    if sorted_users and sorted_dates:
        other_slots = (
            TimeSlot.objects.filter(
                user_id__in=list(users.keys()),
                start__date__lte=max_date,
                end__date__gte=min_date,
            )
            .exclude(pk__in=exported_pks)
            .select_related("slot_type")
        )
        for slot in other_slots:
            is_leave = slot.slot_type_id in _LEAVE_TYPES
            d = max(slot.start.date(), min_date)
            end_d = min(slot.end.date(), max_date)
            while d <= end_d:
                key = (slot.user_id, d)
                if key not in cell_map:
                    # leave wins over generic busy for a friendlier label
                    if is_leave or key not in busy_map:
                        busy_map[key] = "leave" if is_leave else "busy"
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
        ("#ffe9a8", "Leave / time off"),
        (PHX_GRAY_200, "Unavailable (committed elsewhere)"),
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
            elif key in busy_map:
                if busy_map[key] == "leave":
                    ws.write(row, col, "Leave", leave_fmt)
                else:
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
        "Phase ID", "Phase", "Status", "Service",
        "Start Date", "Delivery Date",
        "Delivery Days", "Reporting Days", "Mgmt Days", "QA Days",
        "Oversight Days", "Debrief Days", "Contingency Days", "Other Days",
        "Lead", "Author", "Tech QA", "Pres QA",
    ]
    for col, name in enumerate(summary_cols):
        ws2.write(0, col, name, summary_header_fmt)
        ws2.set_column(col, col, SUMMARY_COL_WIDTH)

    phases_seen = {}
    for slot in slots_list:
        if slot.phase and slot.phase.pk not in phases_seen:
            phases_seen[slot.phase.pk] = slot.phase

    for row, phase in enumerate(phases_seen.values(), start=1):
        ws2.write(row, 0, phase.get_id(), summary_cell_fmt)
        ws2.write(row, 1, str(phase.title), summary_cell_fmt)
        ws2.write(row, 2, phase.get_status_display(), summary_cell_fmt)
        ws2.write(row, 3, str(phase.service) if phase.service else "", summary_cell_fmt)
        ws2.write(row, 4, _fmt_date(phase.start_date), summary_cell_fmt)
        ws2.write(row, 5, _fmt_date(phase.delivery_date), summary_cell_fmt)
        ws2.write(row, 6, float(phase.get_total_scoped_days_by_type(TimeSlotDeliveryRole.DELIVERY)), summary_cell_fmt)
        ws2.write(row, 7, float(phase.get_total_scoped_days_by_type(TimeSlotDeliveryRole.REPORTING)), summary_cell_fmt)
        ws2.write(row, 8, float(phase.get_total_scoped_days_by_type(TimeSlotDeliveryRole.MANAGEMENT)), summary_cell_fmt)
        ws2.write(row, 9, float(phase.get_total_scoped_days_by_type(TimeSlotDeliveryRole.QA)), summary_cell_fmt)
        ws2.write(row, 10, float(phase.get_total_scoped_days_by_type(TimeSlotDeliveryRole.OVERSIGHT)), summary_cell_fmt)
        ws2.write(row, 11, float(phase.get_total_scoped_days_by_type(TimeSlotDeliveryRole.DEBRIEF)), summary_cell_fmt)
        ws2.write(row, 12, float(phase.get_total_scoped_days_by_type(TimeSlotDeliveryRole.CONTINGENCY)), summary_cell_fmt)
        ws2.write(row, 13, float(phase.get_total_scoped_days_by_type(TimeSlotDeliveryRole.OTHER)), summary_cell_fmt)
        ws2.write(row, 14, phase.project_lead.get_full_name() if phase.project_lead else "", summary_cell_fmt)
        ws2.write(row, 15, phase.report_author.get_full_name() if phase.report_author else "", summary_cell_fmt)
        ws2.write(row, 16, phase.techqa_by.get_full_name() if phase.techqa_by else "", summary_cell_fmt)
        ws2.write(row, 17, phase.presqa_by.get_full_name() if phase.presqa_by else "", summary_cell_fmt)
        # Size the row for the widest wrapping text column (title / service).
        max_lines = max(
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
