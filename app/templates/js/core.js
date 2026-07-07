{% load static %}

// Function to GET csrftoken from Cookie
function getCookie(name) {
    var cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var cookie = jQuery.trim(cookies[i]);
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

var csrftoken = getCookie('csrftoken');

function csrfSafeMethod(method) {
    // these HTTP methods do not require CSRF protection
    return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));
}

// Function to set Request Header with `CSRFTOKEN`
function setRequestHeader(){
    $.ajaxSetup({
        beforeSend: function(xhr, settings) {
            if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
                xhr.setRequestHeader("X-CSRFToken", csrftoken);
            }
        }
    });
}

$(document).ready(function() {        
    $('#mainModal').on('shown.bs.modal', function (e) {
        // select2 is only present on pages that load a select2 form's media.
        if ($.fn.select2) {
            $('.modelselect2').select2({
                dropdownParent: $('#mainModal .modal-content')
            });
        }
    });

    // Fix for select2 dropdowns in offcanvas panels
    $('#settings-offcanvas').on('shown.bs.offcanvas', function (e) {
        if (!$.fn.select2) {
            return;
        }
        $('.select2-widget').select2({
            dropdownParent: $('#settings-offcanvas .offcanvas-body')
        });
        // Re-initialize select2 for any newly loaded content
        $('#settings-offcanvas .offcanvas-body').on('DOMNodeInserted', '.select2-widget', function() {
            $(this).select2({
                dropdownParent: $('#settings-offcanvas .offcanvas-body')
            });
        });
    });
});

$(function() {

    const dt = new DataTable('table.datatable', {
        {% include 'js/dtDefaultConfig.js' %}
    });
    dt.tables().every(function () {
        const th = this.table().header().querySelector('th.default-sort');
        if (!th) return;
        this.order([th.cellIndex, th.classList.contains("sort-desc") ? 'desc' : 'asc']).draw();
    });

    var loadForm = function() {
        var btn = $(this);
        $.ajax({
            url: btn.attr("data-url"),
            type: 'get',
            dataType: 'json',
            success: function(data) {
                $("#mainModalContent").html(data.html_form);
                $("#mainModal").modal("show");
            }
        });
    };

    var loadWorkflowConf = function() {
        var btn = $(this);
        statusID = btn.attr("data-status-id");
        status = btn.attr("data-status");
        $.ajax({
            url: btn.attr("data-url"),
            type: 'get',
            dataType: 'json',
            // beforeSend: function () {
            // },
            success: function(data) {
                $("#mainModalContent").html(data.html_form);
                if (statusID == 10) {
                    $("#closeAlert").show();
                }
                $("#newStatusInt").val(statusID);
                $("#newStatus").text(status);
                $("#mainModal").modal("show");
            }
        });
    };

    function reloadWithTabContext() {
        const activeLink = document.querySelector('#sectionNav .nav-link.active');
        const tabTarget = activeLink
            ? (activeLink.getAttribute('href') || activeLink.getAttribute('data-bs-target') || '')
            : '';
        if (tabTarget && tabTarget !== '#') {
            sessionStorage.setItem('chaotica.restoreTab', tabTarget);
        }
        location.reload();
    }

    // Guard modal forms against double-submission (e.g. slow clone operations).
    // Returns false if the form is already in flight so callers can bail out.
    var lockSubmit = function(form) {
        if (form.data("submitting")) {
            return false;
        }
        form.data("submitting", true);
        var btn = form.find('button[type="submit"]');
        if (btn.length) {
            btn.data("orig-html", btn.html());
            btn.prop("disabled", true).html(
                '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Working&hellip;'
            );
        }
        return true;
    };

    var unlockSubmit = function(form) {
        form.data("submitting", false);
        var btn = form.find('button[type="submit"]');
        if (btn.length && btn.data("orig-html") !== undefined) {
            btn.prop("disabled", false).html(btn.data("orig-html"));
        }
    };

    var saveForm = function() {
        var form = $(this);
        var submit = function() {
            if (!lockSubmit(form)) {
                return;
            }
            $.ajax({
                url: form.attr("action"),
                data: form.serialize(),
                type: form.attr("method"),
                dataType: 'json',
                success: function(data) {
                    if (data.form_is_valid) {
                        if (data.next) {
                            location.href = data.next
                        } else {
                            reloadWithTabContext();
                        }
                    } else {
                        $("#mainModalContent").html(data.html_form);
                    }
                },
                error: function() {
                    unlockSubmit(form);
                    Swal.fire({
                        title: "Something went wrong",
                        text: "The action could not be completed. Please try again.",
                        icon: "error"
                    });
                }
            });
        };
        // Some transitions (e.g. marking a job as Lost) cancel phases and clear
        // their scheduled slots. Force an explicit acknowledgement first.
        if (form.data("confirm-clear-slots")) {
            var phaseCount = form.data("phase-count");
            var slotCount = form.data("slot-count");
            Swal.fire({
                title: "Clear scheduled work?",
                html: "This will cancel <strong>" + phaseCount + "</strong> phase(s) and permanently remove <strong>" + slotCount + "</strong> scheduled slot(s) from the schedule.<br><br>This cannot be undone.",
                icon: "warning",
                showCancelButton: true,
                confirmButtonText: "Yes, cancel phases & clear schedule",
                cancelButtonText: "No, keep them",
                customClass: { confirmButton: "btn btn-danger", cancelButton: "btn btn-light" },
                buttonsStyling: false
            }).then(function(result) {
                if (result.isConfirmed) {
                    submit();
                }
            });
            return false;
        }
        submit();
        return false;
    };

    var saveFileForm = function() {
        var form = $(this);
        if (!lockSubmit(form)) {
            return false;
        }
        var formData = new FormData(this);
        $.ajax({
            url: form.attr("action"),
            data: formData,
            type: form.attr("method"),
            dataType: 'json',
            processData: false,  // tell jQuery not to process the data
            contentType: false,  // tell jQuery not to set contentType
            success: function(data) {
                if (data.form_is_valid) {
                    if (data.next) {
                        location.href = data.next
                    } else {
                        reloadWithTabContext();
                    }
                } else {
                    $("#mainModalContent").html(data.html_form);
                }
            },
            error: function() {
                unlockSubmit(form);
                Swal.fire({
                    title: "Something went wrong",
                    text: "The upload could not be completed. Please try again.",
                    icon: "error"
                });
            }
        });
        return false;
    };

    var saveBulkWorkflowForm = function() {
        var form = $(this);
        var selectedPhases = form.find('input[name="phase_ids[]"]:checked');

        if (selectedPhases.length === 0) {
            alert('Please select at least one phase to update.');
            return false;
        }
        if (!lockSubmit(form)) {
            return false;
        }
        $.ajax({
            url: form.attr("action"),
            data: form.serialize(),
            type: form.attr("method"),
            dataType: 'json',
            success: function(data) {
                if (data.form_is_valid) {
                    if (data.next) {
                        location.href = data.next
                    } else {
                        reloadWithTabContext();
                    }
                } else {
                    if (data.error) {
                        alert(data.error);
                    }
                    $("#mainModalContent").html(data.html_form);
                }
            },
            error: function(xhr, status, error) {
                unlockSubmit(form);
                alert('An error occurred while processing the bulk action.');
            }
        });
        return false;
    };

    var profileUpdateSkills = function() {
        var form = $(this);
        if (!lockSubmit(form)) {
            return false;
        }
        $.ajax({
            url: form.attr("action"),
            data: form.serialize(),
            type: form.attr("method"),
            dataType: 'json',
            success: function(data) {
                if (data.form_is_valid) {
                    if (data.next) {
                        location.href = data.next
                    } else {
                        reloadWithTabContext();
                    }
                } else {
                    $("#mainModalContent").html(data.html_form);
                }
            },
            error: function() {
                unlockSubmit(form);
                Swal.fire({
                    title: "Something went wrong",
                    text: "The action could not be completed. Please try again.",
                    icon: "error"
                });
            }
        });
        return false;
    };

    var readNotifications = function() {
        var btn = $(this);
        $.ajax({
            url: btn.attr("data-url"),
            type: 'get',
            dataType: 'json',
            success: function(data) {
                if (data.result) {
                    location.reload();
                }
            }
        });        
    };

    $(".js-update-job-workflow").click(loadWorkflowConf);
    $(".js-update-phase-workflow").click(loadWorkflowConf);
    $(".js-bulk-workflow-phases").click(loadWorkflowConf);
    $(".js-load-modal-form").click(loadForm);
    $(".datatable").on("click", ".js-load-modal-form", loadForm);
    $("#mainModal").on("submit", ".js-workflow-phase-form", saveForm);
    $("#mainModal").on("submit", ".js-workflow-job-form", saveForm);
    $("#mainModal").on("submit", ".js-bulk-workflow-phases-form", saveBulkWorkflowForm);
    $("#mainModal").on("submit", ".js-submit-modal-form", saveForm);
    $("#mainModal").on("submit", ".js-submit-file-modal-form", saveFileForm);
    

    const themeController = document.body;

    themeController.addEventListener(
      "clickControl",
      ({ detail: { control, value } }) => {    
        if (control === "phoenixTheme") {
          const mode = value === 'auto' ? window.phoenix.utils.getSystemTheme() : value;
          $.get('{% url 'update_own_theme' %}', {mode:value}, function (data, textStatus, jqXHR) {});
        }
      }
    );

    $("#sectionNav li .nav-link").click(function(e) {
        const target = $(this).attr("href") || $(this).attr("data-bs-target");
        if (target && target !== '#') window.location.hash = target;
    });

    let url = location.href.replace(/\/$/, "");
    const _savedTab = sessionStorage.getItem('chaotica.restoreTab');
    if (_savedTab) sessionStorage.removeItem('chaotica.restoreTab');
    const _activeHash = (_savedTab || location.hash || '').replace('#', '');
    if (_activeHash) {
        const _sel = '#sectionNav li a[href="#' + _activeHash + '"], #sectionNav li a[data-bs-target="#' + _activeHash + '"]';
        $(_sel).tab("show");
        history.replaceState(null, null, url.split('#')[0] + '#' + _activeHash);
        setTimeout(() => {
            $(window).scrollTop(0);
        }, 400);
    }


    var search = function(str) {
        setRequestHeader();
        $.ajax({
            url: "{% url 'search' %}",
            type: 'POST',
            dataType: 'json',
            data: {
                "q": str,
            },
            params: { // extra parameters that will be passed to ajax
                contentType: "application/json; charset=utf-8",
            },
            success: function(data) {
                $("#searchResultContainer").html(data.html_form);
            }
        });
    };
        
    // Resolve a typed Job ID / Phase ID straight to its page. On a hit we
    // navigate there; on a miss we do nothing and leave the normal search
    // results dropdown in place.
    var searchGoto = function(str) {
        setRequestHeader();
        $.ajax({
            url: "{% url 'search_goto' %}",
            type: 'GET',
            dataType: 'json',
            data: {
                "q": str,
            },
            success: function(data) {
                if (data.url) {
                    window.location = data.url;
                }
            }
        });
    };

    // Job IDs are plain digits ("1234"); Phase IDs are "1234-1".
    const idLikePattern = /^\d+(-\d+)?$/;

    let timeoutID = null;

    $('#searchField').keyup(function(e) {
        clearTimeout(timeoutID);
        const value = e.target.value
        timeoutID = setTimeout(() => search(value), 500)
    });

    $('#searchField').keydown(function(e) {
        if (e.key === 'Enter' || e.keyCode === 13) {
            // The search box has no submit target — stop Enter reloading the page.
            e.preventDefault();
            const value = e.target.value.trim();
            if (idLikePattern.test(value)) {
                searchGoto(value);
            }
        }
    });

});

{% if config.EASTEREGG_GAMES_ENABLED %}
jQuery(document).ready(function($){
    window.CHAOS_AUDIO_URL = "{% static 'assets/data/holodeck-laugh.mp3' %}";
    ChaosGames.initMenu();
});
{% elif config.KONAMI_ENABLED %}
jQuery(document).ready(function($){

    var data = localStorage.safetyProtocols;
    if (data == "true") {
        $("html").addClass("holodeck");
    }

    onKonamiCode(function () {
        var audioElement = document.createElement('audio');
        audioElement.setAttribute('src', "{% static 'assets/data/holodeck-laugh.mp3' %}");
        audioElement.play();


        var data = localStorage.safetyProtocols;
        var spTitlePrefix = "Disengaging"
        if (data == "true") {
            $("html").removeClass("holodeck");
            localStorage.safetyProtocols = "";
            spTitlePrefix = "Engaging"
        } else {
            $("html").addClass("holodeck");
            localStorage.safetyProtocols = "true";
        }

        let timerInterval;
        Swal.fire({
        title: "Warning",
        html: spTitlePrefix+" holodeck safety protocols...",
        timer: 10000,
        backdrop: `
            rgba(0,0,123,0.4)
            url("{% static 'assets/img/Chaotical.jpg' %}")
            100%
        `,
        timerProgressBar: true,
        didOpen: () => {
            Swal.showLoading();
        },
        willClose: () => {
            clearInterval(timerInterval);
        }
        }).then((result) => {
        /* Read more about handling dismissals below */
        if (result.dismiss === Swal.DismissReason.timer) {
            console.log("I was closed by the timer");
        }
        });

    });
});


{% endif %}

{% if config.ENTROPY_METER_ENABLED %}
jQuery(document).ready(function ($) {
    var artifact = document.getElementById('entropyArtifact');
    if (!artifact) return;

    var entropyData = null;

    // Level -> accent colour for the gauge/level label.
    var LEVEL_COLOUR = { calm: '#4caf72', elevated: '#e0b000', high: '#e8833a', critical: '#d9534f' };
    var FLAVOUR = {
        calm: 'Systems nominal.',
        elevated: 'A manageable amount of chaos.',
        high: 'Entropy is winning.',
        critical: 'Contain the breach.'
    };
    // Per-category dot colour.
    var FACTOR_COLOUR = {
        delivery_overdue: '#d9534f', job_overdue: '#d9534f',
        tqa_overdue: '#e0a800', pqa_overdue: '#e0a800',
        no_techqa: '#d98a2b', no_presqa: '#d98a2b',
        unscheduled: '#5b8def'
    };

    // Self-contained styles injected once, so the egg renders correctly
    // regardless of whether the compiled stylesheet has been recollected.
    function injectStyles() {
        if (document.getElementById('entropyStyles')) return;
        var css = ''
            + '#entropyArtifact{cursor:pointer;opacity:.28;font-size:.85em;vertical-align:-.05em;margin-left:.35rem;color:inherit;transition:opacity .4s,color .4s,text-shadow .4s;outline:none;user-select:none}'
            + '#entropyArtifact:hover,#entropyArtifact:focus-visible{opacity:.85}'
            + '#entropyArtifact.lvl-elevated{opacity:.4}'
            + '#entropyArtifact.lvl-high{color:#d98a2b;opacity:.5;animation:entPulseHi 3.2s ease-in-out infinite}'
            + '#entropyArtifact.lvl-critical{color:#d9534f;opacity:.55;animation:entPulseCrit 2.2s ease-in-out infinite}'
            + '@keyframes entPulseHi{0%,100%{opacity:.32;text-shadow:none}50%{opacity:.72;text-shadow:0 0 6px rgba(217,138,43,.55)}}'
            + '@keyframes entPulseCrit{0%,100%{opacity:.4;text-shadow:none}50%{opacity:.9;text-shadow:0 0 8px rgba(217,83,79,.65)}}'
            + '@media(prefers-reduced-motion:reduce){#entropyArtifact.lvl-high,#entropyArtifact.lvl-critical{animation:none}}'
            + '.ent-panel{text-align:left;font-size:.9rem;padding-top:.25rem}'
            + '.ent-head{text-align:center;text-transform:uppercase;letter-spacing:.14em;font-size:.66rem;opacity:.6;margin-bottom:.35rem}'
            + '.ent-gaugewrap{text-align:center;margin-bottom:.15rem}'
            + '.ent-lvl{text-align:center;text-transform:uppercase;letter-spacing:.14em;font-size:.72rem;font-weight:700}'
            + '.ent-flavour{text-align:center;font-style:italic;opacity:.7;margin-bottom:.9rem}'
            + '.ent-sub{text-align:center;font-size:.78rem;opacity:.65;margin:-.55rem 0 .9rem}'
            + '.ent-factors{display:flex;flex-direction:column;gap:.1rem;margin-bottom:.5rem}'
            + '.ent-factor{display:flex;align-items:center;gap:.55rem;padding:.28rem .1rem;border-bottom:1px solid rgba(128,138,158,.14)}'
            + '.ent-factor:last-child{border-bottom:0}'
            + '.ent-dot{width:.62rem;height:.62rem;border-radius:50%;flex:0 0 auto}'
            + '.ent-flabel{flex:1}'
            + '.ent-badge{font-variant-numeric:tabular-nums;font-weight:700;background:rgba(128,138,158,.18);border-radius:.6rem;padding:.05rem .55rem;min-width:1.9rem;text-align:center}'
            + '.ent-clear{text-align:center;opacity:.7;margin:.4rem 0 .9rem}'
            + '.ent-trend-head{display:flex;justify-content:space-between;font-size:.72rem;opacity:.6;margin-bottom:.3rem}'
            + '.ent-trend{display:flex;align-items:flex-end;gap:4px;height:46px}'
            + '.ent-bar{flex:1;background:rgba(128,138,158,.3);border-radius:3px 3px 0 0;min-height:3px;transition:height .3s}'
            + '.ent-bar.hot{background:#d9534f}'
            + '.ent-arc{transition:stroke-dasharray 1.1s cubic-bezier(.2,.7,.2,1)}'
            + '@keyframes entShake{10%,90%{transform:translateX(-2px)}20%,80%{transform:translateX(3px)}30%,50%,70%{transform:translateX(-5px)}40%,60%{transform:translateX(5px)}}'
            + '.ent-shake{animation:entShake .5s cubic-bezier(.36,.07,.19,.97)}'
            + '@keyframes entGlitch{0%,100%{text-shadow:none;transform:none}20%{text-shadow:-2px 0 #d9534f,2px 0 #4fd2d9;transform:translateX(-1px)}40%{text-shadow:2px 0 #d9534f,-2px 0 #4fd2d9;transform:translateX(1px)}60%{text-shadow:-1px 0 #d9534f,1px 0 #4fd2d9}}'
            + '.ent-glitch{animation:entGlitch .45s steps(2) 2}'
            + '.ent-flash{position:fixed;inset:0;pointer-events:none;z-index:20000;background:radial-gradient(circle at 50% 45%,rgba(217,83,79,.3),transparent 62%);animation:entFlash .82s ease-out forwards}'
            + '@keyframes entFlash{0%{opacity:0}14%{opacity:1}100%{opacity:0}}'
            + '@media(prefers-reduced-motion:reduce){.ent-arc{transition:none}.ent-shake,.ent-glitch,.ent-flash{animation:none}}';
        var style = document.createElement('style');
        style.id = 'entropyStyles';
        style.textContent = css;
        document.head.appendChild(style);
    }
    injectStyles();

    fetch("{% url 'entropy_status' %}", { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) {
            if (!d) return;
            entropyData = d;
            artifact.classList.add('lvl-' + d.level);
            artifact.title = 'System entropy: ' + d.score + '% (' + d.level + ')';
        })
        .catch(function () {});

    function gaugeSvg(score, colour) {
        // r chosen so the circumference is ~100 -> dasharray "score 100" == score%.
        // Arc + number start at 0 and are animated up in openPanel's didOpen.
        return '<svg width="128" height="128" viewBox="0 0 36 36" role="img">'
            + '<circle cx="18" cy="18" r="15.9155" fill="none" stroke="rgba(128,138,158,.18)" stroke-width="3.2"/>'
            + '<circle class="ent-arc" cx="18" cy="18" r="15.9155" fill="none" stroke="' + colour + '" stroke-width="3.2"'
            +   ' stroke-linecap="round" style="stroke-dasharray:0 100" transform="rotate(-90 18 18)"/>'
            + '<text id="entGaugeNum" x="18" y="19.4" text-anchor="middle" font-size="10" font-weight="700" fill="' + colour + '">0</text>'
            + '</svg>';
    }

    function buildPanel(d) {
        var colour = LEVEL_COLOUR[d.level] || '#4caf72';

        var body = d.factors.length
            ? '<div class="ent-factors">' + d.factors.map(function (f) {
                  var c = FACTOR_COLOUR[f.key] || '#888';
                  return '<div class="ent-factor">'
                      + '<span class="ent-dot" style="background:' + c + '"></span>'
                      + '<span class="ent-flabel">' + f.label + '</span>'
                      + '<span class="ent-badge">' + f.count + '</span></div>';
              }).join('') + '</div>'
            : '<div class="ent-clear">All clear. Nothing overdue &mdash; suspiciously calm.</div>';

        var total = d.trend.reduce(function (a, b) { return a + b; }, 0);
        var max = Math.max.apply(null, d.trend.concat([1]));
        var bars = d.trend.map(function (c) {
            var h = c > 0 ? Math.max(Math.round((c / max) * 100), 12) : 3;
            return '<div class="ent-bar' + (c > 0 ? ' hot' : '') + '" style="height:' + h + '%" title="' + c + ' late"></div>';
        }).join('');

        var sub = d.alarm_count
            ? '<div class="ent-sub">' + d.alarm_count + ' item' + (d.alarm_count === 1 ? '' : 's') + ' need attention</div>'
            : '';

        return '<div class="ent-panel">'
            + '<div class="ent-head">operational chaos level</div>'
            + '<div class="ent-gaugewrap">' + gaugeSvg(d.score, colour) + '</div>'
            + '<div class="ent-lvl" style="color:' + colour + '">' + d.level + '</div>'
            + '<div class="ent-flavour">' + (FLAVOUR[d.level] || '') + '</div>'
            + sub
            + body
            + '<div class="ent-trend-head"><span>Late deliveries &middot; last ' + d.trend_weeks + ' weeks</span><span>' + total + ' total</span></div>'
            + '<div class="ent-trend">' + bars + '</div>'
            + '</div>';
    }

    function animateReveal(popup) {
        var d = entropyData;
        var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        var arc = popup.querySelector('.ent-arc');
        var num = popup.querySelector('#entGaugeNum');

        if (reduce) {
            if (arc) arc.style.strokeDasharray = d.score + ' 100';
            if (num) num.textContent = d.score;
            return;
        }

        if (arc) requestAnimationFrame(function () { arc.style.strokeDasharray = d.score + ' 100'; });
        if (num && d.score > 0) {
            var start = performance.now(), dur = 1000;
            (function tick(t) {
                var p = Math.min(1, (t - start) / dur);
                num.textContent = Math.round(p * d.score);
                if (p < 1) requestAnimationFrame(tick);
            })(start);
        }

        // A bit of drama once things are genuinely on fire. NB: shake the inner
        // panel, never the Swal popup itself — animating the popup's transform
        // leaves a residual that breaks Swal's close animation (modal won't clear).
        if (d.level === 'high' || d.level === 'critical') {
            var panel = popup.querySelector('.ent-panel');
            if (panel) panel.classList.add('ent-shake');
            var lvl = popup.querySelector('.ent-lvl');
            if (lvl) lvl.classList.add('ent-glitch');
            if (d.level === 'critical') {
                var flash = document.createElement('div');
                flash.className = 'ent-flash';
                document.body.appendChild(flash);
                setTimeout(function () { if (flash.parentNode) flash.parentNode.removeChild(flash); }, 840);
            }
        }
    }

    function removeFlash() {
        var f = document.querySelector('.ent-flash');
        if (f && f.parentNode) f.parentNode.removeChild(f);
    }

    function openPanel() {
        if (!entropyData || typeof Swal === 'undefined') return;
        Swal.fire({
            html: buildPanel(entropyData),
            width: 400,
            showConfirmButton: true,
            confirmButtonText: 'Dismiss',
            showCloseButton: true,
            didOpen: animateReveal,
            willClose: removeFlash
        });
    }

    artifact.addEventListener('click', openPanel);
    artifact.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openPanel(); }
    });
});
{% endif %}