"""Read-only discovery status for the selected map area, not the global queue."""
import json
import time

from .browse import view_tile_range
from .sources import SOURCES


def area_progress(db, bbox, source):
    z = SOURCES[source]['max_zoom']
    xs, ys = view_tile_range(bbox, z)
    total = len(xs) * len(ys)
    algorithms = db.execute('SELECT COUNT(*) FROM algorithms WHERE active=1').fetchone()[0]
    scope = '''FROM tiles t JOIN jobs j ON j.tile_id=t.id
        JOIN algorithms a ON a.fingerprint=j.algorithm
        WHERE a.active=1 AND t.source=? AND t.z=? AND t.x>=? AND t.x<=? AND t.y>=? AND t.y<=?'''
    args = (source,z,xs.start,xs.stop-1,ys.start,ys.stop-1)
    row = db.execute('''WITH per_tile AS (SELECT t.id,
        SUM(j.state='complete') done,SUM(j.state='pending') pending,
        SUM(j.state='running') running,SUM(j.state='failed') failed '''+scope+'''
        GROUP BY t.id) SELECT COUNT(*) known,COALESCE(SUM(done=?),0) complete,
        COALESCE(SUM(done),0) done,COALESCE(SUM(pending),0) pending,
        COALESCE(SUM(running),0) running,COALESCE(SUM(failed),0) failed FROM per_tile''',
        (*args,algorithms)).fetchone()
    paused = json.loads(db.execute("SELECT value FROM settings WHERE key='paused'").fetchone()[0])
    current = db.execute('''SELECT a.name,t.x,t.y,j.lease_until,
        (SELECT started FROM attempts WHERE token=j.token LIMIT 1) started '''+scope+
        " AND j.state='running' ORDER BY j.id LIMIT 1",args).fetchone()
    if current:
        current = dict(current)
        current['elapsed_seconds'] = max(0,int(time.time()-(current.pop('started') or time.time())))
        current['stale'] = (current.pop('lease_until') or 0) < time.time()
    global_running = db.execute('''SELECT COUNT(*) FROM jobs j JOIN algorithms a
        ON a.fingerprint=j.algorithm WHERE a.active=1 AND j.state='running' ''').fetchone()[0]
    w,s,e,n = bbox
    findings = db.execute('''SELECT COALESCE(SUM(p.disposition='candidate'),0) candidates,
        COALESCE(SUM(p.disposition='excluded'),0) excluded
        FROM pois p JOIN jobs j ON j.id=p.job_id JOIN tiles t ON t.id=j.tile_id
        JOIN algorithms a ON a.fingerprint=j.algorithm
        WHERE a.active=1 AND j.state='complete' AND t.source=? AND p.kind!='trail'
        AND COALESCE(p.east,p.lon)>=? AND COALESCE(p.west,p.lon)<=?
        AND COALESCE(p.north,p.lat)>=? AND COALESCE(p.south,p.lat)<=?''',(source,w,e,s,n)).fetchone()
    expected = total * algorithms
    if not algorithms: state = 'unavailable'
    elif row['complete']==total: state = 'complete'
    elif paused and (row['pending'] or row['running']): state = 'paused'
    elif current and current['stale']: state = 'interrupted'
    elif row['running']: state = 'running'
    elif row['pending']: state = 'queued'
    elif row['failed']: state = 'failed'
    elif row['known']: state = 'partial'
    else: state = 'not_queued'
    return dict(total=total,complete=row['complete'],queued_or_running=row['known']-row['complete'],
        not_queued=total-row['known'],state=state,paused=paused,
        checks=dict(total=expected,complete=row['done'],pending=row['pending'],running=row['running'],
                    failed=row['failed'],not_queued=(total-row['known'])*algorithms,
                    percent=round(100*row['done']/expected,1) if expected else 0),
        current=current,working_elsewhere=bool(global_running and not row['running']),findings=dict(findings))


def plan_message(areas, added):
    checks = {key:sum(a['checks'][key] for a in areas) for key in ('complete','total','pending','running','failed')}
    if added:
        return f"Added {added:,} checks to the queue. Results appear as checks finish."
    if all(a['state']=='complete' for a in areas):
        count = sum(a['findings']['candidates'] for a in areas)
        return (f"Search complete: {count:,} text/symbol candidates. Display settings may hide some." if count else
                'Search complete: no text/symbol candidates detected. Real landmarks may still have been missed.')
    if any(a['paused'] for a in areas) and (checks['pending'] or checks['running']):
        return 'Already queued; discovery is paused. Resume to continue.'
    return (f"Already queued: {checks['complete']:,}/{checks['total']:,} checks complete, "
            f"{checks['pending']:,} waiting, {checks['running']} running, {checks['failed']} failed. "
            + ('Open Background work to retry failures.' if checks['failed'] else 'Not finished yet.'))
