"""Uncertainty-aware matching. Scores are ranking aids, never name probabilities."""
import unicodedata

UNKNOWN = '?'


def canonical_reading(value):
    value = unicodedata.normalize('NFKC', value).strip()
    return ''.join(UNKNOWN if c in '?〓�' else c for c in value)


def search_key(value):
    value = canonical_reading(value).casefold()
    return ''.join(chr(ord(c)+0x60) if '\u3041'<=c<='\u3096' else c
                   for c in value if not c.isspace())


def informative(value):
    return {c for c in search_key(value) if c != UNKNOWN and c.isalnum()}


def match_name(query, reading):
    """Semi-global weighted edit distance: query may match part of a longer name."""
    q, text = search_key(query), search_key(reading)
    if not q or not text or not (informative(q) & informative(text)):
        return None
    if q == text and UNKNOWN not in q:
        return dict(score=1.0, reason='exact', distance=0.0)
    if UNKNOWN not in q and q in text:
        return dict(score=.99, reason='contains', distance=0.0)
    # Free leading/trailing candidate context; unknown matches exactly one character.
    previous = [0.0]*(len(text)+1)
    for i,a in enumerate(q,1):
        row = [float(i)]
        for j,b in enumerate(text,1):
            cost = .2 if UNKNOWN in (a,b) else 0.0 if a==b else 1.0
            row.append(min(previous[j]+1,row[j-1]+1,previous[j-1]+cost))
        previous = row
    distance = min(previous[1:])
    allowance = min(3,max(1,len(q)//4)) if len(informative(q))>=3 else .4
    if distance > allowance + 1e-9:
        return None
    return dict(score=round(max(0,1-distance/len(q)),4),
                reason='unknown-character' if UNKNOWN in q+text and distance<1 else 'similar-spelling',
                distance=round(distance,4))


def reading_options(item):
    """A user reading overrides recognition; raw alternatives remain in evidence."""
    if item.get('reading'):
        return [canonical_reading(item['reading'])]
    import json
    details=item.get('details') or {}
    if isinstance(details,str):details=json.loads(details)
    values=[item.get('text','')]+[r.get('text','') for r in details.get('reading_candidates',[])]
    return list(dict.fromkeys(canonical_reading(v) for v in values if v))


def match_item(query,item):
    matches=[dict(**m,matched_reading=value) for value in reading_options(item)
             if (m:=match_name(query,value))]
    if not matches:return None
    best=max(matches,key=lambda m:m['score'])
    proposal=canonical_reading(query)
    if (UNKNOWN not in proposal and len(search_key(proposal))>=len(search_key(best['matched_reading']))
            and search_key(proposal)!=search_key(best['matched_reading'])):
        best['suggested_name']=proposal
        best['suggestion_source']='Your search; unverified'
    return best
