"""
Connect to a running LibreOffice instance over the UNO socket bridge.

This module deliberately does NOT start LibreOffice itself. The intended
workflow is interactive: you start LibreOffice once (visible, listening on a
socket), keep it running, and every script invocation reconnects to that same
live process. That way manual edits you make in the GUI are never lost and
are visible to the next automated call.

Start LibreOffice like this (adjust the profile path if you like -- using a
separate -env:UserInstallation profile avoids clashing with your normal
LibreOffice user profile / the single-instance lock it uses):

    soffice --impress \
        -env:UserInstallation=file:///tmp/lo_automation_profile \
        --accept="socket,host=localhost,port=2002;urp;" \
        --norestore --nologo

Then, from Python (must be run with an interpreter that can `import uno` --
on Fedora that's the system /usr/bin/python3, NOT a venv/conda env unless you
add LibreOffice's site-packages to its path):

    from slidebuilder.connection import connect
    ctx, desktop = connect()
"""

import subprocess
import time

import uno
from com.sun.star.connection import NoConnectException


DEFAULT_HOST = "localhost"
DEFAULT_PORT = 2002


def connect(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = 15.0):
    """Connect to a LibreOffice instance already listening on host:port.

    Returns (ctx, desktop). Raises ConnectionError if nothing is listening
    (or it doesn't come up) within `timeout` seconds.
    """
    local_ctx = uno.getComponentContext()
    resolver = local_ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local_ctx
    )
    uno_url = f"uno:socket,host={host},port={port};urp;StarOffice.ComponentContext"

    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            ctx = resolver.resolve(uno_url)
            smgr = ctx.ServiceManager
            desktop = smgr.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
            return ctx, desktop
        except NoConnectException as e:
            last_error = e
            time.sleep(0.5)

    raise ConnectionError(
        f"Could not connect to LibreOffice on {host}:{port} after {timeout}s. "
        "Is it running with --accept=\"socket,host=%s,port=%s;urp;\"? "
        "See slidebuilder/connection.py module docstring for the launch command. "
        f"Last error: {last_error}" % (host, port)
    )


def launch(
    profile_dir: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    visible: bool = True,
    startup_wait: float = 8.0,
):
    """Start a new LibreOffice process listening on host:port, using an
    isolated user profile so it won't collide with any LibreOffice instance
    you already have open normally.

    Returns the subprocess.Popen handle. Does not connect -- call connect()
    afterwards (it will poll/wait, so a short race is fine).
    """
    args = [
        "soffice",
        "--impress",
        f"-env:UserInstallation=file://{profile_dir}",
        f"--accept=socket,host={host},port={port};urp;",
        "--norestore",
        "--nologo",
    ]
    if not visible:
        args.insert(1, "--headless")

    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(startup_wait)
    return proc
