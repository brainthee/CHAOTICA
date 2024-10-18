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
        if(this.value) {
          urlParams = urlParams+"&include_user="+this.value;
        }
      });
      calendar.refetchResources();
      calendar.refetchEvents();
    };

    $('#addUserToResource').click(addUser);

    function get_start_of_week(d) {
      d = new Date(d);
      var day = d.getDay(),
        diff = d.getDate() - day + (day == 0 ? -6 : 1); // adjust when day is sunday
      return new Date(d.setDate(diff));
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
        resourceOrder: 'first_name',
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
                    location.reload();
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
    