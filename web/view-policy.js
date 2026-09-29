'use strict';
const MapwalkerView = Object.freeze({
  zoom(value) {
    return Number.isFinite(value) ? Math.max(5, Math.min(19, Math.round(value))) : 15;
  },
  error(detail, status) {
    if (status === 422) return 'That request could not be completed. Please try again.';
    if (status >= 500) return 'The map service is temporarily unavailable. Please try again.';
    return typeof detail === 'string' && detail.trim() && detail.length <= 180
      ? detail : 'Unable to complete this request. Please try again.';
  }
});
if (typeof module !== 'undefined') module.exports = MapwalkerView;
