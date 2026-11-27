import AppKit
import WebKit

final class Workspace: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    private let viewerName = Bundle.main.object(forInfoDictionaryKey: "CFBundleName") as? String ?? "Claude Workspace"
    private var window: NSWindow!
    private var viewer: WKWebView?
    private var viewerURL: URL?
    private var editProcess: Process?
    private let editWrites = DispatchQueue(label: "workspace.edit-commands")
    private var editInput: FileHandle?

    @objc private func editRegionSettings() {
        guard let folder = Bundle.main.resourceURL else { return }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = ["-B", folder.appendingPathComponent("region/settings.py").path]
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        try? process.run()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let menu = NSMenu()
        let appMenu = NSMenu()
        let regionSettings = appMenu.addItem(withTitle: "Настройки региона…", action: #selector(editRegionSettings), keyEquivalent: ",")
        regionSettings.target = self
        appMenu.addItem(withTitle: "Завершить просмотр", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        menu.addItem(withTitle: viewerName, action: nil, keyEquivalent: "").submenu = appMenu
        let edit = NSMenu(title: "Правка")
        for (title, key, command) in [
            ("Отменить", "z", "z"), ("Повторить", "z", "redo"),
            ("Вырезать", "x", "x"), ("Скопировать", "c", "c"),
            ("Вставить в Linux", "v", "paste"), ("Выделить всё", "a", "a"),
            ("Найти", "f", "f")
        ] {
            let item = edit.addItem(withTitle: title, action: #selector(editLinux(_:)), keyEquivalent: key)
            item.representedObject = command
            item.target = self
            if command == "redo" { item.keyEquivalentModifierMask = [.command, .shift] }
        }
        menu.addItem(withTitle: edit.title, action: nil, keyEquivalent: "").submenu = edit
        let windows = NSMenu(title: "Окно")
        windows.addItem(withTitle: "Закрыть", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        menu.addItem(withTitle: windows.title, action: nil, keyEquivalent: "").submenu = windows
        NSApp.mainMenu = menu

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1152, height: 720),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = viewerName
        window.isReleasedWhenClosed = false
        window.center()
        window.setFrameAutosaveName(viewerName == "Claude Workspace" ? "ClaudeLinuxDesktop" : viewerName)
        let status = NSTextField(labelWithString: "Подключаемся к окну Linux…")
        status.translatesAutoresizingMaskIntoConstraints = false
        let view = window.contentView!
        view.addSubview(status)
        NSLayoutConstraint.activate([status.centerXAnchor.constraint(equalTo: view.centerXAnchor), status.centerYAnchor.constraint(equalTo: view.centerYAnchor)])
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        guard let script = Bundle.main.url(forResource: "Workspace", withExtension: "command") else {
            fail("В пакете отсутствует файл запуска.")
            return
        }
        DispatchQueue.global().async {
            let setup = Process()
            let pipe = Pipe()
            setup.executableURL = script
            setup.arguments = ["--viewer"]
            setup.standardOutput = pipe
            setup.standardError = FileHandle.nullDevice
            do { try setup.run() } catch {
                DispatchQueue.main.async { self.fail("Не удалось запустить подготовку Docker.") }
                return
            }
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            setup.waitUntilExit()
            let fields = String(decoding: data, as: UTF8.self).split(whereSeparator: { $0.isWhitespace })
            DispatchQueue.main.async {
                if setup.terminationStatus == 43 {
                    self.fail("Страна выхода Mac или Docker не прошла проверку. Проверьте VPN.")
                } else if setup.terminationStatus == 0, fields.count == 2,
                          let port = UInt16(fields[0]), port > 0, fields[1].count == 64,
                          fields[1].allSatisfy({ "0123456789abcdef".contains($0) }) {
                    self.openViewer(port: port, token: String(fields[1]))
                } else {
                    let reasons: [Int32: String] = [
                        51: "Docker Desktop не запустился.",
                        52: "Docker не смог подготовить контейнер Linux.",
                        61: "Не удалось запустить службу связки ключей Linux.",
                        62: "Виртуальный экран Linux не запустился.",
                        63: "Завершилась служба передачи изображения Linux.",
                        64: "Завершилась служба подключения к экрану Linux.",
                        65: "Графическое приложение в Linux завершился до открытия окна.",
                        66: "Контейнер Linux остановился до открытия окна.",
                        67: "За 90 секунд окно Claude в Linux не стало доступно."
                    ]
                    self.fail(reasons[setup.terminationStatus] ?? "Не удалось получить подключение к окну Linux.")
                }
            }
        }
    }

    private func openViewer(port: UInt16, token: String) {
        let url = URL(string: "http://127.0.0.1:\(port)/workspace.html")!
        viewerURL = url
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        let bootstrap = "if (location.href === '\(url.absoluteString)') window.workspaceToken = '\(token)';"
        config.userContentController.addUserScript(WKUserScript(source: bootstrap, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        // AppKit handles Command shortcuts. noVNC otherwise sends Command as Alt to X11.
        let commandKeys = """
        for (const event of ['keydown', 'keyup']) {
            window.addEventListener(event, e => {
                if (e.key === 'Meta' || (event === 'keydown' && e.metaKey && !['Shift','Control','Alt'].includes(e.key))) {
                    e.stopImmediatePropagation();
                }
            }, true);
        }
        """
        config.userContentController.addUserScript(WKUserScript(source: commandKeys, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        let page = WKWebView(frame: .zero, configuration: config)
        page.navigationDelegate = self
        viewer = page
        window.contentView = page
        window.makeFirstResponder(page)
        page.load(URLRequest(url: url))
        startEditing()
    }

    func webView(_ view: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        decisionHandler(action.request.url == viewerURL && action.targetFrame?.isMainFrame == true ? .allow : .cancel)
    }

    private func startEditing() {
        let task = Process()
        let input = Pipe(), output = Pipe()
        do {
            let script = try String(contentsOf: Bundle.main.resourceURL!.appendingPathComponent("linux-edit.py"), encoding: .utf8)
            task.executableURL = URL(fileURLWithPath: "/Applications/Docker.app/Contents/Resources/bin/docker")
            task.currentDirectoryURL = Bundle.main.resourceURL
            task.arguments = ["--context", "desktop-linux", "compose", "exec", "-T", "desktop", "python3", "-c", script]
            task.standardInput = input
            task.standardOutput = output
            task.standardError = FileHandle.nullDevice
            try task.run()
        } catch {
            window.title = viewerName + " — буфер обмена недоступен"
            return
        }
        editInput = input.fileHandleForWriting
        editProcess = task
        NSEvent.addLocalMonitorForEvents(matching: [.leftMouseUp, .rightMouseUp, .keyUp]) { event in
            let copyKey = event.modifierFlags.contains(.control) && ["c", "x"].contains(event.charactersIgnoringModifiers ?? "")
            if event.window === self.window && (event.type != .keyUp || copyKey) {
                self.sendCommand("check")
            }
            return event
        }
        DispatchQueue.global().async {
            var pending = Data()
            let file = output.fileHandleForReading
            while true {
                let chunk = file.availableData
                if chunk.isEmpty { break }
                pending.append(chunk)
                while let end = pending.firstIndex(of: 10) {
                    let line = pending[..<end]
                    if let bytes = Data(base64Encoded: line), let text = String(data: bytes, encoding: .utf8) {
                        DispatchQueue.main.async {
                            let pasteboard = NSPasteboard.general
                            pasteboard.clearContents()
                            pasteboard.setString(text, forType: .string)
                        }
                    }
                    pending.removeSubrange(...end)
                }
            }
            DispatchQueue.main.async {
                self.editInput = nil
                self.window.title = self.viewerName + " — буфер обмена недоступен"
            }
        }
    }

    @objc private func editLinux(_ sender: NSMenuItem) {
        guard editInput != nil, var command = sender.representedObject as? String else { NSSound.beep(); return }
        if command == "paste" {
            guard let text = NSPasteboard.general.string(forType: .string) else { NSSound.beep(); return }
            command += " " + Data(text.utf8).base64EncodedString()
        }
        sendCommand(command)
    }

    private func sendCommand(_ command: String) {
        guard let input = editInput else { return }
        let line = Data((command + "\n").utf8)
        editWrites.async { try? input.write(contentsOf: line) }
    }

    func applicationWillTerminate(_ notification: Notification) {
        if let input = editInput { editWrites.async { try? input.close() } }
    }

    private func fail(_ message: String) {
        let alert = NSAlert()
        alert.messageText = viewerName
        alert.informativeText = message
        alert.runModal()
        NSApp.terminate(nil)
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows: Bool) -> Bool {
        window?.deminiaturize(nil)
        window?.makeKeyAndOrderFront(nil)
        return true
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

let app = NSApplication.shared
signal(SIGPIPE, SIG_IGN)
let workspace = Workspace()
app.setActivationPolicy(.regular)
app.delegate = workspace
app.run()
