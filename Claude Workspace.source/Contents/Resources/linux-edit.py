"""Text clipboard and editing shortcuts for the active X11 viewer."""
import base64
import ctypes as c
import hashlib
import queue
import sys
import threading


def bind(library, name, result, *arguments):
    function = getattr(library, name)
    function.restype = result
    function.argtypes = arguments
    return function


ptr, integer, string = c.c_void_p, c.c_int, c.c_char_p
gtk = c.CDLL("libgtk-3.so.0")
gdk = c.CDLL("libgdk-3.so.0")
glib = c.CDLL("libglib-2.0.so.0")
gobject = c.CDLL("libgobject-2.0.so.0")
x11 = c.CDLL("libX11.so.6")
xtst = c.CDLL("libXtst.so.6")

if not bind(gtk, "gtk_init_check", integer, ptr, ptr)(None, None):
    sys.exit(1)
atom = bind(gdk, "gdk_atom_intern_static_string", ptr, string)(b"CLIPBOARD")
clipboard = bind(gtk, "gtk_clipboard_get", ptr, ptr)(atom)
request_text = bind(gtk, "gtk_clipboard_request_text", None, ptr, ptr, ptr)
set_text = bind(gtk, "gtk_clipboard_set_text", None, ptr, string, integer)
display = bind(x11, "XOpenDisplay", ptr, string)(None)
if not display:
    sys.exit(1)
selection = bind(x11, "XInternAtom", c.c_ulong, ptr, string, integer)(display, b"CLIPBOARD", 0)
owner = bind(x11, "XGetSelectionOwner", c.c_ulong, ptr, c.c_ulong)
keycode = bind(x11, "XKeysymToKeycode", c.c_uint, ptr, c.c_ulong)
send_key = bind(xtst, "XTestFakeKeyEvent", integer, ptr, c.c_uint, integer, c.c_ulong)
flush = bind(x11, "XFlush", integer, ptr)
gdk_flush = bind(gdk, "gdk_display_sync", None, ptr)
gdk_display = bind(gdk, "gdk_display_get_default", ptr)()
idle_add = bind(glib, "g_idle_add", c.c_uint, ptr, ptr)
timeout_add = bind(glib, "g_timeout_add", c.c_uint, c.c_uint, ptr, ptr)
quit_loop = bind(gtk, "gtk_main_quit", None)
commands = queue.Queue()
our_owner = 0
generation = 0
last_digest = None
pending_check = False


@c.CFUNCTYPE(None, ptr, string, ptr)
def received_text(_clipboard, text, request):
    global last_digest
    version, reason = divmod(request, 3)
    if version != generation:
        return
    digest = hashlib.sha256(text).digest() if text else None
    changed = digest != last_digest
    last_digest = digest
    if text and (reason == 1 or (reason == 2 and changed)):
        sys.stdout.buffer.write(base64.b64encode(text) + b"\n")
        sys.stdout.buffer.flush()


def read_clipboard(reason):
    current = owner(display, selection)
    if current and current != our_owner:
        request_text(clipboard, received_text, generation * 3 + reason)


@c.CFUNCTYPE(None, ptr, ptr, ptr)
def owner_changed(_clipboard, _event, _data):
    global generation
    generation += 1
    read_clipboard(1)


@c.CFUNCTYPE(integer, ptr)
def after_gesture(_data):
    global pending_check
    pending_check = False
    read_clipboard(2)
    return 0


def shortcut(letter, redo=False):
    modifiers = [0xffe3, 0xffe1] if redo else [0xffe3]
    for symbol in modifiers + [ord(letter)]:
        send_key(display, keycode(display, symbol), 1, 0)
    for symbol in [ord(letter)] + modifiers[::-1]:
        send_key(display, keycode(display, symbol), 0, 0)
    flush(display)


@c.CFUNCTYPE(integer, ptr)
def dispatch(_data):
    global our_owner, pending_check
    command = commands.get_nowait()
    if not command:
        quit_loop()
    elif command.startswith(b"paste "):
        text = base64.b64decode(command[6:], validate=True)
        set_text(clipboard, text, len(text))
        gdk_flush(gdk_display)
        our_owner = owner(display, selection)
        shortcut("v")
    elif command == b"redo":
        shortcut("z", redo=True)
    elif command in (b"a", b"c", b"x", b"z", b"f"):
        shortcut(command.decode("ascii"))
    # Some X11 apps update their clipboard without claiming ownership again.
    if command in (b"check", b"c", b"x") and not pending_check:
        pending_check = True
        timeout_add(180, after_gesture, None)
    return 0


def read_commands():
    try:
        for line in sys.stdin.buffer:
            commands.put(line.rstrip(b"\n"))
            idle_add(dispatch, None)
    finally:
        commands.put(None)
        idle_add(dispatch, None)


bind(gobject, "g_signal_connect_data", c.c_ulong, ptr, string, ptr, ptr, ptr, integer)(
    clipboard, b"owner-change", owner_changed, None, None, 0)
generation = 1
read_clipboard(0)  # Establish a comparison baseline without exporting old text.
threading.Thread(target=read_commands, daemon=True).start()
bind(gtk, "gtk_main", None)()
