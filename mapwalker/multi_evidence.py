"""Conservative counterpart hypotheses, never labels or POI probabilities.

Only raw automatic readings enter inference. Annotation/link data is deliberately
absent from this interface. Modern sources can disagree or share provenance.
"""
import math
import re

from .names import canonical_reading, informative, match_name, reading_options, search_key
from .osm import distance_m

VERSION = 'multi-evidence-1'
RADIUS_M = 1000
GENERIC = set('山峰嶺岳川溪河湖社庄村郡市町道路')
TYPE_HINTS = {'山': {'peak'}, '峰': {'peak'}, '嶺': {'peak','saddle'},
              '溪': {'stream','river'}, '川': {'stream','river'},
              '社': {'hamlet','village','locality'}}


def raw_readings(poi):
    # Do not pass the full POI to reading_options: that would prefer manual text.
    return reading_options(dict(text=poi.get('text',''), details=poi.get('details',{})))


def aliases(feature):
    p=feature['properties']; values={p.get('name','')}
    values.update(p.get('aliases',[]))
    for key,value in p.get('tags',{}).items():
        if key.split(':')[0] in {'name','old_name','alt_name','official_name','short_name'}:
            values.update(str(value).split(';'))
    return sorted({canonical_reading(v) for v in values if v})


def elevation(value):
    text=canonical_reading(str(value))
    if not re.fullmatch(r'\d{1,4}(?:[.,]\d{1,2})?\s*(?:m|公尺)?',text):return None
    value=float(re.sub(r'\s*(m|公尺)$','',text).replace(',','.'))
    return value if 0<=value<=5000 else None


def name_evidence(readings, feature):
    matches=[]
    for reading in readings:
        key=search_key(reading)
        # A generic suffix such as 山 cannot identify one of several peaks.
        if len(informative(key))<2 or not (informative(key)-GENERIC) or elevation(key) is not None:continue
        for alias in aliases(feature):
            result=match_name(key,alias)
            if result is None:continue
            # Short fuzzy strings match almost anything. Keep exact fragments;
            # tolerate one edit only with >=4 known characters and >=3 shared.
            exact=result['reason'] in ('exact','contains')
            fuzzy=(len(informative(key))>=4 and result['distance']<=1 and
                   len(informative(key)&informative(alias))>=3)
            if exact or fuzzy:
                matches.append(dict(reading=reading,alias=alias,**result))
    return max(matches,key=lambda m:(m['score'],len(search_key(m['reading'])))) if matches else None


def analyze(poi, features, terrain=None, coverage=None):
    """Pure inference except the optional local terrain sampler; no DB/network."""
    readings=raw_readings(poi)
    numbers=sorted({n for r in readings if (n:=elevation(r)) is not None})
    hints=set().union(*(TYPE_HINTS.get(r[-1:],set()) for r in readings))
    ranked=[];seen=set()
    for feature in features:
        p=feature['properties'];geometry=feature['geometry']
        identity=(p.get('provider','osm'),p.get('osm_type','record'),p.get('osm_id',p.get('record_id')))
        if identity in seen:continue
        seen.add(identity)
        distance=distance_m(geometry,poi['lon'],poi['lat'])
        if not math.isfinite(distance) or distance>RADIUS_M:continue
        tags=p.get('tags',{})
        kind=tags.get('natural') or tags.get('waterway') or tags.get('place') or tags.get('man_made','')
        match=name_evidence(readings,feature)
        height=elevation(tags.get('ele',''))
        numeric=[dict(reading_m=n,modern_m=height,difference_m=round(abs(n-height),1))
                 for n in numbers if height is not None and abs(n-height)<=max(15,.01*height)]
        terrain_result=None
        if terrain and geometry['type']=='Point' and (match or numeric or kind in ('peak','saddle','survey_point')):
            terrain_result=terrain.point(*geometry['coordinates'])
        # Numeric agreement stays a hypothesis: units and contour/spot identity
        # are unverified, even if both modern height sources agree.
        evidence=[]
        if match:evidence.append(dict(channel='name',**match))
        if kind in hints:evidence.append(dict(channel='type',value=kind,meaning='Generic map character; not identity'))
        if numeric:evidence.append(dict(channel='elevation',comparisons=numeric,meaning='Assuming the historical number is metres; contour or spot unresolved'))
        terrain_agrees=False
        if terrain_result and terrain_result['state']=='available':
            if height is not None:
                terrain_agrees=abs(terrain_result['elevation_m']-height)<=max(30,.02*height)
            evidence.append(dict(channel='terrain',**terrain_result,modern_height_compatible=terrain_agrees if height is not None else None))
        elif terrain_result:
            evidence.append(dict(channel='terrain',**terrain_result))
        ranked.append(dict(feature=feature,distance_m=round(distance),name_match=match,
                           evidence=evidence,numeric_compatible=bool(numeric),
                           support='name-supported' if match else 'elevation-compatible' if numeric else 'context-only',
                           _rank=(match['score'] if match else 0, bool(numeric), terrain_agrees and bool(numeric),kind in hints,-distance)))
    ranked.sort(key=lambda c:c['_rank'],reverse=True)
    supported=[c for c in ranked if c['name_match']]
    # Duplicate representations in OSM and the gazetteer are not extra votes.
    # Separate nearby names can remain competing candidates even at equal score.
    competing=[]
    if supported:
        best=supported[0]
        for other in supported[1:]:
            a,b=best['feature'],other['feature']
            same_place=(a['geometry']['type']==b['geometry']['type']=='Point' and
                        distance_m(a['geometry'],*b['geometry']['coordinates'])<=150 and
                        bool({search_key(v) for v in aliases(a)}&{search_key(v) for v in aliases(b)}))
            if not same_place:competing.append(other)
    state='ambiguous' if competing else 'name-supported' if supported else 'elevation-compatible' if any(c['numeric_compatible'] for c in ranked) else 'unknown'
    for candidate in ranked:candidate.pop('_rank')
    return dict(version=VERSION,state=state,raw_readings=readings,radius_m=RADIUS_M,
                candidates=ranked[:12],total=len(ranked),truncated=len(ranked)>12,
                competing_name_matches=len(competing),coverage=coverage or {},
                note='Hypotheses, not confirmation. Label placement, map drift and changed names are unresolved. Modern sources may share data; agreement is not an independent vote.',
                numeric_note='A matching height cannot distinguish a contour label from a peak or survey elevation. Historical units are unverified.' if numbers else None)
