"""Opening an agent in a new terminal window. Only macOS Terminal.app for now."""
import shlex
import subprocess


def open_terminal(script):
    # The window title comes from Claude Code (the session name); Terminal adds the command, so keep it short.
    cmd = f"bash {shlex.quote(str(script))}"
    osa = f'tell application "Terminal"\n do script "{cmd}"\n activate\nend tell'
    subprocess.run(["osascript", "-e", osa], check=True, capture_output=True)
