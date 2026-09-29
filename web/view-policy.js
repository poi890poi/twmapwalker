'use strict';
const MapwalkerView = Object.freeze({
  zoom(value) {
    return Number.isFinite(value) ? Math.max(5, Math.min(19, Math.round(value))) : 15;
  },
  discovery(area) {
    const c=area.checks, pct=Math.floor(c.percent);
    const names={running:'Searching this view',queued:'Queued for this view',paused:'Discovery paused',failed:'Some checks failed',partial:'Partly searched',not_queued:'This view is not queued',complete:'Search complete in this view',interrupted:'Worker interrupted',unavailable:'Discovery unavailable'};
    const title=(names[area.state]||'Checking this view')+(c.total && !['complete','not_queued','unavailable'].includes(area.state)?` · ${pct}%`:'');
    const detail=`${c.complete.toLocaleString()} / ${c.total.toLocaleString()} checks · ${area.complete} / ${area.total} tiles`;
    const algorithms={'text':'Reading text','angled-text':'Reading rotated text','text-regions':'Finding text regions','symbols':'Finding symbols','junctions':'Checking intersections','trails':'Checking historical lines'};
    const current=area.current?`${algorithms[area.current.name]||'Processing'} · ${area.current.elapsed_seconds}s`:
      area.working_elsewhere && c.pending?'Other areas are processing':area.not_queued?`${area.not_queued} tiles not queued`:'';
    const queue=[c.pending?`${c.pending.toLocaleString()} waiting`:'',c.failed?`${c.failed} failed`:''].filter(Boolean).join(' · ');
    return {title,detail,current:[current,queue].filter(Boolean).join(' · '),percent:c.percent};
  },
  empty(area, result, hasFilters=false) {
    if(!area || !result || result.total)return {message:'',action:''};
    if(result.display.available>0)return {message:`${result.display.available.toLocaleString()} candidates are hidden by this display level.`,action:'all'};
    if(area.findings.candidates>0)return hasFilters?{message:`${area.findings.candidates.toLocaleString()} candidates do not match the current search or filters.`,action:'filters'}:{message:'New candidates are ready; updating this view…',action:''};
    if(area.state==='failed')return {message:'Some checks failed. Open Background work to retry; this is not a completed search.',action:'jobs'};
    if(area.state==='interrupted')return {message:'Processing was interrupted. These results are incomplete.',action:'jobs'};
    if(area.state==='paused')return {message:'Discovery is paused. Resume to continue searching this view.',action:''};
    if(['running','queued'].includes(area.state))return {message:'No candidates published here yet. Results will appear as checks finish.',action:''};
    if(area.not_queued)return {message:'This view has unsearched tiles. Use Find in this area to queue them.',action:''};
    if(area.findings.excluded>0)return {message:`${area.findings.excluded.toLocaleString()} proposals were excluded by detection filters.`,action:'excluded'};
    return {message:'Search complete, but no text/symbol candidates were detected. Real landmarks may still have been missed.',action:''};
  },
  error(detail, status) {
    if (status === 422) return 'That request could not be completed. Please try again.';
    if (status >= 500) return 'The map service is temporarily unavailable. Please try again.';
    return typeof detail === 'string' && detail.trim() && detail.length <= 180
      ? detail : 'Unable to complete this request. Please try again.';
  }
});
if (typeof module !== 'undefined') module.exports = MapwalkerView;
