// Drag tasks around
$(".drag").draggable({
  revert: "invalid",
  start: function (e, ui) {
    // Date from where task was dragged from
    $(this).data("oldDate", $(this).parent().data("date"));
  },
});

// Select drop area for Tasks (only droppable on TD which have "data-date" attribute)
$("td[data-date]").droppable({
  drop: function (e, ui) {
    var drag = ui.draggable,
      drop = $(this),
      oldDate = drag.data("oldDate"), // Task date on drag
      newDate = drop.data("date"), // Task date on drop
      dragID = drag.data("userid"), // Task userid on drag
      dropID = drop.data("userid"); // Task userid on drop
    if (oldDate != newDate || dragID != dropID) {
      $(drag).detach().css({ top: 0, left: 0 }).appendTo(drop);
      $(drag).data("userid", dropID); // Update task userid
    } else {
      return $(drag).css({ top: 0, left: 0 }); // Return task to old position
    }
  },
});

// show EDIT and TRASH tools
$(".drag").hover(
  function () {
    var isAdmin = 1; // Ability to hide or show edit and delete options
    if (isAdmin == 1) {
      $(this)
        .css("z-index", "999")
        .prepend(
          '<div class="opt-tools"><div class="opt-edit"><i class="fas fa-pen"></i></div><div class="opt-trash"><i class="fas fa-trash"></i></div></div>'
        );
    }
  },
  function () {
    //When mouse hovers out DIV remove tools
    $(this).css("z-index", "0").find(".opt-tools").remove();
  }
);

// Show modal to edit task
$(document).on("click", ".opt-edit", function () {
  // Get task ID and DATE from DATA attribute
  var taskid = $(this).parent().parent().data("taskid"),
    userid = $(this).parent().parent().data("userid");
  // Get DATE
  var date = $(this).closest("td").data("date");
  // insert data to Modal
  $("#ktxt")[0].jscolor.fromString("FFFFFF");
  $("#kbg")[0].jscolor.fromString("8E8E8E");
  $("#demotaak2").css("color", "#FFFFFF");
  $("#demotaak1").css("border-left-color", "#8E8E8E");
  $("#demotaak2").css("background-color", "#8E8E8E");
  $("#edittask").modal("show");
});

// Modal remove task ?
$(document).on("click", ".opt-trash", function () {
  var taskid = $(this).parent().parent().data("taskid");

  $("#taskdelid").val(taskid);
  $("#modal-delete").html(
    "Are you sure you want to delete task ID <b>" + taskid + "</b>?"
  );
  $("#deletetask").modal("show");
});

// Remove task after conformation
$(document).on("click", "#confdelete", function () {
  var taskid = $("#taskdelid").val();
  $("div")
    .find("[data-taskid=" + taskid + "]")
    .remove();
  $("#deletetask").modal("hide");
});

function changeColor(id, c) {
  if (id == "ctxt") {
    $("#demotaak2").css("color", "#" + c);
  } else if (id == "cbg") {
    $("#demotaak1").css("border-left-color", "#" + c);
    $("#demotaak2").css("background-color", "#" + c);
  }
  return false;
}
