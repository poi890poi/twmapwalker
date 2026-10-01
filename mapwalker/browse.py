"""Read-only selection shared by list, map and export. Never changes findings."""
import json
import math

from .geo import world
from .names import canonical_reading, informative, match_item, reading_options
from .display import VERSION, LEVELS, context_bounds, choose
from .visibility import HIDDEN_SQL

# Viewer and web discovery extent includes Matsu. Coordinate transforms remain
# the same; widening this UI boundary must not invalidate detector identities.
VIEW_BOUNDS = (118.0, 21.5, 123.0, 26.5)


def validate_view_bbox(bbox):
    if len(bbox) != 4 or not all(math.isfinite(v) for v in bbox):
        raise ValueError('Expected finite west,south,east,north bounds')
    w,s,e,n = bbox
    if not (118 <= w < e <= 123 and 21.5 <= s < n <= 26.5):
        raise ValueError('Bounds must lie in the Taiwan viewer region (118–123 E, 21.5–26.5 N)')
    return bbox


def view_tile_range(bbox, zoom):
    w,s,e,n = validate_view_bbox(bbox)
    left,top = world(w,n,zoom); right,bottom = world(e,s,zoom)
    return range(math.floor(left),math.ceil(right)), range(math.floor(top),math.ceil(bottom))


def view_tiles(bbox, zoom):
    xs,ys = view_tile_range(bbox,zoom)
    return ((zoom,x,y) for y in ys for x in xs)


def selection(db, bbox, source, disposition, query, kind, review, reading,include_trails=True,visibility='visible'):
    w, s, e, n = bbox
    args = [w, e, s, n]
    where = ["a.active=1", "j.state='complete'",
             'COALESCE(p.east,p.lon)>=?', 'COALESCE(p.west,p.lon)<=?',
             'COALESCE(p.north,p.lat)>=?', 'COALESCE(p.south,p.lat)<=?']
    if not include_trails:where.append("p.kind!='trail'")
    for column, value in [('t.source', source), ('p.disposition', disposition), ('p.kind', kind)]:
        if value and value != 'all':
            where.append(column + '=?'); args.append(value)
    sql = f'''WITH base AS (SELECT p.*,t.source,t.z,t.x,t.y,a.name algorithm,a.version,
        EXISTS(SELECT 1 FROM annotations WHERE poi_id=p.id) annotated,
        {HIDDEN_SQL} hidden,
        (SELECT verdict FROM reviews WHERE poi_id=p.id ORDER BY id DESC LIMIT 1) review,
        (SELECT value FROM readings WHERE poi_id=p.id ORDER BY id DESC LIMIT 1) reading,
        (SELECT status FROM readings WHERE poi_id=p.id ORDER BY id DESC LIMIT 1) reading_status
        FROM pois p JOIN jobs j ON j.id=p.job_id JOIN tiles t ON t.id=j.tile_id
        JOIN algorithms a ON a.fingerprint=j.algorithm WHERE ''' + ' AND '.join(where) + ')'
    filters = []
    if visibility not in ('visible','hidden','all'):raise ValueError('Unknown visibility filter')
    if visibility!='all':filters.append('hidden='+('1' if visibility=='hidden' else '0'))
    if review == 'unreviewed': filters.append('review IS NULL')
    elif review != 'all': filters.append('review=?'); args.append(review)
    if reading != 'all':
        db.create_function('has_reading', 3, lambda text, value, details:
                           bool(reading_options(dict(text=text, reading=value, details=details))))
        filters.append('has_reading(text,reading,details)=' + ('1' if reading == 'named' else '0'))
    sql += ', filtered AS (SELECT * FROM base' + (' WHERE '+' AND '.join(filters) if filters else '') + ') '
    search = canonical_reading(query)
    message = ''
    if search:
        # Materialize once per request: rank/filter all matches before paging,
        # and share exactly the same snapshot with the map and total.
        if not informative(search):
            sql += ', matches AS (SELECT *,NULL search_match FROM filtered WHERE 0) '
            message = 'Include at least one known character.'
        else:
            def match(text, value, details):
                result = match_item(search, dict(text=text, reading=value, details=details))
                return json.dumps(result, ensure_ascii=False) if result else None
            db.create_function('match_reading', 3, match)
            db.execute('CREATE TEMP TABLE search_results AS ' + sql + '''SELECT *,
                match_reading(text,reading,details) search_match FROM filtered''', args)
            sql, args = 'WITH matches AS (SELECT * FROM search_results WHERE search_match IS NOT NULL) ', []
    else:
        sql += ', matches AS (SELECT *,NULL search_match FROM filtered) '
    return sql, args, search, message


def browse(db, bbox, source=None, disposition='candidate', limit=500, offset=0,
           query='', kind='all', review='all', reading='all', sort='priority', zoom=None,
           display='all',display_zoom=15,include_trails=True,visibility='visible'):
    if display not in ('all',*LEVELS):raise ValueError('Unknown display level')
    area=context_bounds(bbox,display_zoom) if display!='all' else bbox
    sql, args, search, message = selection(db, area, source, disposition, query, kind, review, reading,include_trails,visibility)
    display_info=None
    if display!='all':
        db.execute('CREATE TEMP TABLE display_candidates AS '+sql+'SELECT * FROM matches',args)
        chosen,display_info=choose(db.execute('SELECT * FROM display_candidates'),bbox,display_zoom,display)
        db.execute('CREATE TEMP TABLE display_ids (id INTEGER PRIMARY KEY,display_priority REAL)')
        db.executemany('INSERT INTO display_ids VALUES(?,?)',chosen.items())
        sql='WITH matches AS (SELECT c.*,d.display_priority FROM display_candidates c JOIN display_ids d ON c.id=d.id) '
        args=[]
    total = db.execute(sql+'SELECT COUNT(*) FROM matches', args).fetchone()[0]
    # Preserve requested offsets for the legacy list API. The combined viewer
    # clamps a page that disappeared after filtering/background publication.
    if zoom is not None: offset = min(offset, max(0, (total-1)//limit*limit))
    db.create_function('display_name', 3, lambda text, value, details:
                       next(iter(reading_options(dict(text=text, reading=value, details=details))), ''))
    orders = {
        'priority': ("json_extract(search_match,'$.score') DESC,id" if search else
                     "CASE kind WHEN 'text' THEN 0 WHEN 'trail' THEN 1 ELSE 2 END,score DESC,id"),
        'name': "CASE WHEN display_name(text,reading,details)='' THEN 1 ELSE 0 END,display_name(text,reading,details) COLLATE NOCASE,id",
        'newest': 'id DESC', 'score': 'score DESC,id',
    }
    if display!='all' and sort=='priority':
        orders['priority']=("json_extract(search_match,'$.score') DESC," if search else '')+'display_priority DESC,id'
    if sort not in orders: raise ValueError('Unknown sort order')
    items = [dict(r) for r in db.execute(sql+'SELECT * FROM matches ORDER BY '+orders[sort]+' LIMIT ? OFFSET ?',args+[limit,offset])]
    for item in items:
        item['display_text'] = next(iter(reading_options(item)), '')
        if item['search_match']: item['search_match'] = json.loads(item['search_match'])
        else: item.pop('search_match')
    result = dict(total=total, items=items, offset=offset, limit=limit,visibility=visibility,
                  search_truncated=False, search_message=message,
                  display=display_info or dict(level='all',version=VERSION,available=total,shown=total,hidden=0))
    if zoom is not None:
        rows = db.execute(sql+'''SELECT id,kind,text,reading,details,lon,lat,
            west,south,east,north,disposition,annotated FROM matches''', args)
        result['map'] = map_features(rows, bbox, zoom)
    return result


def map_features(rows, bbox, zoom):
    """Bound payload size, preserving the count and extent of every finding."""
    points, groups, cell = [], {}, 64
    w, s, e, n = bbox

    def merge(a, b):
        count = a['count'] + b['count']
        a['lon'] = (a['lon']*a['count'] + b['lon']*b['count'])/count
        a['lat'] = (a['lat']*a['count'] + b['lat']*b['count'])/count
        a['count'] = count
        a['annotated_count'] += b['annotated_count']
        a['bounds'] = [min(a['bounds'][0], b['bounds'][0]), min(a['bounds'][1], b['bounds'][1]),
                       max(a['bounds'][2], b['bounds'][2]), max(a['bounds'][3], b['bounds'][3])]
        a['lon'] = min(a['bounds'][2], max(a['bounds'][0], a['lon']))
        a['lat'] = min(a['bounds'][3], max(a['bounds'][1], a['lat']))
        for kind, value in b['kinds'].items(): a['kinds'][kind] = a['kinds'].get(kind, 0)+value
        a.pop('item', None)

    def add(point):
        x, y = world(point['lon'], point['lat'], zoom)
        key = (math.floor(x*256/cell), math.floor(y*256/cell))
        group = dict(count=1, lon=point['lon'], lat=point['lat'], bounds=point['bounds'],
                     kinds={point['kind']: 1}, annotated_count=int(point['annotated']), item=point)
        if key in groups: merge(groups[key], group)
        else: groups[key] = group

    total, grouped = 0, False
    for row in rows:
        p = dict(row); total += 1
        details = json.loads(p['details'])
        point = dict(id=p['id'],kind=p['kind'],disposition=p['disposition'],annotated=bool(p.get('annotated',False)),
                     label=next(iter(reading_options(p)), ''),
                     # Crossing trails may have an anchor outside the viewport.
                     # Clip the display anchor only; stored coordinates stay intact.
                     lon=min(e,max(w,p['lon'])),lat=min(n,max(s,p['lat'])),
                     bounds=[max(w,p['west'] if p['west'] is not None else p['lon']),
                             max(s,p['south'] if p['south'] is not None else p['lat']),
                             min(e,p['east'] if p['east'] is not None else p['lon']),
                             min(n,p['north'] if p['north'] is not None else p['lat'])])
        if details.get('geometry'): point['geometry'] = details['geometry']
        if not grouped:
            points.append(point)
            if len(points) <= 3000: continue
            grouped = True
            for previous in points: add(previous)
            points = []
        else: add(point)
        while len(groups) > 2000:
            cell *= 2; coarser = {}
            for (x,y), group in groups.items():
                key = (x//2,y//2)
                if key in coarser: merge(coarser[key],group)
                else: coarser[key] = group
            groups = coarser
    return dict(total=total,mode='groups' if grouped else 'points',
                items=list(groups.values()) if grouped else points,cell_pixels=cell if grouped else None)
