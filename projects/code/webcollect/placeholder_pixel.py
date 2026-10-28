"""Independent original-pixel oracle for the fixed 400x200 Chinese placeholder."""
import base64
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import subprocess
import tempfile

MIN_CONFIDENCE=0.9
EXPECTED_TEXT='预览图'
_SWIFT_OCR=r'''import Foundation
import Vision
import ImageIO
guard CommandLine.arguments.count == 3 else { exit(2) }
let bytes=try Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1]))
guard let source=CGImageSourceCreateWithData(bytes as CFData,nil),
      let image=CGImageSourceCreateImageAtIndex(source,0,nil) else { exit(2) }
let roi=CommandLine.arguments[2].split(separator:",").compactMap{Double($0)}
guard roi.count==4 else { exit(2) }
let request=VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages=["zh-Hans","en-US"]
request.usesLanguageCorrection=false
request.regionOfInterest=CGRect(x:roi[0]/Double(image.width),y:1-roi[3]/Double(image.height),
 width:(roi[2]-roi[0])/Double(image.width),height:(roi[3]-roi[1])/Double(image.height))
try VNImageRequestHandler(cgImage:image,orientation:.up,options:[:]).perform([request])
let observations:[[String:Any]]=(request.results ?? []).compactMap { item in
 guard let text=item.topCandidates(1).first else { return nil }
 let b=item.boundingBox
 return ["text":text.string,"confidence":Double(text.confidence),
 "bbox":[roi[0]+b.minX*(roi[2]-roi[0]),roi[1]+(1-b.maxY)*(roi[3]-roi[1]),
 roi[0]+b.maxX*(roi[2]-roi[0]),roi[1]+(1-b.minY)*(roi[3]-roi[1])]]
}
let output=try JSONSerialization.data(withJSONObject:["width":image.width,"height":image.height,
 "observations":observations,"revision":request.revision],options:[.sortedKeys])
print(String(data:output,encoding:.utf8)!)
'''

def _box(box,viewport):
    if not isinstance(box,(list,tuple)) or len(box)!=4 or any(type(n) not in (int,float) or not math.isfinite(n) for n in box):
        raise ValueError('Invalid original screenshot image rectangle')
    if not (0<=box[0]<box[2]<=viewport[0] and 0<=box[1]<box[3]<=viewport[1]):raise ValueError('Placeholder image is clipped/outside viewport')
    rounded=[round(n) for n in box]
    if (abs(box[2]-box[0]-400)>1e-6 or abs(box[3]-box[1]-200)>1e-6 or
            [rounded[2]-rounded[0],rounded[3]-rounded[1]]!=[400,200]):
        raise ValueError('Placeholder must render at its original 400x200 size')
    return rounded

def recognize_original_placeholder(png,box):
    """Only original PNG and actual ROI reach Vision; no desired text/custom words."""
    with tempfile.TemporaryDirectory(prefix='webcollect-placeholder-ocr-') as directory:
        root=Path(directory);script=root/'recognize.swift';source=root/'original.png'
        script.write_text(_SWIFT_OCR);source.write_bytes(png)
        try:process=subprocess.run(['/usr/bin/swift',str(script),str(source),','.join(map(str,box))],capture_output=True,timeout=30,check=False)
        except (OSError,subprocess.TimeoutExpired) as error:raise ValueError('Local Vision OCR unavailable or timed out') from error
        if process.returncode or len(process.stdout)>1000000:raise ValueError('Local Vision OCR failed: '+process.stderr.decode(errors='replace')[:300])
        try:return json.loads(process.stdout)
        except (ValueError,UnicodeDecodeError) as error:raise ValueError('Local Vision OCR returned invalid JSON') from error

def verify_placeholder_png(png,expected_text,image_bbox,image_data_uri,*,viewport=(1280,720)):
    """Decode actual PNG pixels, match screenshot crop, then exact Chinese OCR."""
    from PIL import Image
    from .placeholder_strategy import inspect_placeholder_png
    if expected_text!=EXPECTED_TEXT or not isinstance(png,bytes) or not png.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Placeholder oracle is limited to original PNG and its fixed Chinese text')
    box=_box(image_bbox,viewport)
    metrics=inspect_placeholder_png(image_data_uri)
    image_png=base64.b64decode(image_data_uri.split(',',1)[1],validate=True)
    with Image.open(BytesIO(png)) as frame,Image.open(BytesIO(image_png)) as generated:
        if frame.format!='PNG' or frame.size!=tuple(viewport):raise ValueError('Original placeholder screenshot dimensions changed')
        crop=frame.crop(tuple(box)).convert('RGB')
        if crop.tobytes()!=generated.convert('RGB').tobytes():raise ValueError('Visible original pixels do not match the generated PNG')
    # CSS can place an image at a fractional origin while rasterizing its
    # unchanged bitmap to the nearest pixel. Equality above is mandatory;
    # fractional placement does not permit interpolation or differing pixels.
    observed=recognize_original_placeholder(png,list(image_bbox))
    if (observed.get('width'),observed.get('height'))!=tuple(viewport):raise ValueError('OCR original image dimensions changed')
    rows=observed.get('observations',[])
    if len(rows)!=1:raise ValueError('Placeholder ROI must contain exactly one independently recognized text line')
    row=rows[0];recognized=''.join(str(row.get('text','')).split());confidence=row.get('confidence');bounds=row.get('bbox')
    if recognized!=EXPECTED_TEXT or type(confidence) not in (int,float) or not math.isfinite(confidence) or confidence<MIN_CONFIDENCE:
        raise ValueError('Placeholder text OCR mismatch or below the fixed confidence threshold')
    if (not isinstance(bounds,list) or len(bounds)!=4 or any(type(n) not in (int,float) or not math.isfinite(n) for n in bounds) or
        not (box[0]<=bounds[0]<bounds[2]<=box[2] and box[1]<=bounds[1]<bounds[3]<=box[3])):
        raise ValueError('OCR glyphs are outside the observed placeholder image')
    return {'passed':True,'image_sha256':sha256(png).hexdigest(),'generated_image_sha256':metrics['png_sha256'],
      'generated_rgb_sha256':metrics['rgb_sha256'],'image_bbox':list(image_bbox),'raster_bbox':box,'image_width':400,'image_height':200,
      'expected_text':EXPECTED_TEXT,'recognized_text':recognized,'confidence':confidence,'minimum_confidence':MIN_CONFIDENCE,
      'ocr_bbox':bounds,'ocr_revision':observed.get('revision'),'decoder':'Apple Vision VNRecognizeTextRequest',
      'decoder_source_sha256':sha256(_SWIFT_OCR.encode()).hexdigest(),'expected_text_supplied_to_decoder':False,
      'evidence_source':'original_saved_png_pixels','screenshot_crop_equals_generated_png':True}
