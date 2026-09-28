import math

TAIWAN = (118.0, 21.5, 123.0, 26.0)


def validate_bbox(bbox):
    if len(bbox) != 4 or not all(math.isfinite(v) for v in bbox):
        raise ValueError('Expected finite west,south,east,north bounds')
    w, s, e, n = bbox
    if not (TAIWAN[0] <= w < e <= TAIWAN[2] and TAIWAN[1] <= s < n <= TAIWAN[3]):
        raise ValueError('Bounds must lie in the Taiwan study region (118–123 E, 21.5–26 N)')
    return bbox


def world(lon, lat, z):
    scale = 2 ** z
    return (lon + 180) / 360 * scale, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * scale


def lonlat(x, y, z):
    return x / 2 ** z * 360 - 180, math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / 2 ** z))))


def tile_range(bbox, z):
    validate_bbox(bbox)
    w, s, e, n = bbox
    left, top = world(w, n, z)
    right, bottom = world(e, s, z)
    return range(math.floor(left), math.ceil(right)), range(math.floor(top), math.ceil(bottom))


def tiles(bbox, z):
    xs, ys = tile_range(bbox, z)
    for y in ys:
        for x in xs:
            yield z, x, y


def pixel_lonlat(z, x, y, px, py):
    return lonlat(x + px / 256, y + py / 256, z)
