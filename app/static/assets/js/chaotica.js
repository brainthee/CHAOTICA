function onKonamiCode(cb) {
    var input = '';
    var key = '38384040373937396665';
    document.addEventListener('keydown', function (e) {
      input += ("" + e.keyCode);
      if (input === key) {
        return cb();
      }
      if (!key.indexOf(input)) return;
      input = ("" + e.keyCode);
    });
}

const tooltipInit = () => {
  const tooltipTriggerList = [].slice.call(
    document.querySelectorAll('[data-bs-tooltip="tooltip"]')
  );

  tooltipTriggerList.map(
    tooltipTriggerEl =>
      new bootstrap.Tooltip(tooltipTriggerEl, {
        trigger: 'hover'
      })
  );
};