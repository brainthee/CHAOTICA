{% load index %}
    var calendarEl = document.getElementById('calendar');
    var csrf = $('input[name="csrfmiddlewaretoken"]');
    
    urlParams = window.location.search + "{% if phase %}&phases={{ phase.pk }}{% endif %}{% if job %}&jobs={{ job.pk }}{% endif %}{% if project %}&project={{ project.pk }}{% endif %}";
    
    if (urlParams.substring(0,1) != "?") {
      urlParams = "?" + urlParams;
    }

    var addUser = function() {
      var form = $(this);
      $("#id_user > option").each(function() {
        if(this.value && this.selected) {
          urlParams = urlParams+"&include_user="+this.value;
        }
      });
      calendar.refetchResources();
      calendar.refetchEvents();
      $("#addUserModal").modal("hide");
    };

    $('#addUserToResource').click(addUser);

    function get_start_of_week(d) {
      d = new Date(d);
      var day = d.getDay(),
        diff = d.getDate() - day + (day == 0 ? -6 : 1); // adjust when day is sunday
      return new Date(d.setDate(diff));
    }

    var utilUrl = "{% if phase %}{% url 'view_phase_schedule_util' phase.job.slug phase.slug %}{% elif job %}{% url 'view_job_schedule_util' job.slug %}{% endif %}";
    var phaseStatusUrl = "{% if job %}{% url 'view_job_schedule_phase_status' job.slug %}{% endif %}";
    var userBreakdownUrl = "{% if phase %}{% url 'view_phase_schedule_user_breakdown' phase.job.slug phase.slug %}{% elif job %}{% url 'view_job_schedule_user_breakdown' job.slug %}{% endif %}";

    function refreshUtilisation() {
      if (!utilUrl) return;
      var container = document.getElementById('schedule-util-container');
      if (!container) return;
      // Preserve toggle state
      var showDays = true;
      var checkbox = document.getElementById('utilDaysChecked');
      if (checkbox) showDays = checkbox.checked;
      $.get(utilUrl, function(html) {
        container.innerHTML = html;
        // Restore toggle state
        var newCheckbox = document.getElementById('utilDaysChecked');
        if (newCheckbox && !showDays) {
          newCheckbox.checked = false;
          toggleUtilUnit();
        }
      });
    }

    function refreshUserBreakdown() {
      if (!userBreakdownUrl) return;
      var container = document.getElementById('schedule-user-breakdown-container');
      if (!container) return;
      var showDays = true;
      var checkbox = document.getElementById('breakdownDaysChecked');
      if (checkbox) showDays = checkbox.checked;
      $.get(userBreakdownUrl, function(html) {
        container.innerHTML = html;
        var newCheckbox = document.getElementById('breakdownDaysChecked');
        if (newCheckbox && !showDays) {
          newCheckbox.checked = false;
          toggleBreakdownUnit();
        }
      });
    }

    function refreshPhaseStatus() {
      if (!phaseStatusUrl) return;
      var container = document.getElementById('schedule-phase-status-container');
      if (!container) return;
      $.get(phaseStatusUrl, function(html) {
        container.innerHTML = html;
        // Re-init tooltips in the refreshed content
        container.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function(el) {
          new bootstrap.Tooltip(el);
        });
      });
    }

    function getResources(fetchInfo, handleData) {
      $.ajax({
        url: "{% url 'view_scheduler_members' %}" + urlParams + "&start="+fetchInfo.startStr+"&end="+fetchInfo.endStr,
        method: 'GET',
        success:function(data) {
            handleData(data); 
        }
      });
    }

    function getEvents(fetchInfo, handleData) {
      $.ajax({
        url: "{% url 'view_scheduler_slots' %}" + urlParams + "&start="+fetchInfo.startStr+"&end="+fetchInfo.endStr,
        method: 'GET',
        success:function(data) {
            handleData(data); 
        }
      });
    }

    var calendar = new FullCalendar.Calendar(calendarEl, {
        schedulerLicenseKey: 'GPL-My-Project-Is-Open-Source',
        resourceOrder: '{% if filter_form.ordering_direction.value %}-{% endif %}{{ filter_form.ordering.value|default_if_none:"title" }}',
        resourceAreaColumns: [
          {
            field: 'html_view',
            headerContent: 'User',
            width: "70%",
          },
          {
            field: 'util',
            headerContent: 'Util',
            width: "30%",
            cellClassNames: "text-center",
            cellContent: function(arg) {
              return arg.resource.extendedProps.util+"%";
            },
          }
        ],
        firstDay: 1,
        initialView: 'resourceTimelineThreeMonth',
        themeSystem: 'bootstrap5',
        eventDisplay: "block",
        headerToolbar: {
            left: 'today prev,next',
            center: 'title',
            right: 'resourceTimelineMonth,resourceTimelineThreeMonth,resourceTimelineYear'
        },
        // {% py_date_to_js_date request.GET.from_date as from_date %}
        // {% if earliest_scheduled_date %}
        // {% py_date_to_js_date earliest_scheduled_date as earliest_scheduled_date_js %}
        initialDate: '{{ earliest_scheduled_date_js }}',
        // {% else %}
        // {% if from_date %}
        initialDate: '{{ from_date }}',
        // {% endif %}
        // {% endif %}
        nowIndicator: true,
        height: "100%",
        {% comment %} timeZone: '{{ user.pref_timezone }}', // the default (unnecessary to specify) {% endcomment %}
        views: {
          resourceTimelineThreeMonth: {
              type: 'resourceTimeline',
              duration: { months: 3 },
              buttonText: '3 Months'
          }
        },
        slotMinWidth: 150,
        displayEventTime: false,
        refetchResourcesOnNavigate: true,
        contentHeight: '100%',
        stickyHeaderDates: true,
        stickyFooterScrollbar : true,
        resourceAreaWidth: "300px",
        resourceAreaHeaderContent: 'Users',
        resourceLabelContent: function(info) {    
          return {html: info.resource.extendedProps.html_view};
        },
        eventDidMount: function(info) {
          var icon = info.event.extendedProps.icon;
          if (info.event.extendedProps.icon) {                  
            $(info.el).find('.fc-event-title').prepend("<i class='"+icon+" pe-1'></i> ");
          };
        },
        datesSet: function(dateInfo){
          start_of_week = get_start_of_week(new Date());
          const diffDays = Math.abs(start_of_week - dateInfo.start) / (1000 * 60 * 60 * 24);
          dateInfo.view.calendar.scrollToTime({days:diffDays});
        },
        lazyFetching: true,
        loading: function (isLoading) {
            if (isLoading) {
                $('#loading').show();
            }
            else {                
                $('#loading').hide();
            }
        },
        {% comment %} resources: {
            url: "{% url 'view_scheduler_members' %}" + urlParams,
            method: 'GET',
            failure: function() {
              Swal.fire({
                icon: 'error',
                title: 'Oops...',
                text: 'Something went wrong getting scheduler members!',
              })
            },
        },
        eventSources: {
            url: "{% url 'view_scheduler_slots' %}" + urlParams,
            method: 'GET',
            failure: function() {
              Swal.fire({
                icon: 'error',
                title: 'Oops...',
                text: 'Something went wrong getting scheduler members!',
              })
            },
        }, {% endcomment %}
        resources: function(fetchInfo, successCallback, failureCallback) {
          getResources(fetchInfo, function(resourceObjects) {
            successCallback(resourceObjects);
          });
        },
        eventSources: function(fetchInfo, successCallback, failureCallback) {
          getEvents(fetchInfo, function(resourceObjects) {
            successCallback(resourceObjects);
          });
        },        
        // {% if readonly %}
        selectable: false,
        editable: false,
        droppable: false,
        // {% else %}
        eventClick: function(info) {
          if(info.event.extendedProps.can_edit) {
            info.jsEvent.preventDefault(); // don't let the browser navigate
            // Show slot edit modal
            $.ajax({
              url: info.event.extendedProps.edit_url,
              type: 'get',
              dataType: 'json',
              success: function(data) {
                  $("#mainModalContent").html(data.html_form);
                  $("#mainModal").modal("show");
              }
            });
          };

        },
        selectable: true,
        editable: true,
        droppable: true,
        // {% endif %}
        select: function(info) {
          // get the selection info
          // https://swisnl.github.io/jQuery-contextMenu/
          $.contextMenu( 'destroy' );
          $.contextMenu({
            selector: '.fc-scroller', 
            zIndex: 10,
            reposition: false,
            trigger: 'none',
            build: function($triggerElement, e){
              return {
                callback: function(key, options) {
                  start_date_o = info.start.toJSON();
                  end_date_o = info.end.toJSON();

                  start_split = info.resource.extendedProps.workingHours.startTime.split(':')
                  info.start.setHours(start_split[0], start_split[1]);
                  start_date = info.start.toJSON();

                  end_split = info.resource.extendedProps.workingHours.endTime.split(':')
                  info.end.setHours(end_split[0], end_split[1]);
                  // Because of fullcalendar's date selection, we need to minus one day?!
                  info.end.setDate(info.end.getDate() - 1);
                  end_date = info.end.toJSON();
          
                  grr = info.end.toJSON();
                  resource_id = info.resource.id;
                  // {% if phase %}
                  phase_id = "&phase={{ phase.pk }}";
                  // {% else %}
                  phase_id = "";
                  // {% endif %}
                  // {% if job %}
                  job_id = "&job={{ job.pk }}";
                  // {% else %}
                  job_id = "";
                  // {% endif %}
                  // {% if project %}
                  project_id = "&project={{ project.pk }}";
                  // {% else %}
                  project_id = "";
                  // {% endif %}
                  // Lets open a modal window to setup the   
                  switch(key) {
                    case "assign_phase":
                      $.ajax({
                        url: '{% url "create_scheduler_phase_slot" %}?resource_id='+parseInt(resource_id)+'&start='+start_date+'&end='+end_date+job_id+phase_id,
                        type: 'get',
                        dataType: 'json',
                        success: function(data) {
                            $("#mainModalContent").html(data.html_form);
                            $("#mainModal").modal("show");
                        }
                      });
                      break;
                      case "assign_project":
                        $.ajax({
                          url: '{% url "create_scheduler_project_slot" %}?resource_id='+parseInt(resource_id)+'&start='+start_date+'&end='+end_date+project_id,
                          type: 'get',
                          dataType: 'json',
                          success: function(data) {
                              $("#mainModalContent").html(data.html_form);
                              $("#mainModal").modal("show");
                          }
                        });
                        break;
                    case "assign_internal":
                      $.ajax({
                        url: '{% url "create_scheduler_internal_slot" %}?resource_id='+parseInt(resource_id)+'&start='+start_date+'&end='+end_date,
                        type: 'get',
                        dataType: 'json',
                        success: function(data) {
                            $("#mainModalContent").html(data.html_form);
                            $("#mainModal").modal("show");
                        }
                      });
                      break;
                    case "add_comment":
                      $.ajax({
                        url: '{% url "create_scheduler_comment" %}?resource_id='+parseInt(resource_id)+'&start='+start_date+'&end='+end_date,
                        type: 'get',
                        dataType: 'json',
                        success: function(data) {
                            $("#mainModalContent").html(data.html_form);
                            $("#mainModal").modal("show");
                        }
                      });
                      break;
                    case "clear":
                      $.ajax({
                        url: '{% url "clear_scheduler_range" %}?resource_id='+parseInt(resource_id)+'&start='+start_date+'&end='+end_date,
                        type: 'get',
                        dataType: 'json',
                        success: function(data) {
                            $("#mainModalContent").html(data.html_form);
                            $("#mainModal").modal("show");
                        }
                      });
                      break;
                  } 
                  // Swal.fire({
                  //   title: "clicked: " + key,
                  //   icon: "success",
                  // });
                },
                position: function(opt, x, y){
                    opt.$menu.css({
                      top: info.jsEvent.pageY, 
                      left: info.jsEvent.pageX
                    });
                },
                items: {
                    "assign_phase": {name: "Assign phase", icon: "fas fa-cubes fs-8 me-2"},
                    "assign_project": {name: "Assign project", icon: "fas fa-diagram-project fs-8 me-2"},
                    "assign_internal": {name: "Assign internal", icon: "fas fa-briefcase fs-8 me-2"},
                    "add_comment": {name: "Add Comment", icon: "fas fa-comment fs-8 me-2"},
                    "clear": {name: "Clear Range", icon: "fas fa-eraser fs-8 me-2"},
                }
              };
            }
          });
          $('.fc-scroller').contextMenu();
        },
        eventDrop: function(info) {
          Swal.fire({
            title: 'Do you want to save the changes?',
            showCancelButton: true,
            confirmButtonText: 'Save',
          }).then((result) => {
            if (result.isConfirmed) {
              // Save the change...
              var slotData = {
                  "pk": info.event.id,
                  "start": info.event.start.toJSON(),
                  "end": info.event.end.toJSON(),
                  "user": info.event.extendedProps.userId,
                  "csrfmiddlewaretoken": csrf.val(),
                };
              if (info.newResource) {
                slotData['user'] = info.newResource.id;
              };
              if(info.event.extendedProps.is_comment) {
                change_url = '{% url "change_scheduler_slot_comment_date" %}'+info.event.id;
              } else {
                change_url = '{% url "change_scheduler_slot_date" %}'+info.event.id;
              };
              $.ajax({
                url: change_url,
                data: slotData,
                type: "POST",
                dataType: 'json',
                success: function(data) {
                  if (!data.form_is_valid) {
                    Swal.fire(
                      'Failed to modify',
                      'Something went wrong. Please check the data entered.',
                      'warning'
                    );    
                    info.revert();
                  } else {
                    calendar.refetchEvents();
                    refreshUtilisation();
                    refreshUserBreakdown();
                    refreshPhaseStatus();
                  }
                }
              });
            } else {
              info.revert();
            }
          });
        },
        eventResize: function(info) {
          Swal.fire({
            title: 'Do you want to save the changes?',
            showCancelButton: true,
            confirmButtonText: 'Save',
          }).then((result) => {
            if (result.isConfirmed) {          
              // Save the change...
              var slotData = {
                  "pk": info.event.id,
                  "start": info.event.start.toJSON(),
                  "end": info.event.end.toJSON(),
                  "user": info.event.extendedProps.userId,
                  "csrfmiddlewaretoken": csrf.val(),
                };
              if(info.event.extendedProps.is_comment) {
                change_url = '{% url "change_scheduler_slot_comment_date" %}'+info.event.id;
              } else {
                change_url = '{% url "change_scheduler_slot_date" %}'+info.event.id;
              };
              $.ajax({
                url: change_url,
                data: slotData,
                type: "POST",
                dataType: 'json',
                success: function(data) {
                  if (!data.form_is_valid) {
                    Swal.fire(
                      'Failed to modify',
                      'Something went wrong. Please check the data entered.',
                      'warning'
                    );    
                    info.revert();
                  } else {
                    calendar.refetchEvents();
                    refreshUtilisation();
                    refreshUserBreakdown();
                    refreshPhaseStatus();
                  }
                }
              });
            } else {
              info.revert();
            }
          });
        },
      });
    
    calendar.render();

    // --- Schedule Tools ---

    // Clear Schedule
    var clearUrl = "{% if phase %}{% url 'phase_schedule_clear' job.slug phase.slug %}{% elif job %}{% url 'job_schedule_clear' job.slug %}{% endif %}";

    $(document).on('click', '.js-clear-schedule', function(e) {
      e.preventDefault();
      if (!clearUrl) return;
      var clearType = $(this).data('clear-type') || 'all';
      var clearId = $(this).data('clear-id') || '';

      // GET to fetch count and description
      $.ajax({
        url: clearUrl + '?clear_type=' + clearType + '&clear_id=' + clearId,
        type: 'get',
        dataType: 'json',
        success: function(data) {
          if (data.count === 0) {
            Swal.fire('Nothing to clear', 'No matching timeslots found.', 'info');
            return;
          }
          Swal.fire({
            title: 'Clear Schedule',
            html: 'Are you sure you want to clear <strong>' + data.count + '</strong> timeslot' + (data.count !== 1 ? 's' : '') + '?<br><span class="text-body-secondary">' + data.description + '</span>',
            icon: 'warning',
            showCancelButton: true,
            confirmButtonText: 'Clear',
            confirmButtonColor: '#e63757',
          }).then(function(result) {
            if (result.isConfirmed) {
              $.ajax({
                url: clearUrl,
                type: 'POST',
                data: {
                  'clear_type': clearType,
                  'clear_id': clearId,
                  'csrfmiddlewaretoken': csrf.val(),
                },
                dataType: 'json',
                success: function(data) {
                  if (data.form_is_valid) {
                    Swal.fire('Cleared', data.deleted + ' timeslot' + (data.deleted !== 1 ? 's' : '') + ' removed.', 'success');
                    calendar.refetchEvents();
                    calendar.refetchResources();
                    refreshUtilisation();
                    refreshUserBreakdown();
                    refreshPhaseStatus();
                  } else {
                    Swal.fire('Error', 'Something went wrong.', 'error');
                  }
                }
              });
            }
          });
        }
      });
    });

    // Move Slots - load modal
    $(document).on('click', '.js-load-move-slots-form', function() {
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
    });

    // Move Slots - submit handler
    $("#mainModal").on("submit", ".js-schedule-tool-form", function() {
      var form = $(this);
      $.ajax({
        url: form.attr("action"),
        data: form.serialize(),
        type: form.attr("method"),
        dataType: 'json',
        success: function(data) {
          if (data.form_is_valid) {
            $("#mainModal").modal("hide");
            calendar.refetchResources();
            calendar.refetchEvents();
            refreshUtilisation();
            refreshUserBreakdown();
            refreshPhaseStatus();
            Swal.fire('Moved', data.moved + ' timeslot' + (data.moved !== 1 ? 's' : '') + ' moved.', 'success');
          } else {
            $("#mainModalContent").html(data.html_form);
          }
        }
      });
      return false;
    });
    