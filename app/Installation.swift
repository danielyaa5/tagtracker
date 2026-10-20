import AppKit

enum Installation {
    static func mountedInstallers(for app: URL) -> [URL] {
        guard let installed = Bundle(url: app), let identifier = installed.bundleIdentifier,
              let build = installed.object(forInfoDictionaryKey: "CFBundleVersion") as? String,
              let installedNumber = Int(build),
              let text = try? Services.run("/usr/bin/hdiutil", ["info", "-plist"]),
              let plist = try? PropertyListSerialization.propertyList(from: Data(text.utf8), format: nil) as? [String: Any],
              let images = plist["images"] as? [[String: Any]] else { return [] }
        return images.compactMap { image in
            guard image["writeable"] as? Bool == false,
                  let entities = image["system-entities"] as? [[String: Any]],
                  let path = entities.compactMap({ $0["mount-point"] as? String }).first else { return nil }
            let mount = URL(fileURLWithPath: path, isDirectory: true)
            guard let marker = try? String(contentsOf: mount.appendingPathComponent(".tagtracker-installer"), encoding: .utf8),
                  let number = Int(marker), number <= installedNumber,
                  let candidate = Bundle(url: mount.appendingPathComponent("TagTracker.app")),
                  candidate.bundleIdentifier == identifier,
                  candidate.object(forInfoDictionaryKey: "CFBundleVersion") as? String == marker else { return nil }
            return mount
        }
    }

    static func prepare() -> Bool {
        let app = Bundle.main.bundleURL.standardizedFileURL
        let locations = FileManager.default.urls(for: .applicationDirectory, in: .localDomainMask)
            + FileManager.default.urls(for: .applicationDirectory, in: .userDomainMask)
        if locations.contains(where: { app.deletingLastPathComponent() == $0.standardizedFileURL }) { return true }
        let alert = NSAlert()
        alert.messageText = "Move TagTracker to Applications"
        alert.informativeText = "Drag TagTracker into Applications, then open it there. This gives tracking and updates a stable home. The installed app will eject its installer disk."
        alert.addButton(withTitle: "Show in Finder and Quit")
        alert.addButton(withTitle: "Quit")
        if alert.runModal() == .alertFirstButtonReturn { NSWorkspace.shared.activateFileViewerSelecting([app]) }
        return false
    }

    static func ejectMatchingInstallers() {
        let app = Bundle.main.bundleURL
        DispatchQueue.global(qos: .utility).async {
            for mount in mountedInstallers(for: app) {
                // A busy disk remains mounted; never force-eject or trash a download.
                _ = try? Services.run("/usr/bin/hdiutil", ["detach", mount.path])
            }
        }
    }
}
