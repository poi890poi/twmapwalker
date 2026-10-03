"""Conservative native-scale ring/stem evidence. Suggestions, never POI deletion."""
import math

import cv2
import numpy as np

VERSION = 'native-component-2'
NATIVE_ZOOM = 16


def analyze(image, box, zoom):
    """Return inspectable matches; absence of a match does not establish a POI."""
    if zoom != NATIVE_ZOOM:
        return dict(version=VERSION, status='unsupported-scale', matches=[])
    if len(box) != 4 or not all(math.isfinite(v) for v in box):
        raise ValueError('Invalid detection box')
    area_box = (box[2]-box[0])*(box[3]-box[1])
    if area_box <= 0:
        raise ValueError('Invalid detection box')
    gray = np.asarray(image.convert('L'))
    observations = []
    for threshold in (120, 145, 170):
        ink = (gray < threshold).astype('uint8')
        ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
        _, labels = cv2.connectedComponents(ink, connectivity=8)
        contours, hierarchy = cv2.findContours(ink, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        if hierarchy is None:
            continue
        for i, contour in enumerate(contours):
            parent = hierarchy[0][i][3]
            if parent < 0:
                continue
            hx, hy, hw, hh = cv2.boundingRect(contour)
            cx, cy = hx+(hw-1)/2, hy+(hh-1)/2
            if not (box[0] <= cx <= box[2] and box[1] <= cy <= box[3]):
                continue
            area = cv2.contourArea(contour)
            perimeter = cv2.arcLength(contour, True)
            if not (5 <= min(hw, hh) <= max(hw, hh) <= 13 and 10 <= area <= 100
                    and min(hw, hh)/max(hw, hh) >= .65
                    and 4*math.pi*area/max(1, perimeter**2) >= .60):
                continue
            px, py, pw, ph = cv2.boundingRect(contours[parent])
            if px <= 0 or py <= 0 or px+pw >= gray.shape[1] or py+ph >= gray.shape[0]:
                continue  # A clipped component is not an isolated symbol.
            above, below = hy-py, py+ph-(hy+hh)
            if not (np.sum(hierarchy[0, :, 3] == parent) == 1
                    and 9 <= pw <= 32 and 20 <= ph <= 40
                    and 2 <= above <= 10 and 4 <= below <= 20
                    and below >= above+2 and abs(px+pw/2-cx) <= 8):
                continue
            overlap = max(0, min(px+pw, box[2])-max(px, box[0])) * max(0, min(py+ph, box[3])-max(py, box[1]))
            coverage = overlap/area_box
            if coverage < .15:
                continue  # Incidental vegetation inside a large label is not its class.
            point = contours[parent][0, 0]
            component = labels[point[1], point[0]]
            mask = labels[py:py+ph, px:px+pw] == component
            stem = mask[max(0, hy+hh+1-py):min(ph, hy+hh+5-py),
                        max(0, round(cx)-1-px):min(pw, round(cx)+2-px)]
            if not stem.size or float(stem.mean()) < .45:
                continue
            observations.append(dict(threshold=threshold, center=[cx, cy],
                                     box=[px, py, px+pw, py+ph],
                                     hole=[hx, hy, hx+hw, hy+hh], coverage=coverage))
    matches = []
    for observation in observations:
        support = [r for r in observations if math.dist(r['center'], observation['center']) <= 2]
        thresholds = sorted({r['threshold'] for r in support})
        if len(thresholds) < 2 or any(math.dist(m['center'], observation['center']) <= 2 for m in matches):
            continue
        matches.append({**observation, 'thresholds': thresholds})
    return dict(version=VERSION, status='candidate' if matches else 'no-match', matches=matches[:4])
