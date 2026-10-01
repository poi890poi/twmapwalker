"""Classification owns visibility; legacy manual choices remain recoverable."""

# Shared by detail, list, map, search, and export. Derive from the latest saved
# annotation so existing annotations and later corrections behave identically.
HIDDEN_SQL = """COALESCE((SELECT CASE json_extract(payload,'$.classification')
    WHEN 'poi' THEN 0 WHEN 'other' THEN 1 WHEN 'noise' THEN 1 END
    FROM annotations WHERE poi_id=p.id ORDER BY id DESC LIMIT 1),
    (SELECT hidden FROM poi_visibility WHERE poi_id=p.id ORDER BY id DESC LIMIT 1),0)"""
