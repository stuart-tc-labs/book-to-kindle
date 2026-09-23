import AppKit
import ApplicationServices
import Darwin

final class AppDelegate: NSObject, NSApplicationDelegate, NSSharingServiceDelegate {
    let manager = FileManager.default
    let support = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Book to Kindle Shortcut")
    let cache = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Caches/Book to Kindle Shortcut")
    var lockFD: Int32 = -1
    var timer: Timer?
    var service: NSSharingService?
    var window: NSWindow!
    var label: NSTextField!
    var job: SendJob?
    var phase = "preparing"
    var phaseStarted = Date()
    var matchedWindow: AXUIElement?
    var mode = "auto"
    var preview = false
    var finished = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        makeWindow()
        do { try manager.createDirectory(at: support, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700]) }
        catch { finish("failed", "Cannot create the settings folder: \(error.localizedDescription)"); return }
        let args = CommandLine.arguments
        guard let index = args.firstIndex(of: "--file"), args.count > index + 1 else { showSetup(); return }
        preview = args.contains("--preview")
        lockFD = Darwin.open(support.appendingPathComponent("send.lock").path, O_CREAT | O_RDWR, S_IRUSR | S_IWUSR)
        guard lockFD >= 0, flock(lockFD, LOCK_EX | LOCK_NB) == 0 else {
            finish("busy", "Another book is being processed or sent. Wait for it to finish before trying again."); return
        }
        guard AXIsProcessTrusted() else {
            finish("permission_required", "Enable Book to Kindle in System Settings → Privacy & Security → Accessibility, then run the shortcut again. Nothing was moved."); return
        }
        guard let sharing = NSSharingService(named: NSSharingService.Name("com.amazon.Lassen.SendToKindleExtension")) else {
            finish("failed", "Install and sign in to the Kindle Mac app, and enable its Send to Kindle share extension. Nothing was moved."); return
        }
        let source = URL(fileURLWithPath: args[index + 1])
        guard sharing.canPerform(withItems: [source]) else {
            finish("failed", "Kindle cannot share this file. Select one EPUB and check Kindle is installed. Nothing was moved."); return
        }
        service = sharing
        do {
            let config = try Configuration.load(from: support.appendingPathComponent("config.json"))
            mode = config.mode
            let destination = NSString(string: config.destination).expandingTildeInPath
            prepare(source: source, destination: destination)
        } catch { finish("failed", error.localizedDescription) }
    }

    func makeWindow() {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 440, height: 120), styleMask: [.titled], backing: .buffered, defer: false)
        window.title = "Book to Kindle"
        label = NSTextField(wrappingLabelWithString: "Preparing your book…")
        label.frame = NSRect(x: 24, y: 24, width: 392, height: 72)
        window.contentView?.addSubview(label)
        window.center(); window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func showSetup() {
        label.stringValue = "Enable Accessibility for Book to Kindle, then run the Book to Kindle Quick Action on one EPUB in Finder."
        let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
        let trusted = AXIsProcessTrustedWithOptions(options)
        let message = trusted ? "Accessibility is enabled. Import Book to Kindle.shortcut, enable Allow Running Scripts in Shortcuts → Settings → Advanced, and select one EPUB in Finder to run it." : "Enable Book to Kindle in System Settings → Privacy & Security → Accessibility. Then import the generated shortcut and enable Allow Running Scripts in Shortcuts → Settings → Advanced."
        finish("setup", message)
    }

    func prepare(source: URL, destination: String) {
        guard let script = Bundle.main.url(forResource: "books", withExtension: "py") else {
            finish("failed", "The EPUB processor is missing. Run the installer again."); return
        }
        // Blocking file work is kept away from AppKit's main thread.
        DispatchQueue.global(qos: .userInitiated).async {
            let process = Process(), output = Pipe(), errors = Pipe()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
            process.arguments = [script.path, "--destination", destination, "--cache", self.cache.path, "--", source.path]
            process.standardOutput = output; process.standardError = errors
            do {
                try process.run()
                let data = output.fileHandleForReading.readDataToEndOfFile()
                let errorData = errors.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                guard process.terminationStatus == 0 else {
                    let errorText = String(data: errorData, encoding: .utf8) ?? "The EPUB could not be prepared."
                    DispatchQueue.main.async { self.finish("failed", errorText) }; return
                }
                let prepared = try JSONDecoder().decode(SendJob.self, from: data)
                DispatchQueue.main.async { self.openShare(prepared) }
            } catch { DispatchQueue.main.async { self.finish("failed", error.localizedDescription) } }
        }
    }

    func openShare(_ prepared: SendJob) {
        job = prepared
        label.stringValue = "Archived: \(prepared.title)\nOpening Send to Kindle…"
        phase = "waiting"; phaseStarted = Date()
        guard record("archived") else { finish("failed", "Could not save send status. The book is archived, but nothing was sent."); return }
        service?.delegate = self
        service?.perform(withItems: [URL(fileURLWithPath: prepared.send)])
        timer = Timer.scheduledTimer(withTimeInterval: 0.4, repeats: true) { [weak self] _ in self?.tick() }
    }

    func sharingService(_ sharingService: NSSharingService, sourceWindowForShareItems items: [Any], sharingContentScope: UnsafeMutablePointer<NSSharingService.SharingContentScope>) -> NSWindow? { window }
    func sharingService(_ sharingService: NSSharingService, didFailToShareItems items: [Any], error: Error) {
        finish(phase == "sending" ? "unconfirmed" : "failed", "Kindle did not complete sharing: \(error.localizedDescription). Check the library before retrying.")
    }
    // didShareItems alone is not proof of Amazon accepting the upload; require File sent.

    @discardableResult func record(_ state: String, _ message: String = "") -> Bool {
        guard let job = job else { return true }
        let status: [String: Any] = ["id": job.id, "title": job.title, "author": job.author,
            "archive": job.archive, "sha256": job.sha256, "status": state, "message": message,
            "timestamp": Date().timeIntervalSince1970]
        do {
            let data = try JSONSerialization.data(withJSONObject: status, options: [.sortedKeys, .prettyPrinted])
            try data.write(to: support.appendingPathComponent("last-result.json"), options: .atomic)
            let jobs = support.appendingPathComponent("results")
            try manager.createDirectory(at: jobs, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
            try data.write(to: jobs.appendingPathComponent(job.id + ".json"), options: .atomic)
            return true
        } catch { return false }
    }

    func finish(_ state: String, _ message: String) {
        guard !finished else { return }
        finished = true; timer?.invalidate()
        let recorded = record(state, message)
        label.stringValue = message
        // Do not discard a share copy while Kindle may still be processing it.
        if ["sent", "preview_verified"].contains(state), let job = job {
            if state == "sent" { try? manager.removeItem(at: URL(fileURLWithPath: job.send).deletingLastPathComponent()) }
        }
        let alert = NSAlert()
        alert.messageText = state == "sent" ? "Sent to Kindle" : "Book to Kindle"
        alert.informativeText = message + (recorded ? "" : "\nThe local result log could not be saved.")
        alert.addButton(withTitle: "OK")
        NSApp.activate(ignoringOtherApps: true)
        if state == "sent" {
            // Keep a visible, nonblocking confirmation briefly; no extra click is needed.
            label.stringValue = "Sent to Kindle: \(job?.title ?? "book")"
            DispatchQueue.main.asyncAfter(deadline: .now() + 3) { NSApp.terminate(nil) }
        } else {
            alert.runModal(); NSApp.terminate(nil)
        }
    }

    func tick() {
        guard let job = job, !finished else { return }
        let limit: TimeInterval = phase == "sending" || phase == "review" ? 300 : 60
        if Date().timeIntervalSince(phaseStarted) > limit {
            let uncertain = phase == "sending" || phase == "review"
            finish(uncertain ? "unconfirmed" : "failed", uncertain ? "Kindle has not confirmed delivery. Check its library before retrying to avoid duplicates." : "The expected English Kindle form did not appear. The book is archived, but sending did not complete.")
            return
        }
        // Scope AX access to our own share-service host, never arbitrary app windows.
        let root = AXUIElementCreateApplication(ProcessInfo.processInfo.processIdentifier)
        AXUIElementSetMessagingTimeout(root, 0.5)
        let nodes = walk(root)
        let dialogs = nodes.filter { [kAXWindowRole, kAXSheetRole, "AXDialog"].contains(string($0, kAXRoleAttribute)) }
        for dialog in dialogs {
            let elements = walk(dialog), allText = walk(dialog).flatMap(texts)
            if phase == "sending" || phase == "review" {
                guard let matched = matchedWindow, CFEqual(matched, dialog) else { continue }
                if SendJob.isSuccess(allText) {
                    if let ok = elements.first(where: { string($0, kAXRoleAttribute) == kAXButtonRole && texts($0).contains("OK") }) { _ = press(ok) }
                    finish("sent", "Kindle confirmed File sent for \(job.title)."); return
                }
                if allText.contains(where: { $0.localizedCaseInsensitiveContains("failed to send") || $0.localizedCaseInsensitiveContains("unable to send") }) {
                    finish("failed", "Kindle reported a sending error. Check its window before retrying."); return
                }
                continue
            }
            guard allText.contains("Title (required)"), allText.contains("Author name") else { continue }
            let fields = elements.filter { string($0, kAXRoleAttribute) == kAXTextFieldRole }
            let values = fields.map { string($0, kAXValueAttribute) }
            if phase == "waiting" {
                guard job.matches(fields: values) else { continue }
                matchedWindow = dialog
                guard AXUIElementSetAttributeValue(fields[0], kAXValueAttribute as CFString, job.title as CFString) == .success,
                      AXUIElementSetAttributeValue(fields[1], kAXValueAttribute as CFString, job.author as CFString) == .success else {
                    finish("failed", "Kindle did not accept the title and author. Nothing was sent."); return
                }
                phase = "verifying"; phaseStarted = Date(); return
            }
            guard let matched = matchedWindow, CFEqual(matched, dialog) else { continue }
            guard job.verified(fields: values) else { finish("failed", "The title or author changed before sending. Nothing was sent."); return }
            if preview { finish("preview_verified", "Title and author verified. Preview did not click Send."); return }
            if mode == "review" {
                phase = "review"; phaseStarted = Date(); record("review")
                label.stringValue = "Review the title and author in Kindle, then click Send."
                return
            }
            guard let send = elements.first(where: { string($0, kAXRoleAttribute) == kAXButtonRole && texts($0).contains("Send") }), (attribute(send, kAXEnabledAttribute) as? Bool) == true else { continue }
            // Persist before the click. An uncertain send is never retried automatically.
            guard record("sending") else { finish("failed", "Could not record the send attempt. Nothing was sent."); return }
            phase = "sending"; phaseStarted = Date()
            if !press(send) { finish("unconfirmed", "The Send action could not be confirmed. Check Kindle before retrying.") }
            return
        }
    }
}

@main struct Main {
    static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.regular)
        let delegate = AppDelegate(); app.delegate = delegate
        app.run(); withExtendedLifetime(delegate) {}
    }
}
