"""Read-only, on-demand vegetation evidence from the recorded map pixels."""
import base64
import io
import time
from pathlib import Path

from PIL import Image, ImageDraw

from .reading_suggestions import ReadingSuggestions, evidence_crop
from .vegetation import VERSION, analyze


class VegetationEvidence:
    def __init__(self, data, reader=None):
        self.data = Path(data)
        self.reader = reader if reader is not None else ReadingSuggestions(data)

    def inspect(self, item):
        if item['kind'] == 'trail' or item['z'] != 16:
            return dict(version=VERSION, status='unsupported-scale' if item['z'] != 16 else 'unsupported-kind', matches=[])
        start = time.perf_counter()
        image, box, pixels = evidence_crop(self.data, item, 24)
        decoded = time.perf_counter()
        result = analyze(image, box, item['z'])
        analyzed = time.perf_counter()
        result.update(pixels=pixels, note='A shape suggestion only. Compare the original map before choosing a type.',
                      timing_ms=dict(input=(decoded-start)*1000, analysis=(analyzed-decoded)*1000))
        if result['matches']:
            # A digit 9 can have the same ring/stem geometry. Any plausible
            # overlapping multi-digit reading is a veto, never a repaired label.
            numbers = self.reader.suggest(item, 'numbers')
            result['timing_ms']['number_guard'] = (time.perf_counter()-analyzed)*1000
            if numbers['readings']:
                result.update(status='numeric-context', matches=[], numeric_readings=numbers['readings'])
                return result
            preview = image.copy()
            draw = ImageDraw.Draw(preview)
            draw.rectangle(box, outline='#bd6500', width=1)
            for match in result['matches']:
                draw.rectangle(match['box'], outline='#00895c', width=1)
            scale = min(3, 480/max(preview.size))
            preview = preview.resize((max(1, round(preview.width*scale)), max(1, round(preview.height*scale))), Image.Resampling.NEAREST)
            payload = io.BytesIO(); preview.save(payload, format='PNG')
            result['preview'] = 'data:image/png;base64,'+base64.b64encode(payload.getvalue()).decode('ascii')
        return result
