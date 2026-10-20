import Foundation
import CoreLocation

guard CommandLine.arguments.count > 1 else {
    FileHandle.standardError.write(Data("usage: geocoder <address_or_town>\n".utf8))
    exit(1)
}

let query = CommandLine.arguments.dropFirst().joined(separator: " ").trimmingCharacters(in: .whitespacesAndNewlines)
guard !query.isEmpty else {
    FileHandle.standardError.write(Data("empty query\n".utf8))
    exit(1)
}

let geocoder = CLGeocoder()
var done = false
var exitCode: Int32 = 2

geocoder.geocodeAddressString(query) { placemarks, error in
    defer { done = true }
    if let p = placemarks?.first, let loc = p.location {
        let name = [p.name, p.locality, p.administrativeArea].compactMap { $0 }.joined(separator: ", ")
        let precision = name.isEmpty ? "macOS geocoded location" : name
        let result: [String: Any] = [
            "lat": loc.coordinate.latitude,
            "lon": loc.coordinate.longitude,
            "precision": precision,
            "source": "macOS Geocoder"
        ]
        if let data = try? JSONSerialization.data(withJSONObject: result, options: [.sortedKeys]) {
            FileHandle.standardOutput.write(data)
            FileHandle.standardOutput.write(Data([0x0a]))
            exitCode = 0
            return
        }
    }
}

let timeout = Date(timeIntervalSinceNow: 2.5)
while !done && Date() < timeout {
    RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.05))
}

exit(exitCode)
