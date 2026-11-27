import AppKit
import WebKit

private let home = URL(string: "http://localhost:43107")!
private func local(_ url: URL?) -> Bool {
    guard let url else { return false }
    return url.scheme == home.scheme && url.host == home.host && url.port == home.port
        && url.user == nil && url.password == nil
}

final class Workspace: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    private var window: NSWindow!
    private var web: WKWebView?
    private let setup = Process()
    private var openingLink = false

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
        appMenu.addItem(withTitle: "Завершить Paperclip", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        menu.addItem(withTitle: "Paperclip", action: nil, keyEquivalent: "").submenu = appMenu
        let edit = NSMenu(title: "Правка")
        for (name, action, key) in [("Отменить", "undo:", "z"), ("Вырезать", "cut:", "x"), ("Скопировать", "copy:", "c"), ("Вставить", "paste:", "v"), ("Выбрать всё", "selectAll:", "a")] {
            edit.addItem(withTitle: name, action: Selector(action), keyEquivalent: key)
        }
        menu.addItem(withTitle: edit.title, action: nil, keyEquivalent: "").submenu = edit
        let view = NSMenu(title: "Окно")
        view.addItem(withTitle: "Назад", action: #selector(back), keyEquivalent: "[")
        view.addItem(withTitle: "Вперёд", action: #selector(forward), keyEquivalent: "]")
        view.addItem(withTitle: "Обновить страницу", action: #selector(reload), keyEquivalent: "r")
        view.addItem(withTitle: "Закрыть окно", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        menu.addItem(withTitle: view.title, action: nil, keyEquivalent: "").submenu = view
        NSApp.mainMenu = menu

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1100, height: 760),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Paperclip Workspace"
        window.isReleasedWhenClosed = false
        window.center()
        window.setFrameAutosaveName("PaperclipWorkspace")
        let status = NSTextField(labelWithString: "Запускаем Paperclip…")
        status.translatesAutoresizingMaskIntoConstraints = false
        let content = window.contentView!
        content.addSubview(status)
        NSLayoutConstraint.activate([status.centerXAnchor.constraint(equalTo: content.centerXAnchor), status.centerYAnchor.constraint(equalTo: content.centerYAnchor)])
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        setup.executableURL = Bundle.main.url(forResource: "Workspace", withExtension: "command")
        setup.arguments = ["--check"]
        setup.standardOutput = FileHandle.nullDevice
        setup.standardError = FileHandle.nullDevice
        setup.terminationHandler = { process in
            DispatchQueue.main.async {
                if process.terminationStatus == 0 { self.openLocalPage() }
                else if process.terminationStatus == 43 { self.fail("Проверка страны выхода с Mac или из Docker заблокировала запуск. Проверьте VPN.") }
                else { self.fail("Лаунчеру не удалось подготовить Docker или дождаться готовности Paperclip.") }
            }
        }
        do { try setup.run() } catch { fail("Не удалось запустить проверку Paperclip.") }
    }

    private func openLocalPage() {
        // Cancel network resources outside the exact UI origin, including other loopback ports.
        let rules = #"[{"trigger":{"url-filter":"^[a-z]+://"},"action":{"type":"block"}},{"trigger":{"url-filter":"^http://localhost:43107/"},"action":{"type":"ignore-previous-rules"}},{"trigger":{"url-filter":"^ws://localhost:43107/"},"action":{"type":"ignore-previous-rules"}}]"#
        WKContentRuleListStore.default().compileContentRuleList(forIdentifier: "PaperclipLoopbackV1", encodedContentRuleList: rules) { list, _ in
            guard let list else { self.fail("Не удалось включить сетевые ограничения окна."); return }
            let config = WKWebViewConfiguration()
            config.websiteDataStore = .default()
            config.applicationNameForUserAgent = "PaperclipWorkspace/1"
            config.userContentController.add(list)
            let page = WKWebView(frame: .zero, configuration: config)
            page.navigationDelegate = self
            page.uiDelegate = self
            self.web = page
            self.window.contentView = page
            self.window.makeFirstResponder(page)
            page.load(URLRequest(url: home))
        }
    }

    private func fail(_ message: String) {
        let alert = NSAlert()
        alert.messageText = "Paperclip Workspace"
        alert.informativeText = message
        alert.runModal()
        NSApp.terminate(nil)
    }

    @objc private func back() { web?.goBack() }
    @objc private func forward() { web?.goForward() }
    @objc private func reload() { web?.reload() }

    private func offerLinuxBrowser(_ url: URL?) {
        guard window.attachedSheet == nil, !openingLink else { return }
        let alert = NSAlert()
        guard let url, url.scheme == "https", let host = url.host, !host.isEmpty,
              url.user == nil, url.password == nil, url.absoluteString.utf8.count <= 4096 else {
            alert.messageText = "Открытие ссылки заблокировано"
            alert.informativeText = "В браузере Linux можно открыть HTTPS-ссылку без встроенного логина и пароля."
            alert.beginSheetModal(for: window)
            return
        }
        alert.messageText = "Открыть сайт в Firefox внутри Linux?"
        let destination = host + (url.port.map { ":\($0)" } ?? "")
        alert.informativeText = "Сайт \(destination) откроется в отдельном окне «Браузер Paperclip» внутри Linux. После входа вернитесь в Paperclip."
        alert.addButton(withTitle: "Отмена")
        alert.addButton(withTitle: "Открыть в Linux")
        alert.beginSheetModal(for: window) { choice in
            if choice == .alertSecondButtonReturn { self.openLinuxLink(url) }
        }
    }

    private func openLinuxLink(_ url: URL) {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/bin/bash")
        guard let script = Bundle.main.path(forResource: "open-linux-link", ofType: "sh") else { return }
        task.arguments = [script]
        let input = Pipe()
        task.standardInput = input
        task.standardOutput = FileHandle.nullDevice
        task.standardError = FileHandle.nullDevice
        openingLink = true
        window.title = "Paperclip Workspace — открываем Firefox в Linux…"
        task.terminationHandler = { process in
            DispatchQueue.main.async { self.finishedOpeningLink(process.terminationStatus) }
        }
        do {
            try task.run()
        } catch {
            finishedOpeningLink(1)
            return
        }
        let payload = Data((url.absoluteString + "\n").utf8)
        DispatchQueue.global().async {
            try? input.fileHandleForWriting.write(contentsOf: payload)
            try? input.fileHandleForWriting.close()
        }
    }

    private func finishedOpeningLink(_ status: Int32) {
        openingLink = false
        window.title = "Paperclip Workspace"
        guard status != 0 else { return }
        let alert = NSAlert()
        alert.messageText = "Не удалось открыть ссылку в Linux"
        alert.informativeText = status == 43 ? "Проверка страны выхода заблокировала переход. Проверьте VPN." : "Проверьте, что Docker Desktop и «Браузер Paperclip» доступны, и повторите переход."
        alert.beginSheetModal(for: window)
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        window?.deminiaturize(nil)
        window?.makeKeyAndOrderFront(nil)
        return true
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func webView(_ view: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        let url = action.request.url
        let localBlob = url?.absoluteString.hasPrefix("blob:http://localhost:43107/") == true
        if action.shouldPerformDownload && (local(url) || localBlob) { decisionHandler(.download); return }
        guard local(url) else {
            decisionHandler(.cancel)
            if action.navigationType == .linkActivated, action.sourceFrame.isMainFrame,
               local(action.sourceFrame.request.url), action.request.httpMethod == "GET" {
                offerLinuxBrowser(url)
            }
            return
        }
        if action.targetFrame == nil {
            decisionHandler(.cancel)
            view.load(action.request)
        } else { decisionHandler(.allow) }
    }

    func webView(_ view: WKWebView, decidePolicyFor response: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        guard local(response.response.url) else { decisionHandler(.cancel); return }
        decisionHandler(response.canShowMIMEType ? .allow : .download)
    }

    func webView(_ view: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { download.delegate = self }
    func webView(_ view: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) { download.delegate = self }

    func download(_ download: WKDownload, willPerformHTTPRedirection response: HTTPURLResponse,
                  newRequest request: URLRequest, decisionHandler: @escaping (WKDownload.RedirectPolicy) -> Void) {
        decisionHandler(local(request.url) ? .allow : .cancel)
    }

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String,
                  completionHandler: @escaping (URL?) -> Void) {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = (suggestedFilename as NSString).lastPathComponent
        panel.beginSheetModal(for: window) { completionHandler($0 == .OK ? panel.url : nil) }
    }

    func webView(_ view: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.canChooseDirectories = parameters.allowsDirectories
        panel.beginSheetModal(for: window) { completionHandler($0 == .OK ? panel.urls : nil) }
    }

    func webView(_ view: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        if (error as NSError).code != NSURLErrorCancelled && view.url == nil {
            fail("Не удалось открыть локальную страницу Paperclip.")
        }
    }
}

let app = NSApplication.shared
let workspace = Workspace()
app.setActivationPolicy(.regular)
app.delegate = workspace
app.run()
