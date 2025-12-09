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
        $('.modelselect2').select2({
            dropdownParent: $('#mainModal .modal-content')
        });
    });
    
    // Fix for select2 dropdowns in offcanvas panels
    $('#settings-offcanvas').on('shown.bs.offcanvas', function (e) {
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

    new DataTable('table.datatable', {
        {% include 'js/dtDefaultConfig.js' %}
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

    var saveForm = function() {
        var form = $(this);
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
                        location.reload();
                    }
                } else {
                    $("#mainModalContent").html(data.html_form);
                }
            }
        });
        return false;
    };

    var saveFileForm = function() {
        var form = $(this);
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
                        location.reload();
                    }
                } else {
                    $("#mainModalContent").html(data.html_form);
                }
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
                        location.reload();
                    }
                } else {
                    if (data.error) {
                        alert(data.error);
                    }
                    $("#mainModalContent").html(data.html_form);
                }
            },
            error: function(xhr, status, error) {
                alert('An error occurred while processing the bulk action.');
            }
        });
        return false;
    };

    var profileUpdateSkills = function() {
        var form = $(this);
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
                        location.reload();
                    }
                } else {
                    $("#mainModalContent").html(data.html_form);
                }
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
        // e.preventDefault();
        window.location.hash = $(this).attr("href");
    });


    let url = location.href.replace(/\/$/, "");    
    if (location.hash) {
        const hash = url.split("#");
        $('#sectionNav li a[href="#' + hash[1] + '"]').tab("show");
        // url = location.href.replace(/\/#/, "#");
        history.replaceState(null, null, url);
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
        
    let timeoutID = null;

    $('#searchField').keyup(function(e) {
        clearTimeout(timeoutID);
        const value = e.target.value
        timeoutID = setTimeout(() => search(value), 500)
    });

});

{% if config.KONAMI_ENABLED %}
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