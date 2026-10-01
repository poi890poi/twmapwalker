'use strict';
(() => {
  let revision, pending = false, stopped = false;
  function editing() {
    const el = document.activeElement;
    return !!document.querySelector('dialog[open]') ||
      !!(el && (el.matches('input,textarea,select') || el.isContentEditable));
  }
  async function check() {
    try {
      const response = await fetch('/api/live-revision', {cache:'no-store'});
      if (!response.ok) return;
      const next = await response.json();
      if (!next.enabled) { stopped = true; return; }
      if (revision && next.revision !== revision) pending = true;
      revision = next.revision;
      if (pending && !document.hidden && !editing()) {
        // Existing view-state persistence retains map position, filters and layers.
        location.reload();
        stopped = true;
      }
    } catch (_) {
      // The Python child may be reloading; retry after it is ready.
    } finally {
      if (!stopped) setTimeout(check, 2000);
    }
  }
  check();
})();
