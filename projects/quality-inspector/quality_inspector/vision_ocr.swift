// Local OCR of original PNG pixels. Optional ROI is coordinates only: no
// expected task text, DOM values, image modifications, or external API calls.
import Foundation
import Vision
import ImageIO
import CryptoKit

func pixels(_ box: CGRect, _ width: Int, _ height: Int) -> [Double] {
    return [Double(box.minX) * Double(width), (1 - Double(box.maxY)) * Double(height),
            Double(box.maxX) * Double(width), (1 - Double(box.minY)) * Double(height)]
}

do {
    guard [2, 3].contains(CommandLine.arguments.count) else { throw NSError(domain: "vision-ocr", code: 1, userInfo: [NSLocalizedDescriptionKey: "Expected original PNG path and optional x1,y1,x2,y2 ROI"]) }
    let url = URL(fileURLWithPath: CommandLine.arguments[1])
    let bytes = try Data(contentsOf: url)
    guard let source = CGImageSourceCreateWithData(bytes as CFData, nil),
          CGImageSourceGetType(source) as String? == "public.png",
          CGImageSourceGetCount(source) == 1,
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        throw NSError(domain: "vision-ocr", code: 2, userInfo: [NSLocalizedDescriptionKey: "Expected one decodable original PNG"])
    }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["zh-Hans", "en-US"]
    request.usesLanguageCorrection = false
    var roi: [Double]? = nil
    if CommandLine.arguments.count == 3 {
        let values = CommandLine.arguments[2].split(separator: ",").compactMap { Double($0) }
        guard values.count == 4, values.allSatisfy({ $0.isFinite }),
              values[0] >= 0, values[1] >= 0, values[2] <= Double(image.width), values[3] <= Double(image.height),
              values[0] < values[2], values[1] < values[3] else {
            throw NSError(domain: "vision-ocr", code: 4, userInfo: [NSLocalizedDescriptionKey: "ROI outside original PNG"])
        }
        roi = values
        request.regionOfInterest = CGRect(x: values[0] / Double(image.width), y: 1 - values[3] / Double(image.height),
            width: (values[2] - values[0]) / Double(image.width), height: (values[3] - values[1]) / Double(image.height))
    }
    let supported = try request.supportedRecognitionLanguages()
    guard request.recognitionLanguages.allSatisfy({ supported.contains($0) }) else {
        throw NSError(domain: "vision-ocr", code: 3, userInfo: [NSLocalizedDescriptionKey: "Requested offline recognition languages unavailable"])
    }
    try VNImageRequestHandler(cgImage: image, orientation: .up, options: [:]).perform([request])
    var observations: [[String: Any]] = []
    for (index, observation) in (request.results ?? []).enumerated() {
        guard let text = observation.topCandidates(1).first else { continue }
        // Vision normalizes observations against regionOfInterest. Convert
        // those coordinates back to the unchanged, full PNG pixel space.
        let box = observation.boundingBox
        let pixelBox = roi.map { region in
            [region[0] + Double(box.minX) * (region[2] - region[0]),
             region[1] + (1 - Double(box.maxY)) * (region[3] - region[1]),
             region[0] + Double(box.maxX) * (region[2] - region[0]),
             region[1] + (1 - Double(box.minY)) * (region[3] - region[1])]
        } ?? pixels(box, image.width, image.height)
        observations.append(["index": index, "text": text.string, "confidence": Double(text.confidence),
                             "bbox": pixelBox])
    }
    let result: [String: Any] = ["schema_version": "local-vision-ocr-1", "engine": "Apple Vision VNRecognizeTextRequest",
        "recognition_revision": request.revision, "recognition_level": "accurate",
        "recognition_languages": request.recognitionLanguages, "uses_language_correction": false,
        "custom_words": [], "whole_original_image": roi == nil, "region_of_interest_pixels": roi as Any? ?? NSNull(),
        "coordinate_space": "top-left-original-pixels",
        "image_sha256": SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined(),
        "image_width": image.width, "image_height": image.height,
        "os_version": ProcessInfo.processInfo.operatingSystemVersionString, "observations": observations]
    let output = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
    FileHandle.standardOutput.write(output)
    FileHandle.standardOutput.write(Data("\n".utf8))
} catch {
    FileHandle.standardError.write(Data((String(describing: error) + "\n").utf8))
    exit(1)
}
