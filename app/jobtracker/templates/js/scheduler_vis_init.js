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
  function buildFormat(dayFmt) {
    return {
      minorLabels: {
        hour: 'HH:mm', weekday: 'ddd D', day: dayFmt || 'D',
        week: 'D MMM', month: 'MMM', year: 'YYYY'
      },
      majorLabels: MAJOR
    };
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
    editable: { updateTime: true, updateGroup: true, add: false, remove: false, overrideItems: false },
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
    var bottom = (footerEl ? footerEl.getBoundingClientRect().top : window.innerHeight);
    var h = Math.max(240, Math.floor(bottom - cTop - 8));
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
    var scale, dayFmt = null;
    if (ppd >= 55) { scale = 'day'; dayFmt = 'ddd D'; }    // roomy: weekday + number
    else if (ppd >= 16) { scale = 'day'; dayFmt = 'D'; }   // tight: number only
    else if (ppd >= 3.5) { scale = 'week'; }
    else if (ppd >= 0.6) { scale = 'month'; }
    else { scale = 'year'; }
    var key = scale + '|' + (dayFmt || '');
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
    return '<div class="sched-res">' +
             '<span class="meta">' +
               '<span class="name">' + name + '</span>' +
               (lvl ? '<span class="lvl">' + lvl + '</span>' : '') +
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
    return {
      id: idPrefix + e.id,
      group: e.resourceId,
      start: dispStart,
      end: dispEnd,
      content: icon + escapeHtml(e.title || ''),
      title: escapeHtml(buildTooltip(e)),
      className: e.is_comment ? 'cmt' : '',
      style: 'background-color:' + bg + '; color:' + fg + '; border-color:' + bg + ';',
      editable: e.can_edit ? { updateTime: true, updateGroup: true, remove: false } : false,
      _meta: {
        origId: e.id,
        isComment: !!e.is_comment,
        canEdit: !!e.can_edit,
        editUrl: e.edit_url,
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
      if (id === SEL_ID || id.indexOf('unloaded-') === 0) return;
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
        var mapped = data.map(mapEvent);
        var keep = {};
        mapped.forEach(function (m) { keep[m.id] = true; });
        var stale = items.getIds().filter(function (id) {
          id = String(id);
          if (id === SEL_ID || id.indexOf('unloaded-') === 0) return false;
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
            Swal.fire('Could not save', 'The change was rejected. Check overlaps / constraints.', 'warning');
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
    if (props.item == null) return;
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
    if (!url || !ctxCtx) return;
    loading(true);
    $.get(url + '?resource_id=' + parseInt(ctxCtx.group, 10) +
          '&start=' + encodeURIComponent(ctxCtx.startISO) +
          '&end=' + encodeURIComponent(ctxCtx.endISO) +
          createExtraParams,
      function (d) {
        $('#mainModalContent').html(d.html_form);
        $('#mainModal').modal('show');
      }).always(function () { loading(false); });
  }

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

  function openMenuAt(group, startDate, endDate, pageX, pageY) {
    var r = snapRange(group, startDate, endDate);
    ctxCtx = { group: group, startISO: r.start, endISO: r.end, pageX: pageX, pageY: pageY };
    $('#vis-timeline').contextMenu({ x: pageX, y: pageY });
  }

  timeline.on('contextmenu', function (props) {
    if (props.group == null) return;
    props.event.preventDefault();
    openMenuAt(props.group, props.time, props.time, props.event.pageX, props.event.pageY);
  });

  // ---- Select mode: drag across a row to choose a date range ----
  var selectMode = false;
  var sel = null;
  var SEL_ID = '__selection__';
  var btnModePan = document.getElementById('btnModePan');
  var btnModeSelect = document.getElementById('btnModeSelect');

  function clearSelectionHighlight() {
    sel = null;
    if (items.get(SEL_ID)) items.remove(SEL_ID);
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

  timeline.on('mouseDown', function (props) {
    if (!selectMode) return;
    if (props.event.button !== 0) return;
    if (props.group == null || props.item != null) return;
    clearSelectionHighlight();
    sel = { group: props.group, startTime: props.time };
    items.add({ id: SEL_ID, group: props.group, start: props.time, end: props.time,
                type: 'background', className: 'sched-selection' });
  });

  timeline.on('mouseMove', function (props) {
    if (!selectMode || !sel || props.time == null) return;
    var a = sel.startTime, b = props.time;
    items.update({ id: SEL_ID, group: sel.group,
                   start: (a < b ? a : b), end: (a < b ? b : a),
                   type: 'background', className: 'sched-selection' });
  });

  timeline.on('mouseUp', function (props) {
    if (!selectMode || !sel) return;
    var group = sel.group, a = sel.startTime, b = (props.time || sel.startTime);
    var s = (a < b ? a : b), e = (a < b ? b : a);
    sel = null;
    if (Math.abs(e - s) < 1000 * 60 * 30) e = s;
    openMenuAt(group, s, e, props.event.pageX, props.event.pageY);
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
  on('btnFit',     function () { timeline.fit(); });
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

  // Move slots — load modal
  $(document).on('click', '.js-load-move-slots-form', function () {
    var btn = $(this);
    $.ajax({
      url: btn.attr('data-url'), type: 'get', dataType: 'json',
      success: function (data) { $('#mainModalContent').html(data.html_form); $('#mainModal').modal('show'); }
    });
  });
  // Move slots — submit
  $('#mainModal').on('submit', '.js-schedule-tool-form', function () {
    var form = $(this);
    $.ajax({
      url: form.attr('action'), data: form.serialize(), type: form.attr('method'), dataType: 'json',
      success: function (data) {
        if (data.form_is_valid) {
          $('#mainModal').modal('hide');
          loadSlots(); loadMembers(); refreshCards();
          Swal.fire('Moved', data.moved + ' timeslot' + (data.moved !== 1 ? 's' : '') + ' moved.', 'success');
        } else { $('#mainModalContent').html(data.html_form); }
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

  // ---- Initial load ----
  loadMembers();
  loadSlots();
})();
