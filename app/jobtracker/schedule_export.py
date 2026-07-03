import io
from collections import defaultdict
from datetime import timedelta
from django.http import HttpResponse


def _next_day(d):
    return d + timedelta(days=1)


def _fmt_date(d):
    return d.strftime("%d %b %Y") if d else ""


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
    Build a two-sheet XLSX schedule export.

    Sheet 1 "Schedule": an optional client-ready header block, then a grid of
    resources (rows) x dates (columns) with the phase and delivery type in each cell.
    Sheet 2 "Summary": one row per phase with hours breakdown and team.

    ``title``       optional heading rendered at the top of the Schedule sheet.
    ``header_rows`` optional list of (label, value) tuples rendered as a stats block.
    """
    import xlsxwriter

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"remove_timezone": True})

    # Formats
    title_fmt = workbook.add_format({
        "bold": True, "font_size": 15, "valign": "vcenter",
    })
    hdr_label_fmt = workbook.add_format({
        "bold": True, "bg_color": "#E8E8E8", "border": 1, "valign": "vcenter",
    })
    hdr_value_fmt = workbook.add_format({
        "border": 1, "valign": "vcenter", "text_wrap": True,
    })
    header_fmt = workbook.add_format({
        "bold": True, "bg_color": "#D3D3D3", "border": 1,
        "align": "center", "valign": "vcenter", "text_wrap": True,
    })
    date_fmt = workbook.add_format({
        "bold": True, "bg_color": "#E8E8E8", "border": 1,
        "align": "center", "num_format": "ddd dd/mm",
    })
    weekend_fmt = workbook.add_format({
        "bg_color": "#F5F5F5", "border": 1, "font_color": "#AAAAAA",
        "align": "center", "num_format": "ddd dd/mm",
    })
    cell_fmt = workbook.add_format({"border": 1, "text_wrap": True, "align": "center", "valign": "vcenter"})
    weekend_cell_fmt = workbook.add_format({
        "border": 1, "text_wrap": True, "align": "center", "valign": "vcenter",
        "bg_color": "#FAFAFA",
    })
    user_fmt = workbook.add_format({"bold": True, "border": 1, "bg_color": "#E8F4F8"})
    summary_header_fmt = workbook.add_format({
        "bold": True, "bg_color": "#D3D3D3", "border": 1,
        "align": "center", "text_wrap": True,
    })

    # --- Build data structures ---
    slots_list = list(timeslots.select_related("user", "phase", "phase__service", "phase__job"))

    users = {}
    dates = set()

    for slot in slots_list:
        if slot.user:
            users[slot.user.pk] = slot.user
        d = slot.start.date()
        end_d = slot.end.date()
        while d <= end_d:
            dates.add(d)
            d = _next_day(d)

    sorted_dates = sorted(dates)
    sorted_users = sorted(users.values(), key=lambda u: (u.last_name, u.first_name))

    # --- Sheet 1: Schedule ---
    ws = workbook.add_worksheet("Schedule")
    ws.set_column(0, 0, 24)

    row_cursor = 0
    # Title
    if title:
        span = max(3, min(len(sorted_dates), 8))
        ws.merge_range(row_cursor, 0, row_cursor, span, title, title_fmt)
        ws.set_row(row_cursor, 22)
        row_cursor += 2

    # Header stat block (label | value spanning a few columns)
    if header_rows:
        for label, value in header_rows:
            ws.write(row_cursor, 0, label, hdr_label_fmt)
            ws.merge_range(row_cursor, 1, row_cursor, 3, value, hdr_value_fmt)
            row_cursor += 1
        row_cursor += 1  # blank spacer row

    grid_header_row = row_cursor

    # Grid header: Resource + dates
    ws.write(grid_header_row, 0, "Resource", header_fmt)
    for col, d in enumerate(sorted_dates, start=1):
        fmt = weekend_fmt if d.weekday() >= 5 else date_fmt
        ws.write_datetime(grid_header_row, col, d, fmt)
        ws.set_column(col, col, 14)

    ws.freeze_panes(grid_header_row + 1, 1)

    # Build cell map: (user_pk, date) -> "Phase (Role)"
    cell_map = defaultdict(str)
    for slot in slots_list:
        if not slot.user or not slot.phase:
            continue
        role = slot.get_deliveryRole_display()
        phase_title = slot.phase.title[:24]
        if role and role != "None":
            label = "{} ({})".format(phase_title, role)
        else:
            label = phase_title
        d = slot.start.date()
        end_d = slot.end.date()
        while d <= end_d:
            key = (slot.user.pk, d)
            if cell_map[key] and label not in cell_map[key]:
                cell_map[key] += " / " + label
            elif not cell_map[key]:
                cell_map[key] = label
            d = _next_day(d)

    for i, user in enumerate(sorted_users):
        row = grid_header_row + 1 + i
        ws.write(row, 0, user.get_full_name(), user_fmt)
        for col, d in enumerate(sorted_dates, start=1):
            value = cell_map.get((user.pk, d), "")
            fmt = weekend_cell_fmt if d.weekday() >= 5 else cell_fmt
            ws.write(row, col, value, fmt)

    # --- Sheet 2: Summary ---
    ws2 = workbook.add_worksheet("Summary")
    ws2.freeze_panes(1, 0)

    summary_cols = [
        "Phase", "Status", "Service",
        "Start Date", "Delivery Date",
        "Delivery Hrs", "Reporting Hrs", "Mgmt Hrs", "QA Hrs",
        "Oversight Hrs", "Debrief Hrs", "Contingency Hrs", "Other Hrs",
        "Lead", "Author", "Tech QA", "Pres QA",
    ]
    for col, name in enumerate(summary_cols):
        ws2.write(0, col, name, summary_header_fmt)
        ws2.set_column(col, col, 16)

    phases_seen = {}
    for slot in slots_list:
        if slot.phase and slot.phase.pk not in phases_seen:
            phases_seen[slot.phase.pk] = slot.phase

    for row, phase in enumerate(phases_seen.values(), start=1):
        ws2.write(row, 0, str(phase.title), cell_fmt)
        ws2.write(row, 1, phase.get_status_display(), cell_fmt)
        ws2.write(row, 2, str(phase.service) if phase.service else "", cell_fmt)
        ws2.write(row, 3, _fmt_date(phase.start_date), cell_fmt)
        ws2.write(row, 4, _fmt_date(phase.delivery_date), cell_fmt)
        ws2.write(row, 5, float(phase.delivery_hours or 0), cell_fmt)
        ws2.write(row, 6, float(phase.reporting_hours or 0), cell_fmt)
        ws2.write(row, 7, float(phase.mgmt_hours or 0), cell_fmt)
        ws2.write(row, 8, float(phase.qa_hours or 0), cell_fmt)
        ws2.write(row, 9, float(phase.oversight_hours or 0), cell_fmt)
        ws2.write(row, 10, float(phase.debrief_hours or 0), cell_fmt)
        ws2.write(row, 11, float(phase.contingency_hours or 0), cell_fmt)
        ws2.write(row, 12, float(phase.other_hours or 0), cell_fmt)
        ws2.write(row, 13, phase.project_lead.get_full_name() if phase.project_lead else "", cell_fmt)
        ws2.write(row, 14, phase.report_author.get_full_name() if phase.report_author else "", cell_fmt)
        ws2.write(row, 15, phase.techqa_by.get_full_name() if phase.techqa_by else "", cell_fmt)
        ws2.write(row, 16, phase.presqa_by.get_full_name() if phase.presqa_by else "", cell_fmt)

    workbook.close()
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="{}.xlsx"'.format(filename)
    return response
