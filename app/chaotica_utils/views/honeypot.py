"""
Honeypot / canary "web shell" easter egg.

To a vulnerability scanner this looks like a web shell someone left behind on a
compromised host — a classic "you've been owned" artifact at a commonly probed
URL. It is completely inert: it never runs anything. Every "command" returns
canned, hard-coded text via a simple if/else. The second command rickrolls.

Gated behind the ``FAKE_HONEYPOT_ENABLED`` constance flag (see settings.py).
When the flag is off the endpoints 404 so the decoy simply isn't there.

There is deliberately NO os/subprocess/eval/exec anywhere in this module. If a
future edit is tempted to make it "actually work" — don't. The joke, and the
safety, is that it is fake.
"""
from django.http import JsonResponse, HttpResponseNotFound
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from constance import config


RICKROLL_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

RICKROLL_OUTPUT = "\n".join(
    [
        "Never gonna give you up",
        "Never gonna let you down",
        "Never gonna run around and desert you",
        "Never gonna make you cry",
        "Never gonna say goodbye",
        "Never gonna tell a lie and hurt you",
    ]
)


def _fake_output(cmd):
    """Return canned, believable output for common recon commands.

    Pure string lookup — nothing here touches the OS.
    """
    c = cmd.strip()
    low = c.lower()

    if low == "whoami":
        return "root"
    if low == "id":
        return "uid=0(root) gid=0(root) groups=0(root)"
    if low == "pwd":
        return "/var/www/html"
    if low == "hostname":
        return "web-prod-01"
    if low.startswith("uname"):
        return "Linux web-prod-01 5.15.0-91-generic #101-Ubuntu SMP x86_64 GNU/Linux"
    if low == "dir" or low.startswith("ls"):
        return "\n".join(
            [
                "total 28",
                "drwxr-xr-x  4 root root 4096 Jan  1 03:14 .",
                "drwxr-xr-x 18 root root 4096 Jan  1 03:14 ..",
                "-rw-r--r--  1 root root  517 Jan  1 03:14 config.php",
                "-rw-r--r--  1 root root 2048 Jan  1 03:14 index.php",
                "-rw-r--r--  1 root root   66 Jan  1 03:14 shell.php",
                "drwxr-xr-x  2 root root 4096 Jan  1 03:14 uploads",
            ]
        )
    if low.startswith("cat /etc/passwd"):
        return "\n".join(
            [
                "root:x:0:0:root:/root:/bin/bash",
                "daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin",
                "www-data:x:33:33:www-data:/var/www:/usr/sbin/nologin",
                "nice-try:x:1337:1337:reformed:/home/curiosity:/bin/false",
            ]
        )
    if low.startswith("cat"):
        target = c[3:].strip() or "?"
        return "cat: " + target + ": Permission denied"
    if low.startswith("ps"):
        return "\n".join(
            [
                "  PID TTY          TIME CMD",
                "    1 ?        00:00:01 systemd",
                "  842 ?        00:00:12 apache2",
                " 1337 ?        00:00:00 definitely_not_a_miner",
            ]
        )
    if low in ("", "help"):
        return "This box has clearly seen better days. Try a command."

    # Generic believable fallback for anything else.
    return "sh: 1: " + c.split()[0] + ": not found"


def _enabled():
    return bool(getattr(config, "FAKE_HONEYPOT_ENABLED", False))


@csrf_exempt
@require_http_methods(["GET", "POST"])
def fake_shell(request):
    """Serve the decoy shell page (GET) and canned command output (POST)."""
    if not _enabled():
        return HttpResponseNotFound()

    if request.method == "GET":
        # Fresh page load resets the per-session command counter.
        request.session["honeypot_cmds"] = 0
        resp = render(request, "honeypot/shell.html")
        # Dress the response up as a crusty legacy PHP host so scanners bite.
        resp["X-Powered-By"] = "PHP/5.3.3"
        resp["Server"] = "Apache/2.2.15 (CentOS)"
        return resp

    # POST: "run" a command. Nothing is ever executed — canned text only.
    cmd = (request.POST.get("cmd") or "").strip()
    count = int(request.session.get("honeypot_cmds", 0) or 0) + 1
    request.session["honeypot_cmds"] = count

    if count >= 2:
        return JsonResponse(
            {
                "output": RICKROLL_OUTPUT,
                "rickroll": True,
                "rickroll_url": RICKROLL_URL,
            }
        )

    return JsonResponse({"output": _fake_output(cmd), "rickroll": False})
