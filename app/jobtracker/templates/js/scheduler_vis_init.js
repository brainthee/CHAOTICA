// Shared vis-timeline scheduler. Driven entirely by window.SCHEDULER_CONFIG so
// the same code serves the global, job-scoped and phase-scoped surfaces.
//   SCHEDULER_CONFIG = {
//     scope: 'global'|'job'|'phase',
//     membersUrl, slotsUrl,
//     changeDateUrl, changeCommentDateUrl,
//     createUrls: {assign_phase, assign_project, assign_internal, add_comment, clear},
//     createExtraParams: '',            // e.g. '&job=5&phase=12'
//     resetUrl: '',                     // filter "reset" target (global only)
//     cards: {util, userBreakdown, phaseStatus} | null,  // scoped analytics
//   }
(function () {
  var CFG = window.SCHEDULER_CONFIG || {};
  var membersUrl = CFG.membersUrl;
  var slotsUrl   = CFG.slotsUrl;
  var createUrls = CFG.createUrls || {};
  var createExtraParams = CFG.createExtraParams || '';
  var readonly = !!CFG.readonly;   // embedded read-only view (detail tabs)
  // Job/phase views fade in "other" slots (commitments outside this job/phase) so
  // gaps can be trusted. This lets the user hide that noise; remembered per browser.
  var showOthers = (localStorage.getItem('sched-show-others') !== '0');
  // Existing filter querystring (without the leading "?") so the global page can
  // re-apply the same SchedulerFilter. Ignored by the scoped endpoints.
  var filterParams = window.location.search.replace(/^\?/, '');

  function buildUrl(base, start, end) {
    var q = 'start=' + encodeURIComponent(start) + '&end=' + encodeURIComponent(end);
    if (filterParams) q += '&' + filterParams;
    return base + '?' + q;
  }

  var csrf = $('input[name="csrfmiddlewaretoken"]').val();

  var container = document.getElementById('vis-timeline');
  var groups = new vis.DataSet();
  var items = new vis.DataSet();

  // Axis label formats. We drive the axis scale ourselves (see chooseAxisScale) so
  // it cleanly steps day -> week -> month -> year, never vis's "every 2-3 days".
  var MAJOR = {
    hour: 'ddd D MMMM', weekday: 'MMMM YYYY', day: 'MMMM YYYY',
    week: 'MMMM YYYY', month: 'YYYY', year: ''
  };
  var MINOR_STR = {
    hour: 'HH:mm', weekday: 'ddd D', day: 'D',
    week: 'D MMM', month: 'MMM', year: 'YYYY'
  };
  // Weekday initials for the tight day tiers. moment has no single-letter token,
  // so these render via a whole-minorLabels function (vis rejects a function on an
  // individual key — it only accepts a format string there, or a function for the
  // entire minorLabels object).
  var DOW_ONE = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];
  var DOW_TWO = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];
  var DOW_THREE = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  // Two-line label: weekday stacked over the date number ("Mon" / "1"). vis renders
  // axis labels as HTML (xss protection is disabled), so <br> gives the break. The
  // weekday width adapts to zoom (3 → 2 → 1 char); the second line is always the date.
  function dayLabel(dow, date) { return '<span class="sched-day2">' + dow + '<br>' + new Date(date).getDate() + '</span>'; }
  function fmtDayThree(date) { return dayLabel(DOW_THREE[new Date(date).getDay()], date); }
  function fmtDayTwo(date) { return dayLabel(DOW_TWO[new Date(date).getDay()], date); }
  function fmtDayOne(date) { return dayLabel(DOW_ONE[new Date(date).getDay()], date); }
  // dayFmt is either a moment format string (object form) OR a function(date) for the
  // 'day' scale (whole-minorLabels function form; other scales fall back to moment).
  function buildFormat(dayFmt) {
    if (typeof dayFmt === 'function') {
      return {
        minorLabels: function (date, scale, step) {
          if (scale === 'day') return dayFmt(date);
          return (typeof moment !== 'undefined')
            ? moment(date).format(MINOR_STR[scale] || 'D')
            : String(new Date(date).getDate());
        },
        majorLabels: MAJOR
      };
    }
    var minor = {
      hour: MINOR_STR.hour, weekday: MINOR_STR.weekday, day: dayFmt || 'D',
      week: MINOR_STR.week, month: MINOR_STR.month, year: MINOR_STR.year
    };
    return { minorLabels: minor, majorLabels: MAJOR };
  }

  var options = {
    stack: true,
    margin: { item: 3, axis: 6 },
    zoomMin: 1000 * 60 * 60 * 24 * 2,           // ~2 days
    zoomMax: 1000 * 60 * 60 * 24 * 365 * 4,     // ~4 years
    verticalScroll: true,
    horizontalScroll: false,
    zoomKey: 'ctrlKey',
    zoomFriction: 8,
    moveable: true,
    zoomable: true,
    selectable: true,
    multiselect: false,
    groupHeightMode: 'auto',
    tooltip: { followMouse: true, overflowMethod: 'cap' },
    xss: { disabled: true },
    editable: readonly ? false : { updateTime: true, updateGroup: true, add: false, remove: false, overrideItems: false },
    onMove: onItemMove,
    groupOrder: function (a, b) { return (a.order || 0) - (b.order || 0); },
    orientation: 'top',
    format: buildFormat('D')
  };

  var timeline = new vis.Timeline(container, items, groups, options);

  // Initial window: ~1 week back, ~5 weeks forward — days are legible by default.
  var now = new Date();
  var winStart = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
  var winEnd = new Date(now.getTime() + 35 * 24 * 60 * 60 * 1000);
  timeline.setWindow(winStart, winEnd, { animation: false });

  // Size the timeline to the space above the fixed footer; it then provides
  // its own internal vertical scrollbar for the long resource list.
  var footerEl = document.querySelector('footer');
  function fitHeight() {
    var cTop = container.getBoundingClientRect().top;
    // The global scheduler has a fixed-bottom footer, so clamp to it. Scoped
    // pages (job/phase, incl. the read-only detail tab) scroll normally with the
    // footer below the fold — size to the viewport, or the timeline collapses to
    // a short strip and "doesn't show as far".
    var bottom = (CFG.scope === 'global' && footerEl)
      ? footerEl.getBoundingClientRect().top
      : window.innerHeight;
    var h = Math.max(240, Math.floor(bottom - cTop - 8));
    if (readonly) h = Math.min(h, 520);   // bounded preview inside a detail tab
    container.style.height = h + 'px';
    timeline.setOptions({ minHeight: h, maxHeight: h });
  }
  fitHeight();
  window.addEventListener('load', fitHeight);
  if (footerEl && window.ResizeObserver) {
    new ResizeObserver(function () { fitHeight(); }).observe(footerEl);
  }

  // Drive the time-axis scale from pixels-per-day so we never land on vis's
  // awkward "every 2-3 days" step: day(number) -> day(weekday+number) -> week -> month -> year.
  var currentAxisKey = null;
  function chooseAxisScale() {
    var centerEl = container.querySelector('.vis-panel.vis-center');
    var widthPx = centerEl ? centerEl.clientWidth : 0;
    if (!widthPx) return;
    var w = timeline.getWindow();
    var ppd = 86400000 / ((w.end - w.start) / widthPx);   // pixels per day
    var scale, dayFmt = null, dayKey = '';
    if (ppd >= 55) { scale = 'day'; dayFmt = fmtDayThree; dayKey = 'd3'; }        // roomy: "Mon" / "1"
    else if (ppd >= 28) { scale = 'day'; dayFmt = fmtDayTwo; dayKey = 'd2'; }     // "Mo" / "1"
    else if (ppd >= 16) { scale = 'day'; dayFmt = fmtDayOne; dayKey = 'd1'; }     // "M" / "1"
    else if (ppd >= 3.5) { scale = 'week'; }
    else if (ppd >= 0.6) { scale = 'month'; }
    else { scale = 'year'; }
    var key = scale + '|' + dayKey;
    if (key === currentAxisKey) return;
    currentAxisKey = key;
    timeline.setOptions({ timeAxis: { scale: scale, step: 1 }, format: buildFormat(dayFmt) });
  }
  chooseAxisScale();

  var resizeTimer = null;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { fitHeight(); chooseAxisScale(); }, 150);
  });

  // ---- Loading helpers (subtle, non-blocking: toolbar spinner + top progress bar) ----
  var inflight = 0;
  var loadingEl = document.getElementById('sched-loading');
  var progressEl = document.getElementById('sched-progress');
  function loading(on) {
    inflight = Math.max(0, inflight + (on ? 1 : -1));
    var active = inflight > 0;
    if (loadingEl) loadingEl.classList.toggle('is-active', active);
    if (progressEl) progressEl.classList.toggle('is-active', active);
  }

  function utilBadgeClass(util) {
    if (util >= 90) return 'badge-phoenix-danger';
    if (util >= 70) return 'badge-phoenix-success';
    if (util >= 40) return 'badge-phoenix-warning';
    return 'badge-phoenix-secondary';
  }

  function escapeHtml(s) {
    return (s == null ? '' : String(s)).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function buildGroupContent(r) {
    var name = escapeHtml(r.title || ((r.first_name || '') + ' ' + (r.last_name || '')).trim());
    var lvl = escapeHtml(r.job_level || '');
    var util = Math.round((r.util != null) ? r.util : 0);
    var roles = (r.roles || []).map(function (role) {
      return '<span class="sched-role">' + escapeHtml(role) + '</span>';
    }).join('');
    return '<div class="sched-res">' +
             '<span class="meta">' +
               '<span class="name">' + name + '</span>' +
               (lvl ? '<span class="lvl">' + lvl + '</span>' : '') +
               (roles ? '<span class="sched-roles">' + roles + '</span>' : '') +
             '</span>' +
             '<span class="badge badge-phoenix ' + utilBadgeClass(util) + '">' + util + '%</span>' +
           '</div>';
  }

  // ---- Members (resources -> groups) ----
  function loadMembers() {
    loading(true);
    var w = timeline.getWindow();
    $.ajax({
      url: buildUrl(membersUrl, w.start.toISOString(), w.end.toISOString()),
      method: 'GET',
      success: function (data) {
        var g = data.map(function (r, idx) {
          return {
            id: r.id, content: buildGroupContent(r), order: idx, util: r.util,
            workingHours: r.workingHours || r.businessHours || null
          };
        });
        groups.update(g);
      },
      complete: function () { loading(false); }
    });
  }

  // ---- Slots / comments / holidays (events -> items) ----
  function dayAfter(d) {
    var x = new Date(d);
    x.setDate(x.getDate() + 1);
    return x;
  }
  function startOfDay(d) { var x = new Date(d); x.setHours(0, 0, 0, 0); return x; }
  function startOfNextDay(d) { var x = startOfDay(d); x.setDate(x.getDate() + 1); return x; }

  function buildTooltip(e) {
    var t = e.title || '';
    var type = e.slot_type_name || '';
    // Don't duplicate the slot type when the title already conveys it — e.g.
    // delivery slots end with the "Delivery" role, internal slots == the type.
    if (type && t.toLowerCase().indexOf(type.toLowerCase()) === -1) {
      t = type + ': ' + t;
    }
    return t;
  }

  function mapEvent(e) {
    var isBackground = (e.display === 'background') || e.allDay === true;
    if (isBackground) {
      var endBg = e.end;
      if (!endBg || new Date(endBg) <= new Date(e.start)) endBg = dayAfter(e.start);
      var isHoliday = e.allDay === true;
      return {
        id: 'bg-' + e.id + '-' + e.resourceId,
        group: e.resourceId,
        start: e.start,
        end: endBg,
        type: 'background',
        content: escapeHtml(e.title || ''),
        style: 'background-color:' + (isHoliday ? 'rgba(220,53,69,0.12)' : 'rgba(120,130,150,0.10)') + ';'
      };
    }
    var bg = e.backgroundColor || e.color || '#5e6e82';
    var fg = e.textColor || 'white';
    var idPrefix = e.is_comment ? 'cmt-' : 'slot-';
    var icon = e.icon ? '<i class="' + e.icon + ' me-1"></i>' : '';
    // Work is booked by the day (9-5 etc.), so render each booking as a full-day
    // block edge-to-edge — no intra-day gaps. Real times are re-derived from the
    // resource's working hours on drag/resize (see onItemMove). Comments keep
    // their exact time.
    var dispStart = e.start, dispEnd = e.end;
    if (!e.is_comment) {
      dispStart = startOfDay(e.start);
      dispEnd = startOfNextDay(e.end);
    }
    // On a job/phase-scoped view, a member's other commitments are shown FADED
    // (never hidden) so gaps can be trusted; they aren't editable from here.
    var faded = !!e.out_of_scope;
    var canEdit = !!e.can_edit && !faded;
    return {
      id: idPrefix + e.id,
      group: e.resourceId,
      start: dispStart,
      end: dispEnd,
      content: icon + escapeHtml(e.title || ''),
      title: escapeHtml(buildTooltip(e)),
      className: (e.is_comment ? 'cmt' : '') + (faded ? ' sched-faded' : '') + (e.is_tentative ? ' sched-slot-tentative' : ''),
      style: 'background-color:' + bg + '; color:' + fg + '; border-color:' + bg + ';',
      editable: canEdit ? { updateTime: true, updateGroup: true, remove: false } : false,
      _meta: {
        origId: e.id,
        isComment: !!e.is_comment,
        canEdit: canEdit,
        editUrl: canEdit ? e.edit_url : null,
        userId: e.userId
      }
    };
  }

  // ---- Track which time ranges have actually been fetched ----
  var loadedRanges = [];
  var unloadedIds = [];

  function addLoadedRange(s, e) {
    loadedRanges.push([s, e]);
    loadedRanges.sort(function (a, b) { return a[0] - b[0]; });
    var merged = [];
    for (var i = 0; i < loadedRanges.length; i++) {
      var r = loadedRanges[i];
      if (merged.length && r[0] <= merged[merged.length - 1][1]) {
        merged[merged.length - 1][1] = Math.max(merged[merged.length - 1][1], r[1]);
      } else { merged.push([r[0], r[1]]); }
    }
    loadedRanges = merged;
  }

  function resetLoadedRanges() {
    loadedRanges = [];
    if (unloadedIds.length) { items.remove(unloadedIds); unloadedIds = []; }
  }

  function renderUnloaded() {
    if (unloadedIds.length) { items.remove(unloadedIds); unloadedIds = []; }
    var w = timeline.getWindow();
    var ws = w.start.getTime(), we = w.end.getTime();
    var cursor = ws, gaps = [];
    for (var i = 0; i < loadedRanges.length; i++) {
      var r = loadedRanges[i];
      if (r[1] <= ws || r[0] >= we) continue;
      if (r[0] > cursor) gaps.push([cursor, Math.min(r[0], we)]);
      cursor = Math.max(cursor, r[1]);
      if (cursor >= we) break;
    }
    if (cursor < we) gaps.push([cursor, we]);
    gaps.forEach(function (g, idx) {
      var id = 'unloaded-' + idx;
      unloadedIds.push(id);
      items.add({ id: id, start: new Date(g[0]), end: new Date(g[1]),
                  type: 'background', className: 'sched-unloaded' });
    });
  }

  function pruneFar() {
    var w = timeline.getWindow();
    var span = w.end - w.start;
    var lo = w.start.getTime() - span * 2;
    var hi = w.end.getTime() + span * 2;
    var rm = [];
    items.get().forEach(function (it) {
      var id = String(it.id);
      if (id.indexOf('__sel__') === 0 || id.indexOf('unloaded-') === 0) return;
      var st = new Date(it.start).getTime();
      var en = it.end ? new Date(it.end).getTime() : st;
      if (en < lo || st > hi) rm.push(it.id);
    });
    if (rm.length) items.remove(rm);
  }

  function loadSlots() {
    loading(true);
    var w = timeline.getWindow();
    var span = w.end - w.start;
    var s = new Date(w.start.getTime() - span);
    var en = new Date(w.end.getTime() + span);
    $.ajax({
      url: buildUrl(slotsUrl, s.toISOString(), en.toISOString()),
      method: 'GET',
      success: function (data) {
        // Optionally drop out-of-scope ("other") slots so the view isn't noisy.
        var rows = showOthers ? data : data.filter(function (e) { return !e.out_of_scope; });
        var mapped = rows.map(mapEvent);
        var keep = {};
        mapped.forEach(function (m) { keep[m.id] = true; });
        var stale = items.getIds().filter(function (id) {
          id = String(id);
          if (id.indexOf('__sel__') === 0 || id.indexOf('unloaded-') === 0) return false;
          return !keep[id];
        });
        if (stale.length) items.remove(stale);
        items.update(mapped);
        loadedRanges = [];
        addLoadedRange(s.getTime(), en.getTime());
        renderUnloaded();
      },
      complete: function () { loading(false); }
    });
  }

  // ---- Drag / resize / move-to-another-user ----
  function onItemMove(item, callback) {
    var meta = item._meta || {};
    if (!meta.canEdit) { callback(null); return; }
    Swal.fire({
      title: 'Save the change?',
      showCancelButton: true,
      confirmButtonText: 'Save'
    }).then(function (result) {
      if (!result.isConfirmed) { callback(null); return; }
      var changeBase = meta.isComment ? CFG.changeCommentDateUrl : CFG.changeDateUrl;
      // Blocks render as whole days; re-derive real working-hours times from the
      // destination resource so stored times stay clean 9-5 (not midnight).
      var startISO, endISO;
      if (meta.isComment) {
        startISO = new Date(item.start).toISOString();
        endISO = new Date(item.end).toISOString();
      } else {
        var lastDay = new Date(new Date(item.end).getTime() - 1);  // step back into the final day
        var wr = snapRange(item.group, item.start, lastDay);
        startISO = wr.start;
        endISO = wr.end;
      }
      loading(true);
      $.ajax({
        url: changeBase + meta.origId,
        type: 'POST',
        dataType: 'json',
        data: {
          pk: meta.origId,
          start: startISO,
          end: endISO,
          user: item.group,           // moving rows reassigns the user
          csrfmiddlewaretoken: csrf
        },
        success: function (resp) {
          if (resp.form_is_valid) {
            callback(item);
            loadSlots();
            loadMembers();
            refreshCards();
          } else {
            Swal.fire('Could not save', resp.error || 'The change was rejected. Check overlaps / constraints.', 'warning');
            callback(null);
          }
        },
        error: function () {
          Swal.fire('Error', 'Something went wrong saving the change.', 'error');
          callback(null);
        },
        complete: function () { loading(false); }
      });
    });
  }

  // ---- Double-click an item to open the edit modal (reuses #mainModal) ----
  timeline.on('doubleClick', function (props) {
    if (readonly || props.item == null) return;
    var it = items.get(props.item);
    var meta = it && it._meta;
    if (!meta || !meta.editUrl) return;
    loading(true);
    $.ajax({
      url: meta.editUrl,
      type: 'get',
      dataType: 'json',
      success: function (data) {
        $('#mainModalContent').html(data.html_form);
        $('#mainModal').modal('show');
      },
      complete: function () { loading(false); }
    });
  });

  // The reused create/edit modal partials carry their own inline submit handlers
  // which implement the logic-check + `force` bypass flow. They expect these globals
  // (which normally live in the FullCalendar scheduler). Provide them so the modals
  // work unchanged. We deliberately do NOT add our own #mainModal submit handler.
  window.calendar = { refetchEvents: loadSlots, refetchResources: loadMembers };

  function reloadCard(url, sel) {
    if (!url) return;
    $.get(url, function (html) { $(sel).html(html); });
  }
  var cards = CFG.cards || null;
  window.refreshUtilisation   = function () { if (cards) reloadCard(cards.util, '#schedule-util-container'); };
  window.refreshUserBreakdown = function () { if (cards) reloadCard(cards.userBreakdown, '#schedule-user-breakdown-container'); };
  window.refreshPhaseStatus   = function () { if (cards) reloadCard(cards.phaseStatus, '#schedule-phase-status-container'); };
  function refreshCards() {
    window.refreshUtilisation();
    window.refreshUserBreakdown();
    window.refreshPhaseStatus();
  }

  // The slot modals are injected via AJAX after page load, so the select2 /
  // datepicker libraries' own auto-init never fires for them. Re-init on open.
  $('#mainModal').on('shown.bs.modal', function () {
    $('#mainModal .django-select2, #mainModal .select2-widget')
      .not('.select2-hidden-accessible').each(function () {
        var $el = $(this);
        var opts = { dropdownParent: $('#mainModal .modal-content'), width: '100%' };
        if ($.fn.djangoSelect2) { $el.djangoSelect2(opts); }
        else if ($.fn.select2) { $el.select2(opts); }
      });
    var content = document.querySelector('#mainModal .modal-content');
    if (content && content.querySelector('[data-dbdp-config][name]')) {
      content.dispatchEvent(new Event('DOMNodeInserted', { bubbles: true }));
    }
  });

  // ---- Right-click a resource row to create slots ----
  function snapRange(groupId, startDate, endDate) {
    var g = groups.get(groupId);
    var wh = (g && g.workingHours) || { startTime: '09:00', endTime: '17:30' };
    var sp = (wh.startTime || '09:00').split(':');
    var ep = (wh.endTime || '17:30').split(':');
    var s = new Date(startDate);
    var e = new Date(endDate || startDate);
    s.setHours(parseInt(sp[0], 10) || 0, parseInt(sp[1], 10) || 0, 0, 0);
    e.setHours(parseInt(ep[0], 10) || 0, parseInt(ep[1], 10) || 0, 0, 0);
    if (e <= s) { e = new Date(s.getTime() + 8 * 60 * 60 * 1000); }
    return { start: s.toISOString(), end: e.toISOString() };
  }

  function openCreate(key) {
    var url = createUrls[key];
    if (!url || !ctxCtx || !ctxCtx.userIds.length) return;
    var who = (ctxCtx.userIds.length > 1)
      ? 'batch_users=' + ctxCtx.userIds.join(',')
      : 'resource_id=' + parseInt(ctxCtx.userIds[0], 10);
    loading(true);
    $.get(url + '?' + who +
          '&start=' + encodeURIComponent(ctxCtx.startISO) +
          '&end=' + encodeURIComponent(ctxCtx.endISO) +
          createExtraParams,
      function (d) {
        $('#mainModalContent').html(d.html_form);
        $('#mainModal').modal('show');
      }).always(function () { loading(false); });
  }

  // Exposed for the Scheduling Assistant: open the phase booking modal prefilled
  // for a specific user + window (creates a tentative/"draft" slot via the same
  // create flow + logic checks). Replaces the assistant modal content.
  window.schedulerAssistantBook = function (userId, startISO, endISO) {
    var url = createUrls.assign_phase;
    if (!url || !userId) return;
    loading(true);
    $.get(url + '?resource_id=' + parseInt(userId, 10) +
          '&start=' + encodeURIComponent(startISO) +
          '&end=' + encodeURIComponent(endISO) +
          createExtraParams,
      function (d) {
        $('#mainModalContent').html(d.html_form);
        $('#mainModal').modal('show');
      }).always(function () { loading(false); });
  };

  // Exposed for the Scheduling Assistant: refresh timeline + sidebar cards after
  // an assign/book action.
  window.schedulerAssistantRefresh = function () {
    loadSlots(); loadMembers(); refreshCards();
  };

  var ctxCtx = null;
  $.contextMenu({
    selector: '#vis-timeline',
    trigger: 'none',
    build: function () {
      return {
        callback: function (key) { openCreate(key); },
        items: {
          assign_phase: { name: 'Assign phase', icon: 'fas fa-cubes fs-8 me-2' },
          assign_project: { name: 'Assign project', icon: 'fas fa-diagram-project fs-8 me-2' },
          assign_internal: { name: 'Assign internal', icon: 'fas fa-briefcase fs-8 me-2' },
          add_comment: { name: 'Add comment', icon: 'fas fa-comment fs-8 me-2' },
          sep1: '---------',
          clear: { name: 'Clear range', icon: 'fas fa-eraser fs-8 me-2' }
        }
      };
    },
    position: function (opt) {
      opt.$menu.css({ top: ctxCtx ? ctxCtx.pageY : 0, left: ctxCtx ? ctxCtx.pageX : 0 });
    },
    events: { hide: function () { clearSelectionHighlight(); } }
  });

  // ctxCtx.userIds is the ordered list of selected resources (1 for a single row).
  function openMenuAt(userIds, startDate, endDate, pageX, pageY) {
    var r = snapRange(userIds[0], startDate, endDate);
    ctxCtx = { userIds: userIds, startISO: r.start, endISO: r.end, pageX: pageX, pageY: pageY };
    $('#vis-timeline').contextMenu({ x: pageX, y: pageY });
  }

  timeline.on('contextmenu', function (props) {
    if (readonly || props.group == null) return;
    props.event.preventDefault();
    openMenuAt([props.group], props.time, props.time, props.event.pageX, props.event.pageY);
  });

  // ---- Select mode: drag across rows + dates to choose a multi-resource range ----
  var selectMode = false;
  var sel = null;                 // { startGroup, startTime } while dragging
  var SEL_PREFIX = '__sel__';
  var selIds = [];
  var btnModePan = document.getElementById('btnModePan');
  var btnModeSelect = document.getElementById('btnModeSelect');

  function clearSelectionHighlight() {
    sel = null;
    if (selIds.length) { items.remove(selIds); selIds = []; }
  }

  function orderedGroupIds() {
    return groups.get()
      .sort(function (a, b) { return (a.order || 0) - (b.order || 0); })
      .map(function (g) { return g.id; });
  }

  function groupsBetween(g1, g2) {
    var ids = orderedGroupIds();
    var i1 = ids.indexOf(g1), i2 = ids.indexOf(g2);
    if (i1 < 0 || i2 < 0) return [g1];
    if (i1 > i2) { var t = i1; i1 = i2; i2 = t; }
    return ids.slice(i1, i2 + 1);
  }

  function paintSelection(groupIds, start, end) {
    if (selIds.length) { items.remove(selIds); selIds = []; }
    groupIds.forEach(function (gid) {
      var id = SEL_PREFIX + gid;
      selIds.push(id);
      items.add({ id: id, group: gid, start: start, end: end,
                  type: 'background', className: 'sched-selection' });
    });
  }

  function setSelectMode(on) {
    selectMode = on;
    timeline.setOptions({ moveable: !on });
    container.classList.toggle('selecting-mode', on);
    if (btnModeSelect) btnModeSelect.classList.toggle('active', on);
    if (btnModePan) btnModePan.classList.toggle('active', !on);
    if (!on) clearSelectionHighlight();
  }
  if (btnModePan) btnModePan.addEventListener('click', function () { setSelectMode(false); });
  if (btnModeSelect) btnModeSelect.addEventListener('click', function () { setSelectMode(true); });

  // Snap a raw drag (two arbitrary instants) to whole days. `start`/`endExclusive`
  // drive the highlight (full days); `lastDay` is the last selected day's midnight,
  // which snapRange turns into that day's working-hours end.
  function snapDays(a, b) {
    var lo = (a < b ? a : b), hi = (a < b ? b : a);
    return { start: startOfDay(lo), endExclusive: startOfNextDay(hi), lastDay: startOfDay(hi) };
  }

  timeline.on('mouseDown', function (props) {
    if (readonly || !selectMode) return;
    if (props.event.button !== 0) return;
    if (props.group == null || props.item != null) return;
    clearSelectionHighlight();
    sel = { startGroup: props.group, startTime: props.time };
    var d = snapDays(props.time, props.time);
    paintSelection([props.group], d.start, d.endExclusive);
  });

  timeline.on('mouseMove', function (props) {
    if (!selectMode || !sel || props.time == null) return;
    var d = snapDays(sel.startTime, props.time);
    var gids = (props.group != null) ? groupsBetween(sel.startGroup, props.group) : [sel.startGroup];
    paintSelection(gids, d.start, d.endExclusive);
  });

  timeline.on('mouseUp', function (props) {
    if (!selectMode || !sel) return;
    var d = snapDays(sel.startTime, (props.time || sel.startTime));
    var gids = (props.group != null) ? groupsBetween(sel.startGroup, props.group) : [sel.startGroup];
    sel = null;
    openMenuAt(gids, d.start, d.lastDay, props.event.pageX, props.event.pageY);
  });

  // ---- Refetch on pan/zoom (infinite scroll on time) ----
  var debounceTimer = null;
  timeline.on('rangechanged', function () {
    chooseAxisScale();
    pruneFar();
    renderUnloaded();
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(loadSlots, 250);
  });
  var unloadedRaf = null;
  timeline.on('rangechange', function () {
    if (unloadedRaf) return;
    unloadedRaf = requestAnimationFrame(function () {
      unloadedRaf = null;
      chooseAxisScale();
      renderUnloaded();
    });
  });

  // ---- Toolbar controls ----
  function on(id, fn) { var el = document.getElementById(id); if (el) el.addEventListener('click', fn); }
  on('btnZoomIn',  function () { timeline.zoomIn(0.5); });
  on('btnZoomOut', function () { timeline.zoomOut(0.5); });
  // Fit to the DATA AVAILABLE (backend bounds), not the loaded buffer — fitting
  // to the buffer makes repeated Fit creep outward as more data streams in.
  function fitToData() {
    loading(true);
    var url = slotsUrl + (slotsUrl.indexOf('?') >= 0 ? '&' : '?') + 'bounds=1' + (filterParams ? '&' + filterParams : '');
    $.ajax({
      url: url, method: 'GET',
      success: function (b) {
        if (b && b.start && b.end) {
          var s = new Date(b.start), e = new Date(b.end);
          var pad = 3 * 24 * 60 * 60 * 1000;   // 3 days each side
          timeline.setWindow(new Date(s.getTime() - pad), new Date(e.getTime() + pad));
        } else {
          timeline.fit();   // no data — fall back
        }
      },
      complete: function () { loading(false); }
    });
  }
  on('btnFit', fitToData);
  on('btnToday',   function () {
    var n = new Date();
    timeline.setWindow(new Date(n.getTime() - 7 * 24 * 60 * 60 * 1000),
                       new Date(n.getTime() + 35 * 24 * 60 * 60 * 1000));
  });
  Array.prototype.forEach.call(document.querySelectorAll('[data-zoom-weeks]'), function (btn) {
    btn.addEventListener('click', function () {
      var weeks = parseInt(btn.getAttribute('data-zoom-weeks'), 10);
      var center = new Date();
      var half = weeks * 7 * 24 * 60 * 60 * 1000 / 2;
      timeline.setWindow(new Date(center.getTime() - half), new Date(center.getTime() + half));
    });
  });

  // ---- Show/hide "other" (out-of-scope) slots — job/phase views only ----
  (function () {
    var grp = document.getElementById('grpToggleOthers');
    if (!grp) return;
    if (CFG.scope === 'global') { grp.hidden = true; return; }  // nothing out of scope globally
    grp.hidden = false;
    var btn = document.getElementById('btnToggleOthers');
    var icon = document.getElementById('btnToggleOthersIcon');
    function paint() {
      btn.classList.toggle('active', showOthers);
      if (icon) icon.className = (showOthers ? 'fas fa-eye' : 'fas fa-eye-slash') + ' me-1';
      btn.title = showOthers
        ? "Hide slots that aren't part of this job/phase"
        : "Show slots that aren't part of this job/phase";
    }
    paint();
    btn.addEventListener('click', function () {
      showOthers = !showOthers;
      localStorage.setItem('sched-show-others', showOthers ? '1' : '0');
      paint();
      loadSlots();
    });
  })();

  // ---- Live filtering: apply the offcanvas form without a full page reload (global) ----
  $('#settings-offcanvas').on('submit', 'form', function (e) {
    e.preventDefault();
    filterParams = $(this).serialize();
    history.replaceState(null, '', filterParams ? '?' + filterParams : location.pathname);
    groups.clear();
    items.clear();
    resetLoadedRanges();
    loadMembers();
    loadSlots();
    var oc = bootstrap.Offcanvas.getInstance(document.getElementById('settings-offcanvas'));
    if (oc) oc.hide();
    return false;
  });
  // The crispy "Reset to default" link points at /scheduler/ — send it there cleared.
  if (CFG.resetUrl) {
    $('#settings-offcanvas').on('click', 'a[href$="/scheduler/"]', function (e) {
      e.preventDefault();
      window.location = CFG.resetUrl;
    });
  }

  // ---- Sidebar schedule tools (job/phase-scoped pages only) ----
  // Clear schedule (all / by user / by role)
  $(document).on('click', '.js-clear-schedule', function (e) {
    e.preventDefault();
    if (!CFG.clearUrl) return;
    var clearType = $(this).data('clear-type') || 'all';
    var clearId = $(this).data('clear-id') || '';
    $.ajax({
      url: CFG.clearUrl + '?clear_type=' + clearType + '&clear_id=' + clearId,
      type: 'get', dataType: 'json',
      success: function (data) {
        if (data.count === 0) { Swal.fire('Nothing to clear', 'No matching timeslots found.', 'info'); return; }
        Swal.fire({
          title: 'Clear Schedule',
          html: 'Are you sure you want to clear <strong>' + data.count + '</strong> timeslot' + (data.count !== 1 ? 's' : '') + '?<br><span class="text-body-secondary">' + data.description + '</span>',
          icon: 'warning', showCancelButton: true, confirmButtonText: 'Clear', confirmButtonColor: '#e63757'
        }).then(function (result) {
          if (!result.isConfirmed) return;
          $.ajax({
            url: CFG.clearUrl, type: 'POST', dataType: 'json',
            data: { clear_type: clearType, clear_id: clearId, csrfmiddlewaretoken: csrf },
            success: function (data) {
              if (data.form_is_valid) {
                Swal.fire('Cleared', data.deleted + ' timeslot' + (data.deleted !== 1 ? 's' : '') + ' removed.', 'success');
                loadSlots(); loadMembers(); refreshCards();
              } else { Swal.fire('Error', 'Something went wrong.', 'error'); }
            }
          });
        });
      }
    });
  });

  // Schedule tools (reassign / shift / swap / onsite) — load modal
  $(document).on('click', '.js-load-schedule-tool, .js-load-move-slots-form', function (e) {
    e.preventDefault();
    var btn = $(this);
    $.ajax({
      url: btn.attr('data-url'), type: 'get', dataType: 'json',
      success: function (data) { $('#mainModalContent').html(data.html_form); $('#mainModal').modal('show'); }
    });
  });
  // Schedule tools — submit
  $('#mainModal').on('submit', '.js-schedule-tool-form', function () {
    var form = $(this);
    var btn = form.find('button[type="submit"]');
    if (form.data('submitting')) return false;
    form.data('submitting', true);
    btn.prop('disabled', true);
    $.ajax({
      url: form.attr('action'), data: form.serialize(), type: form.attr('method'), dataType: 'json',
      success: function (data) {
        if (data.form_is_valid) {
          $('#mainModal').modal('hide');
          loadSlots(); loadMembers(); refreshCards();
          var msg = data.message || ((data.moved || 0) + ' timeslot' + (data.moved !== 1 ? 's' : '') + ' moved.');
          Swal.fire('Done', msg, 'success');
        } else {
          form.data('submitting', false);
          $('#mainModalContent').html(data.html_form);
        }
      },
      error: function () {
        form.data('submitting', false); btn.prop('disabled', false);
        Swal.fire('Error', 'Something went wrong. Please try again.', 'error');
      }
    });
    return false;
  });

  // Add a user row to the scoped schedule (via the include_user param the
  // scoped members/slots endpoints honour).
  $(document).on('click', '#addUserToResource', function () {
    $('#id_user > option:selected').each(function () {
      if (this.value) filterParams += (filterParams ? '&' : '') + 'include_user=' + encodeURIComponent(this.value);
    });
    loadMembers();
    loadSlots();
    $('#addUserModal').modal('hide');
  });

  // Job/phase-scoped views open fitted to their data range rather than the
  // fixed today-centred window; the global scheduler keeps the today default.
  var scopedFit = (CFG.scope && CFG.scope !== 'global');
  var didScopedFit = false;

  // Redraw hook for embedding in an initially-hidden container (e.g. a Bootstrap
  // tab), where vis first renders at zero width. Call after the tab is shown.
  // Read-only embeds can't fit-to-data until they're visible, so do it on first reveal.
  window.__schedRedraw = function () {
    fitHeight();
    timeline.redraw();
    if (scopedFit && !didScopedFit) { didScopedFit = true; fitToData(); }
  };

  // =====================================================================
  // Version control (history + revert + Ctrl+Z) & live delta updates
  //   Every scheduler mutation commits one ScheduleAction on the server. The
  //   history panel lists them; revert/undo POST back; and open viewers of the
  //   same scope receive the action as a delta (WebSocket, else a ?since= poll)
  //   and apply it to the vis DataSet by pk — no full reload for observers.
  // =====================================================================
  var HIST = {
    listUrl: CFG.historyUrl,
    revertUrl: CFG.revertUrl,
    undoUrl: CFG.undoUrl,
    sinceUrl: CFG.sinceUrl
  };

  // Scope identifiers passed to the history/since endpoints & revert/undo bodies.
  function scopeData() {
    if (CFG.scope === 'job' && CFG.scopeId) return { job: CFG.scopeId };
    if (CFG.scope === 'phase' && CFG.scopeId) return { phase: CFG.scopeId };
    return {};
  }
  function scopeQuery() {
    var d = scopeData(), parts = [];
    for (var k in d) { if (d[k]) parts.push(k + '=' + encodeURIComponent(d[k])); }
    return parts.join('&');
  }

  function relTime(iso) {
    var then = new Date(iso).getTime();
    if (isNaN(then)) return '';
    var s = Math.round((Date.now() - then) / 1000);
    if (s < 60) return 'just now';
    var m = Math.round(s / 60); if (m < 60) return m + 'm ago';
    var h = Math.round(m / 60); if (h < 24) return h + 'h ago';
    var d = Math.round(h / 24); return d + 'd ago';
  }

  var ACTION_ICONS = {
    CREATE: 'fa-plus', UPDATE: 'fa-pen', DELETE: 'fa-trash',
    MOVE: 'fa-arrows-left-right', CLEAR: 'fa-eraser', BATCH: 'fa-layer-group',
    REVERT: 'fa-rotate-left'
  };

  function renderHistory(actions) {
    var $list = $('#sched-history-list');
    if (!$list.length) return;
    if (!actions.length) {
      $list.html('<p class="text-body-secondary small p-3 mb-0">No schedule changes recorded yet.</p>');
      return;
    }
    var html = actions.map(function (a) {
      var icon = ACTION_ICONS[a.action_type] || 'fa-clock-rotate-left';
      var revertBtn = a.can_revert
        ? '<button class="btn btn-sm btn-phoenix-secondary js-revert-action" data-action-id="' + a.id + '" title="Revert this change"><span class="fas fa-rotate-left me-1"></span>Revert</button>'
        : (a.reverted ? '<span class="badge badge-phoenix badge-phoenix-secondary">reverted</span>' : '');
      return '' +
        '<div class="d-flex align-items-start gap-2 px-3 py-2 border-bottom border-translucent' + (a.reverted ? ' opacity-50' : '') + '">' +
          '<span class="fas ' + icon + ' fs-9 text-body-secondary mt-1"></span>' +
          '<div class="flex-1 min-w-0">' +
            '<div class="fw-semibold fs-9 text-truncate">' + escapeHtml(a.summary) + '</div>' +
            '<div class="text-body-secondary fs-10">' + escapeHtml(a.actor) + ' · ' + relTime(a.created) + '</div>' +
          '</div>' +
          '<div class="ms-auto">' + revertBtn + '</div>' +
        '</div>';
    }).join('');
    $list.html(html);
  }

  function loadHistory() {
    if (!HIST.listUrl) return;
    var q = scopeQuery();
    $.get(HIST.listUrl + (q ? '?' + q : ''), function (data) {
      renderHistory((data && data.actions) || []);
    });
  }

  function afterCommit() {
    // The actor reconciles authoritatively; observers get the delta broadcast.
    loadHistory();
    if (!liveConnected) { loadSlots(); loadMembers(); }
    refreshCards();
  }

  function revertAction(id) {
    if (!HIST.revertUrl) return;
    loading(true);
    $.ajax({
      url: HIST.revertUrl, type: 'POST', dataType: 'json',
      data: $.extend({ pk: id, csrfmiddlewaretoken: csrf }, scopeData()),
      success: function (resp) {
        if (resp && resp.ok) { afterCommit(); }
        else { Swal.fire('Cannot revert', (resp && resp.error) || 'The change could not be reverted.', 'warning'); }
      },
      error: function () { Swal.fire('Error', 'Something went wrong reverting the change.', 'error'); },
      complete: function () { loading(false); }
    });
  }

  function undoLast() {
    if (!HIST.undoUrl) return;
    $.ajax({
      url: HIST.undoUrl, type: 'POST', dataType: 'json',
      data: $.extend({ csrfmiddlewaretoken: csrf }, scopeData()),
      success: function (resp) {
        if (resp && resp.ok) { afterCommit(); }
      }
    });
  }

  $(document).on('click', '#btnHistory', function () { loadHistory(); });
  $(document).on('click', '.js-revert-action', function () {
    revertAction($(this).data('action-id'));
  });
  $(document).on('shown.bs.offcanvas', '#history-offcanvas', loadHistory);

  // Ctrl/⌘+Z reverts the current user's most-recent own change in this scope.
  if (!readonly) {
    document.addEventListener('keydown', function (e) {
      if (!(e.ctrlKey || e.metaKey) || e.shiftKey || e.altKey) return;
      if (e.key !== 'z' && e.key !== 'Z') return;
      var t = e.target || {};
      var tag = (t.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select' || t.isContentEditable) return;
      if ($('.modal.show').length) return;
      e.preventDefault();
      undoLast();
    });
  }

  // ---- Live delta application (observer side) ----
  var appliedActions = {};      // action_ids applied here (echo suppression)
  var refreshTimer = null;
  function refreshDebounced() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(function () { refreshCards(); loadMembers(); loadHistory(); }, 400);
  }

  function applyDelta(delta) {
    if (!delta) return;
    if (delta.action_id) {
      if (appliedActions[delta.action_id]) return;   // already applied (own echo)
      appliedActions[delta.action_id] = true;
    }
    var touched = false;
    (delta.upserts || []).forEach(function (e) {
      // Skip background/holiday rows we didn't originate here.
      var mapped = mapEvent(e);
      items.update(mapped);
      touched = true;
    });
    (delta.removals || []).forEach(function (r) {
      var vid = (r.is_comment ? 'cmt-' : 'slot-') + r.id;
      if (items.get(vid)) { items.remove(vid); touched = true; }
    });
    if (touched) refreshDebounced();
  }

  // ---- WebSocket transport (with ?since= polling fallback) ----
  var liveConnected = false;
  var ws = null;
  var pollTimer = null;
  var lastPoll = new Date().toISOString();
  var wsRetry = null;

  function startPolling() {
    if (pollTimer || !HIST.sinceUrl) return;
    pollTimer = setInterval(function () {
      var q = scopeQuery();
      $.get(HIST.sinceUrl + '?since=' + encodeURIComponent(lastPoll) + (q ? '&' + q : ''),
        function (data) {
          if (!data) return;
          (data.deltas || []).forEach(applyDelta);
          if (data.now) lastPoll = data.now;
        });
    }, 5000);
  }
  function stopPolling() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }

  function connectWs() {
    if (!CFG.wsUrl || !('WebSocket' in window)) { startPolling(); return; }
    var proto = location.protocol === 'https:' ? 'wss://' : 'ws://';
    try { ws = new WebSocket(proto + location.host + CFG.wsUrl); }
    catch (err) { startPolling(); return; }
    ws.onopen = function () { liveConnected = true; stopPolling(); };
    ws.onmessage = function (ev) {
      try {
        var msg = JSON.parse(ev.data);
        if (msg && msg.type === 'delta') applyDelta(msg.delta);
      } catch (e) { /* ignore malformed frames */ }
    };
    ws.onclose = function () {
      liveConnected = false;
      startPolling();                       // degrade to polling while disconnected
      clearTimeout(wsRetry);
      wsRetry = setTimeout(connectWs, 8000); // and keep trying to restore the socket
    };
    ws.onerror = function () { try { ws.close(); } catch (e) {} };
  }
  connectWs();

  // ---- Initial load ----
  loadMembers();
  loadSlots();
  // Editable scoped pages (not hidden in a tab) can fit immediately; read-only
  // embeds defer to __schedRedraw above once their tab is shown.
  if (scopedFit && !readonly) { didScopedFit = true; fitToData(); }
})();
