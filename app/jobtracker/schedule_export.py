import io
from collections import defaultdict
from django.http import HttpResponse
from django.utils import timezone


def build_schedule_xlsx(timeslots, filename):
    """
    Build a two-sheet XLSX schedule export.
    Sheet 1 "Schedule": users as rows, dates as columns, phase name in cells.
    Sheet 2 "Summary": one row per phase with hours breakdown and team.
    """
    import xlsxwriter

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"remove_timezone": True})

    # Formats
    header_fmt = workbook.add_format({
        "bold": True, "bg_color": "#D3D3D3", "border": 1,
        "align": "center", "valign": "vcenter", "text_wrap": True,
    })
    date_fmt = workbook.add_format({
        "bold": True, "bg_color": "#E8E8E8", "border": 1,
        "align": "center", "num_format": "dd/mm",
    })
    weekend_fmt = workbook.add_format({
        "bg_color": "#F5F5F5", "border": 1, "font_color": "#AAAAAA",
        "align": "center", "num_format": "dd/mm",
    })
    cell_fmt = workbook.add_format({"border": 1, "text_wrap": True, "align": "center", "valign": "vcenter"})
    user_fmt = workbook.add_format({"bold": True, "border": 1, "bg_color": "#E8F4F8"})
    summary_header_fmt = workbook.add_format({
        "bold": True, "bg_color": "#D3D3D3", "border": 1,
        "align": "center", "text_wrap": True,
    })

    # --- Build data structures ---
    slots_list = list(timeslots.select_related("user", "phase", "phase__service", "phase__job"))

    # Collect unique users and dates
    users = {}
    dates = set()
    phase_slots = defaultdict(list)

    for slot in slots_list:
        if slot.user:
            users[slot.user.pk] = slot.user
        if slot.phase:
            phase_slots[slot.phase.pk].append(slot)
        d = slot.start.date()
        end_d = slot.end.date()
        while d <= end_d:
            dates.add(d)
            d = d.replace(day=d.day) if False else _next_day(d)

    sorted_dates = sorted(dates)
    sorted_users = sorted(users.values(), key=lambda u: (u.last_name, u.first_name))

    # --- Sheet 1: Schedule ---
    ws = workbook.add_worksheet("Schedule")
    ws.freeze_panes(1, 1)

    ws.write(0, 0, "User", header_fmt)
    ws.set_column(0, 0, 20)

    for col, d in enumerate(sorted_dates, start=1):
        fmt = weekend_fmt if d.weekday() >= 5 else date_fmt
        ws.write_datetime(0, col, d, fmt)
        ws.set_column(col, col, 12)

    # Build cell map: (user_pk, date) -> phase name
    cell_map = defaultdict(str)
    for slot in slots_list:
        if not slot.user or not slot.phase:
            continue
        d = slot.start.date()
        end_d = slot.end.date()
        label = slot.phase.title[:20] if slot.phase else ""
        while d <= end_d:
            key = (slot.user.pk, d)
            if cell_map[key]:
                cell_map[key] += " / " + label
            else:
                cell_map[key] = label
            d = _next_day(d)

    for row, user in enumerate(sorted_users, start=1):
        ws.write(row, 0, user.get_full_name(), user_fmt)
        for col, d in enumerate(sorted_dates, start=1):
            value = cell_map.get((user.pk, d), "")
            ws.write(row, col, value, cell_fmt)

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

    # Deduplicate phases from timeslots
    phases_seen = {}
    for slot in slots_list:
        if slot.phase and slot.phase.pk not in phases_seen:
            phases_seen[slot.phase.pk] = slot.phase

    date_cell_fmt = workbook.add_format({"border": 1, "num_format": "yyyy-mm-dd"})
    for row, phase in enumerate(phases_seen.values(), start=1):
        ws2.write(row, 0, str(phase.title), cell_fmt)
        ws2.write(row, 1, phase.get_status_display(), cell_fmt)
        ws2.write(row, 2, str(phase.service) if phase.service else "", cell_fmt)
        ws2.write(row, 3, phase.start_date.strftime("%Y-%m-%d") if phase.start_date else "", cell_fmt)
        ws2.write(row, 4, phase.delivery_date.strftime("%Y-%m-%d") if phase.delivery_date else "", cell_fmt)
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


def _next_day(d):
    from datetime import timedelta
    return d + timedelta(days=1)
