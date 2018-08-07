$(".sidebar-cl-entry a").click(function() {
    $(".sidebar-cl-entry").removeClass("active").addClass("deactive");
    $(this).parent().removeClass("deactive").addClass("active");
});

$(document).ready(function () {
    $(".sidebar-subcl").each(function() {
	$(this).css({height:$(this).height()});
    });
    $(".sidebar-cl-entry").addClass("deactive");
    $(".sidebar-subcl").show();
});

$(".sidebar-subcl-entry").click(function() {
    $(".sidebar-subcl-entry").removeClass("active");
    $(this).addClass("active");
});
