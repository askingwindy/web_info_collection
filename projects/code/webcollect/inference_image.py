"""Derived inference assets. Never substitutes customer/QC PNG evidence."""
from io import BytesIO
from pathlib import Path
from PIL import Image
from .batch_core import file_sha
from .planning import object_sha256

VERSION = 'inference-image'


def derive(source, directory, *, size=(960, 540), quality=85, crop=None, original=False):
    source = Path(source)
    if source.is_symlink():
        raise ValueError('Inference source must be an original regular PNG')
    digest = file_sha(source)
    with Image.open(source) as image:
        if image.format != 'PNG':
            raise ValueError('Inference source must be PNG')
        width, height = image.size
        box = crop or (0, 0, width, height)
        if (len(box) != 4 or any(type(v) is not int for v in box)
                or not 0 <= box[0] < box[2] <= width or not 0 <= box[1] < box[3] <= height):
            raise ValueError('Crop must be inside original viewport')
        derived = image.crop(box) if original else image.crop(box).convert('RGB')
        if not original and crop is None:
            derived.thumbnail(size, Image.Resampling.LANCZOS)
        stream = BytesIO()
        if original:
            derived.save(stream, 'PNG')
            suffix = '.png'
        else:
            derived.save(stream, 'JPEG', quality=quality, subsampling=0, optimize=True)
            suffix = '.jpg'
        # Full-resolution fallback preserves the exact original evidence bytes;
        # only a regional crop needs a newly encoded PNG.
        data = source.read_bytes() if original and crop is None else stream.getvalue()
        spec = {'protocol': VERSION, 'source_sha256': digest, 'crop': list(box),
                'output_size': list(derived.size), 'quality': None if original else quality}
        if not original:
            spec['jpeg'] = {'subsampling': '4:4:4', 'optimize': True}
        directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
        path = directory / (object_sha256(spec) + suffix)
        if path.exists():
            if path.read_bytes() != data:
                raise ValueError('Derived image collision')
        else:
            with path.open('xb') as out: out.write(data)
        result = {**spec, 'source': str(source.resolve()), 'source_size': [width, height],
                  'path': str(path.resolve()), 'sha256': file_sha(path),
                  'source_bytes': source.stat().st_size, 'bytes': len(data),
                  'mapping': {'origin': list(box[:2]),
                              'source_per_output_pixel': [(box[2]-box[0])/derived.width,
                                                          (box[3]-box[1])/derived.height]},
                  'quality_status': 'UNVERIFIED', 'token_savings': 'UNKNOWN'}
    if file_sha(source) != digest: raise ValueError('Source changed during derivation')
    return result
