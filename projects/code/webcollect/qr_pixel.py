"""Independent, bounded, read-only QR decoder for original saved PNG evidence."""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess
import tempfile

_SWIFT_DECODER=r'''import Foundation
import Vision
import ImageIO
guard CommandLine.arguments.count == 2 else { exit(2) }
let url=URL(fileURLWithPath:CommandLine.arguments[1])
let data=try Data(contentsOf:url)
guard let source=CGImageSourceCreateWithData(data as CFData,nil),
      let image=CGImageSourceCreateImageAtIndex(source,0,nil) else { exit(2) }
let request=VNDetectBarcodesRequest(); request.symbologies=[.qr]
try VNImageRequestHandler(cgImage:image,options:[:]).perform([request])
let decoded:[[String:Any]]=(request.results ?? []).map { item in
 let b=item.boundingBox,w=Double(image.width),h=Double(image.height)
 return ["payload":item.payloadStringValue ?? NSNull(),"symbology":item.symbology.rawValue,
         "confidence":item.confidence,"bbox":[b.minX*w,(1-b.maxY)*h,b.maxX*w,(1-b.minY)*h]]
}
let result:[String:Any] = ["width":image.width,"height":image.height,"decoded":decoded]
let output=try JSONSerialization.data(withJSONObject:result,options:[.sortedKeys,.withoutEscapingSlashes])
print(String(data:output,encoding:.utf8)!)
'''


def decode_qr_png(png):
    """Read raw original image bytes; the decoder never receives expected text."""
    from PIL import Image
    if not isinstance(png,bytes) or not png.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('QR pixel oracle requires original PNG bytes')
    try:
        with Image.open(BytesIO(png)) as image:
            if image.format!='PNG':raise ValueError('QR oracle input must be PNG')
            width,height=image.size;image.verify()
    except Exception as error:raise ValueError('QR oracle could not validate the saved PNG') from error
    if width<32 or height<32 or width*height>20000000:
        raise ValueError('QR pixel oracle image dimensions are outside bounded scope')
    with tempfile.TemporaryDirectory(prefix='webcollect-qr-pixels-') as directory:
        root=Path(directory);script=root/'decode.swift';image_path=root/'original.png'
        script.write_text(_SWIFT_DECODER,encoding='utf-8');image_path.write_bytes(png)
        try:
            process=subprocess.run(['/usr/bin/swift',str(script),str(image_path)],capture_output=True,timeout=30,check=False)
        except (OSError,subprocess.TimeoutExpired) as error:
            raise ValueError('Installed offline Swift Vision QR decoder unavailable or timed out') from error
        if process.returncode or len(process.stdout)>1000000:
            raise ValueError('Offline QR pixel decoder failed: '+process.stderr.decode('utf-8',errors='replace')[:400])
        try:result=json.loads(process.stdout)
        except (ValueError,UnicodeDecodeError) as error:raise ValueError('Offline QR decoder returned invalid JSON') from error
    if result.get('width')!=width or result.get('height')!=height or not isinstance(result.get('decoded'),list):
        raise ValueError('QR decoder image dimensions or result schema changed')
    return {**result,'image_sha256':sha256(png).hexdigest(),'decoder':'Apple Vision VNDetectBarcodesRequest',
            'decoder_source_sha256':sha256(_SWIFT_DECODER.encode()).hexdigest(),
            'evidence_source':'original_saved_png_pixels','expected_text_supplied_to_decoder':False}


def verify_qr_png(png,expected_payload,canvas_bbox,*,viewport=(1280,720)):
    """Require one exact decoded QR wholly inside the screenshot's visible canvas."""
    if (not isinstance(expected_payload,str) or not expected_payload or len(expected_payload)>2000 or
        not isinstance(canvas_bbox,(list,tuple)) or len(canvas_bbox)!=4):
        raise ValueError('QR verification requires exact payload and observed canvas bounds')
    if any(type(n) not in (int,float) for n in canvas_bbox):raise ValueError('Invalid QR canvas geometry')
    x1,y1,x2,y2=canvas_bbox
    if not (0<=x1<x2<=viewport[0] and 0<=y1<y2<=viewport[1]):
        raise ValueError('QR canvas must be fully inside the original screenshot')
    result=decode_qr_png(png)
    if (result['width'],result['height'])!=tuple(viewport):raise ValueError('QR pixel oracle viewport changed')
    if len(result['decoded'])!=1:raise ValueError('Original screenshot must contain exactly one decodable QR')
    code=result['decoded'][0]
    if code.get('payload')!=expected_payload:raise ValueError('QR pixel payload differs from the independent task payload')
    box=code.get('bbox')
    if (not isinstance(box,list) or len(box)!=4 or
        not (x1<=box[0]<box[2]<=x2 and y1<=box[1]<box[3]<=y2)):
        raise ValueError('Decoded QR is outside the fully visible task canvas')
    return {**result,'expected_payload':expected_payload,'canvas_bbox':list(canvas_bbox),'passed':True}
