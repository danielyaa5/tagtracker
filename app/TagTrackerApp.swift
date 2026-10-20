import AppKit
import SwiftUI
import Sparkle

final class AppDelegate: NSObject, NSApplicationDelegate, SPUUpdaterDelegate {
    var updater: SPUStandardUpdaterController!

    func applicationDidFinishLaunching(_ notification: Notification) {
        guard Installation.prepare() else { NSApp.terminate(nil); return }
        updater = SPUStandardUpdaterController(startingUpdater: true, updaterDelegate: self, userDriverDelegate: nil)
        Installation.ejectMatchingInstallers()
        // Services are restored after an update only if this app paused them.
        if UserDefaults.standard.bool(forKey: "resumeServicesAfterUpdate") {
            Services.shared.configure()
            UserDefaults.standard.removeObject(forKey: "resumeServicesAfterUpdate")
        }
    }

    func updater(_ updater: SPUUpdater, willInstallUpdate item: SUAppcastItem) {
        if Services.shared.isRunning {
            UserDefaults.standard.set(true, forKey: "resumeServicesAfterUpdate")
            Services.shared.stop()
        }
    }
}

final class Services: ObservableObject {
    static let shared = Services()
    @Published var names = ""
    @Published var devices = false
    @Published var message = "Choose the items to record, then start tracking."
    @Published var busy = false
    let data = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/TagTracker")
    let runtime = Bundle.main.resourceURL!.appendingPathComponent("runtime")
    let labels = ["io.tagtracker.collector", "io.tagtracker.history", "io.tagtracker.sharing-probe"]

    init() {
        if let bytes = try? Data(contentsOf: data.appendingPathComponent("item-names.json")),
           let config = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any] {
            names = (config["expected"] as? [String] ?? []).joined(separator: "\n")
            devices = config["collect_devices"] as? Bool ?? false
            message = "Your saved configuration and history are kept on this Mac."
        }
    }

    @discardableResult
    static func run(_ executable: String, _ arguments: [String]) throws -> String {
        let task = Process(), pipe = Pipe()
        task.executableURL = URL(fileURLWithPath: executable)
        task.arguments = arguments
        task.environment = ProcessInfo.processInfo.environment.merging(["PYTHONDONTWRITEBYTECODE": "1"]) { _, new in new }
        task.standardOutput = pipe
        task.standardError = pipe
        try task.run()
        let bytes = pipe.fileHandleForReading.readDataToEndOfFile()
        task.waitUntilExit()
        let text = String(decoding: bytes, as: UTF8.self)
        guard task.terminationStatus == 0 else {
            throw NSError(domain: "TagTracker", code: Int(task.terminationStatus), userInfo: [NSLocalizedDescriptionKey: text])
        }
        return text
    }

    var isRunning: Bool {
        ownedLabels.contains("io.tagtracker.history") && (try? Self.run("/bin/launchctl", ["print", "gui/\(getuid())/io.tagtracker.history"])) != nil
    }

    var ownedLabels: [String] {
        labels.filter { label in
            let url = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/LaunchAgents/\(label).plist")
            guard let bytes = try? Data(contentsOf: url),
                  let job = try? PropertyListSerialization.propertyList(from: bytes, format: nil) as? [String: Any] else { return false }
            return job["WorkingDirectory"] as? String == runtime.path
        }
    }

    func configure() {
        let items = names.split(separator: "\n").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
        guard !items.isEmpty else { message = "Enter at least one exact item name from Find My."; return }
        busy = true
        let python = runtime.appendingPathComponent("python/bin/python3").path
        var arguments = [runtime.appendingPathComponent("scripts/setup.py").path, "--update", "--load", "--python", python]
        for item in items { arguments += ["--item", item] }
        arguments += ["--devices-enabled", devices ? "yes" : "no"]
        DispatchQueue.global(qos: .userInitiated).async {
            do {
                _ = try Self.run(python, arguments)
                DispatchQueue.main.async {
                    self.busy = false
                    self.message = "Tracking is scheduled. Scans wait for two idle minutes and pause during Screen Sharing. Open History to check collection status."
                }
            } catch {
                DispatchQueue.main.async { self.busy = false; self.message = error.localizedDescription }
            }
        }
    }

    func stop() {
        for label in ownedLabels { _ = try? Self.run("/bin/launchctl", ["bootout", "gui/\(getuid())/\(label)"]) }
        message = "Tracking and the history server are stopped. Your history is retained."
    }

    func permissions() {
        busy = true
        DispatchQueue.global(qos: .userInitiated).async {
            let output = (try? Self.run(self.runtime.appendingPathComponent("bin/findmy-helper").path, ["permissions"])) ?? "Open Privacy & Security to grant permissions."
            DispatchQueue.main.async { self.busy = false; self.message = output }
        }
    }
}

@main
struct TagTrackerApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    @StateObject private var services = Services.shared

    var body: some Scene {
        WindowGroup("TagTracker") {
            VStack(alignment: .leading, spacing: 18) {
                HStack(spacing: 15) {
                    Image(nsImage: NSApp.applicationIconImage).resizable().frame(width: 70, height: 70)
                    VStack(alignment: .leading, spacing: 5) {
                        Text("TagTracker").font(.largeTitle.bold())
                        Text("A little history for the things you carry.").foregroundStyle(.secondary)
                    }
                }
                Text("Item names").font(.headline)
                Text("Enter the exact names shown in Find My, one per line.").foregroundStyle(.secondary)
                TextEditor(text: $services.names).font(.body).frame(height: 100).border(.quaternary).accessibilityLabel("Find My item names")
                Toggle("Also record devices", isOn: $services.devices)
                HStack {
                    Button("Start Tracking", action: services.configure).buttonStyle(.borderedProminent)
                    Button("Stop Tracking", action: services.stop)
                    Button("Open History") { NSWorkspace.shared.open(URL(string: "http://127.0.0.1:8768/")!) }
                }.disabled(services.busy)
                Divider()
                Text("Allow Accessibility and Screen Recording for the collector in Privacy & Security. The Mac must stay awake, logged in, and unlocked.")
                    .font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                HStack {
                    Button("Check Permissions", action: services.permissions).disabled(services.busy)
                    Button("Privacy & Security") { NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security")!) }
                    Button("Show Collector") { NSWorkspace.shared.activateFileViewerSelecting([services.runtime.appendingPathComponent("bin/findmy")]) }
                }
                Text(services.message).font(.callout).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading).fixedSize(horizontal: false, vertical: true)
                if services.busy { ProgressView().controlSize(.small) }
                Text("Experimental · Observations reflect what Find My displayed. Older locations and gaps are possible. Quitting this window leaves scheduled tracking running.")
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            .padding(28).frame(width: 600)
        }
        .windowResizability(.contentSize)
        .commands {
            CommandGroup(after: .appInfo) {
                Button("Check for Updates…") { delegate.updater?.checkForUpdates(nil) }
            }
            CommandGroup(replacing: .newItem) { }
        }
    }
}
