$(function() {

    new DataTable('table.datatable', {
        info: true,
        ordering: true,
        paging: true,
        "aLengthMenu": [[25, 50, 75, -1], [25, 50, 75, "All"]],
        "pageLength": 25
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

    $(".js-update-job-workflow").click(loadWorkflowConf);
    $(".js-update-phase-workflow").click(loadWorkflowConf);
    $(".js-load-modal-form").click(loadForm);
    $("#mainModal").on("submit", ".js-workflow-phase-form", saveForm);
    $("#mainModal").on("submit", ".js-workflow-job-form", saveForm);
    $("#mainModal").on("submit", ".js-submit-modal-form", saveForm);

    $('.theme-control-toggle-input').change(function(){
        var modeVal = "light";
        if(this.checked) {
            modeVal = "dark";
        }
        $.get('{% url 'update_own_theme' %}', {mode:modeVal}, function (data, textStatus, jqXHR) {});
    });

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

    var polling = true;
    var period = 60 * 1000; // every 60 seconds

    var interval = polling && setInterval(function() {
    if (polling) {
        $.ajax({
            url: "{% url 'notifications_feed' %}",
            type: 'get',
            dataType: 'json',
            success: function(data) {
                $("#navbarDropdownNotfication").html(data.html_form);
            },
        });
    } else {
        if (interval) {
        clearInterval(interval);
        }
    }
    }, period);

});