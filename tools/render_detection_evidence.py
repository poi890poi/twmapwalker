"""Deterministic review figures from immutable pixels and saved proposals; no inference."""
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evidence/detection-round2'
FOLDER = OUT / 'visual-evidence'
BG = '#f7f6ef'
INK = '#173e35'
BLUE = '#1260d4'
TEAL = '#00786b'
PURPLE = '#833bd0'
GREEN = '#188034'


def font(size, bold=False):
    return ImageFont.truetype('C:/Windows/Fonts/seguisb.ttf' if bold else 'C:/Windows/Fonts/segoeui.ttf', size)


def wrapped(draw, text, xy, width, size=20):
    x, y = xy
    face = font(size)
    line = ''
    for word in text.split():
        candidate = (line + ' ' + word).strip()
        if draw.textlength(candidate, font=face) > width and line:
            draw.text((x, y), line, fill=INK, font=face)
            y += size + 9
            line = word
        else:
            line = candidate
    draw.text((x, y), line, fill=INK, font=face)
    return y + size + 9


def dashed(draw, points, fill, width=2, dash=8):
    import math
    phase = 0
    for a, b in zip(points, points[1:]):
        distance = math.dist(a, b)
        if distance == 0:
            continue
        steps = max(1, int(distance))
        for i in range(steps):
            if (phase // dash) % 2 == 0:
                p = tuple(a[j] + (b[j] - a[j]) * i / steps for j in (0, 1))
                q = tuple(a[j] + (b[j] - a[j]) * (i + 1) / steps for j in (0, 1))
                draw.line([p, q], fill=fill, width=width)
            phase += 1


def keep(p):
    return not p.get('repeating') or p.get('details', {}).get('trail_context')


def rows(method, split, scene):
    path = OUT / (method + '-' + split + '.jsonl')
    row = next(r for r in map(json.loads, path.read_text('utf-8').splitlines()) if r['scene'] == scene)
    return [p for p in row['proposals'] if keep(p)], path


def panel(image, crop, scale, proposals=(), refs=(), trace=None):
    # Nearest-neighbor enlargement preserves native pixels. No sharpening/inpainting.
    im = image.crop(crop).resize(((crop[2]-crop[0])*scale, (crop[3]-crop[1])*scale), Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(im)
    def point(p):
        return ((p[0]-crop[0])*scale, (p[1]-crop[1])*scale)
    for p in proposals:
        if p['kind'] == 'trail':
            draw.line([point(v) for v in p['details']['pixel_path']], fill=PURPLE, width=2)
        else:
            x, y, x1, y1 = p['box']
            draw.rectangle([point((x,y)), point((x1,y1))], outline=TEAL if p['kind']=='symbol' else BLUE, width=2)
    for ref in refs:
        x,y,x1,y1 = ref['box']
        pts = [point(p) for p in [(x,y),(x1,y),(x1,y1),(x,y1),(x,y)]]
        dashed(draw, pts, GREEN, 2)
    if trace:
        dashed(draw, [point(p) for p in trace], GREEN, 2)
    return im


def figure(filename, title, subtitle, source, crop, scale, columns, legend, conclusion):
    im = Image.open(source).convert('RGB')
    width = (crop[2]-crop[0])*scale
    height = (crop[3]-crop[1])*scale
    gap, margin = 22, 24
    total_width = 2*margin+len(columns)*width+(len(columns)-1)*gap
    canvas = Image.new('RGB', (total_width, height+340), BG)
    draw = ImageDraw.Draw(canvas)
    y = wrapped(draw, title, (margin,20), total_width-2*margin, 30)
    y = wrapped(draw, subtitle, (margin,y+3), total_width-2*margin, 18)
    top = y+54
    for i, (label, kwargs) in enumerate(columns):
        left = margin+i*(width+gap)
        draw.text((left, top-36), label, fill=INK, font=font(21, True))
        canvas.paste(panel(im,crop,scale,**kwargs),(left,top))
        draw.rectangle((left,top,left+width,top+height),outline='#ccd4c8',width=1)
    y = wrapped(draw, legend, (margin,top+height+18), total_width-2*margin, 19)
    y = wrapped(draw, conclusion, (margin,y+6), total_width-2*margin, 21)
    canvas = canvas.crop((0,0,total_width,y+20))
    path=FOLDER/filename
    canvas.save(path)
    return dict(file=str(path.relative_to(OUT)),source=str(source.relative_to(ROOT)),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),crop_native_pixels=crop,display_scale=scale,output_sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def main():
    FOLDER.mkdir(exist_ok=True)
    suite=json.loads((OUT/'inputs.json').read_text('utf-8'))['scenes']
    marks=json.loads((ROOT/'evidence/symbol-first/references.json').read_text('utf-8'))['marks']
    artifacts=[];inputs=set()
    def get(scene, split, method):
        ps,path=rows(method,split,scene);inputs.add(path);return ps
    def source(scene):
        s=next(s for s in suite if s['id']==scene)
        path=(OUT/s['path']).resolve()
        assert hashlib.sha256(path.read_bytes()).hexdigest()==s['sha256']
        return path

    scene='JM50K_1924_new-vertical'
    before=get(scene,'development','craft-base');after=get(scene,'development','craft-compact')
    artifacts.append(figure('01-text-before-after.png','Text: the first glyph now has a proposal',
        '1924 map | z16 / 54896 / 28092 | identical source crop in all three panels',source(scene),[62,81,149,352],3,
        [('Original pixels',{}),('Before',dict(proposals=before)),('After',dict(proposals=after))],
        'Blue = actual saved text-region boxes. The source pixels are enlarged without enhancement.',
        'The new top box localizes the user-identified first glyph. This is detection only: no reading was produced.'))

    scene='JM50K_1924_new-fresh-southwest'
    before=get(scene,'fresh','trails-base');after=get(scene,'fresh','trails-safe')
    trace=json.loads((OUT/'fresh-references.json').read_text('utf-8'))['paths'][0]['points']
    artifacts.append(figure('02-trails-before-after.png','Trails: fewer false-looking cross-links, but the path is still mostly missed',
        '1924 map | z16 / 54894 / 28094 | same full padded tile',source(scene),[0,0,384,384],1,
        [('Original pixels',{}),('Before',dict(proposals=before,trace=trace)),('After',dict(proposals=after,trace=trace))],
        'Purple = saved trail segments. Dashed green = manually traced review path, never used by the detector.',
        'Cross-links on the left disappear. Many remaining purple segments still follow contours; this is not a recovered route.'))

    scene='JM50K_1924_new-symbols'
    before=get(scene,'development','symbols-base');alternative=get(scene,'development','symbols-thick')
    refs=[m for m in marks if m['scene']==scene]
    artifacts.append(figure('03-symbols-unresolved.png','Symbols: an unresolved case and a rejected replacement',
        '1924 map | z16 / 54895 / 28092 | school mark above-right, hot-spring mark below-left',source(scene),[140,88,302,232],2,
        [('Original pixels',{}),('Current symbol proposals',dict(proposals=before,refs=refs)),('Thick-stroke experiment',dict(proposals=alternative,refs=refs))],
        'Teal = saved shape proposals. Dashed green = user-identified reference boxes, not detections.',
        'The school mark is proposed. The hot-spring mark is not reliably enclosed as a whole. The experiment was not promoted.'))

    manifest=dict(role='Post-run visual evidence only. No detector changes or reruns. Original pixels plus actual saved proposals; no generative edits.',artifacts=artifacts,
        proposal_inputs=[dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(inputs)])
    (FOLDER/'manifest.json').write_text(json.dumps(manifest,indent=2),'utf-8')
    print(json.dumps([a['file'] for a in artifacts]))


if __name__=='__main__':main()
