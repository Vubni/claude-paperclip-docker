"""Local Qt viewer for Linux and WSLg. Credentials never become browser URLs."""
import json
import os
from pathlib import Path
import re
import sys

from PyQt6.QtCore import QProcess, QTimer, QUrl
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox
from PyQt6.QtWebEngineCore import (
    QWebEnginePage, QWebEngineProfile, QWebEngineScript, QWebEngineSettings,
    QWebEngineUrlRequestInterceptor,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

ROOT = Path(__file__).resolve().parents[1]
APPS = {"claude": "Claude Workspace", "paperclip": "Paperclip Workspace", "browser": "Paperclip Browser"}


class LocalOnly(QWebEngineUrlRequestInterceptor):
    def __init__(self, url, parent):
        super().__init__(parent)
        self.host, self.port = url.host(), url.port()

    def allows(self, url):
        return (url.scheme() in ("http", "ws") and not url.userInfo()
                and (url.host(), url.port()) == (self.host, self.port))

    def interceptRequest(self, request):
        if not self.allows(request.requestUrl()):
            request.block(True)


class Page(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line, source):
        pass  # URLs and user content do not belong in launcher logs.

    def acceptNavigationRequest(self, url, kind, main):
        if self.window.filter.allows(url):
            return True
        if (self.window.mode == "paperclip" and main and url.scheme() == "https"
                and kind == self.NavigationType.NavigationTypeLinkClicked):
            QTimer.singleShot(0, lambda: self.window.external(url))
        return False


class Window(QMainWindow):
    def __init__(self, mode):
        super().__init__()
        self.mode = mode
        self.setWindowTitle(APPS[mode])
        self.resize(1200, 800)
        self.setCentralWidget(QLabel("Checking network and container readiness…"))
        self.process = QProcess(self)
        self.process.setStandardErrorFile(QProcess.nullDevice())
        self.process.finished.connect(self.prepared)
        self.process.errorOccurred.connect(self.failed_to_start)
        self.link = QProcess(self)
        self.link.setStandardOutputFile(QProcess.nullDevice())
        self.link.setStandardErrorFile(QProcess.nullDevice())
        self.link.finished.connect(self.link_finished)
        self.link.errorOccurred.connect(self.failed_to_start)
        QTimer.singleShot(0, self.start)

    def start(self):
        if self.mode == "claude":
            answer = QMessageBox.question(self, APPS[self.mode], "Open Claude in its Linux container? Sign-in and approval take place in that window.")
            if answer != QMessageBox.StandardButton.Yes:
                self.close()
                return
        self.process.start("/bin/bash", [str(ROOT / (APPS[self.mode] + ".source") /
                                             "Contents/Resources/Workspace.command"), "--viewer"])

    def failed_to_start(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            QMessageBox.warning(self, self.windowTitle(), "The workspace launcher could not start.")

    def prepared(self, code, status):
        if code or status != QProcess.ExitStatus.NormalExit:
            message = "Network or region policy blocked startup." if code == 43 else "Docker or the workspace did not become ready. See Troubleshooting in the README."
            self.setCentralWidget(QLabel(message))
            return
        token = None
        if self.mode == "paperclip":
            url = QUrl("http://localhost:43107")
        else:
            match = re.fullmatch(rb"([0-9]{1,5})\n([0-9a-f]{64})\n", bytes(self.process.readAllStandardOutput()))
            if not match or not 0 < int(match[1]) <= 65535:
                self.setCentralWidget(QLabel("The Linux viewer returned an invalid endpoint."))
                return
            url = QUrl(f"http://127.0.0.1:{int(match[1])}/workspace.html")
            token = match[2].decode("ascii")
        view = QWebEngineView(self)
        self.profile = (QWebEngineProfile("PaperclipWorkspace", self) if self.mode == "paperclip"
                        else QWebEngineProfile(self))
        self.filter = LocalOnly(url, self.profile)
        self.profile.setUrlRequestInterceptor(self.filter)
        self.profile.downloadRequested.connect(lambda download: download.cancel())
        self.page = Page(self.profile, view)
        self.page.window = self
        view.setPage(self.page)
        self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.DnsPrefetchEnabled, False)
        self.page.newWindowRequested.connect(self.new_window)
        if token:
            script = QWebEngineScript()
            script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
            script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            script.setRunsOnSubFrames(False)
            script.setSourceCode(f"if(location.href==={json.dumps(url.toString())})window.workspaceToken={json.dumps(token)};")
            self.page.scripts().insert(script)
        self.setCentralWidget(view)
        view.load(url)

    def new_window(self, request):
        url = request.requestedUrl()
        if request.isUserInitiated() and self.mode == "paperclip":
            if self.filter.allows(url):
                self.page.setUrl(url)
            elif url.scheme() == "https":
                self.external(url)

    def external(self, url):
        if (not url.host() or url.userInfo() or self.link.state() != QProcess.ProcessState.NotRunning
                or not self.filter.allows(self.page.url())):
            return
        if QMessageBox.question(self, "Paperclip Browser", f"Open {url.host()} in the separate Linux Firefox?") != QMessageBox.StandardButton.Yes:
            return
        self.link.start("/bin/bash", [str(ROOT / "Paperclip Workspace.source/Contents/Resources/open-linux-link.sh")])
        self.link.write(url.toEncoded() + b"\n")
        self.link.closeWriteChannel()

    def link_finished(self, code, status):
        if code or status != QProcess.ExitStatus.NormalExit:
            QMessageBox.warning(self, "Paperclip Browser", "The link was blocked or Firefox could not start.")
        else:
            QProcess.startDetached("/usr/bin/python3", [str(Path(__file__).resolve()), "browser"])


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in APPS:
        sys.exit("Usage: viewer.py {claude|paperclip|browser}")
    if os.geteuid() == 0:
        sys.exit("Run the viewer as your desktop user.")
    # The host window displays only loopback content. Disable speculative network
    # activity as well as unproxied WebRTC UDP in the embedded Chromium process.
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = ("--disable-background-networking "
        "--disable-quic --force-webrtc-ip-handling-policy=disable_non_proxied_udp")
    app = QApplication(sys.argv)
    app.setApplicationName("Claude Paperclip Workspace")
    window = Window(sys.argv[1])
    window.show()
    sys.exit(app.exec())
