"""Parses server_name/listen out of the nginx site config so they aren't duplicated in app config."""
import os
import re

SITE_CONF_PATH = os.environ.get(
    "NGINX_SITE_CONF", "/etc/nginx/sites-available/hound-coder.conf"
)
DEFAULT_SERVER_NAME = "localhost"

_SERVER_NAME_RE = re.compile(r"^\s*server_name\s+(\S+)\s*;", re.MULTILINE)
_LISTEN_RE = re.compile(r"^\s*listen\s+([^;]+);", re.MULTILINE)


def _read_site_conf() -> str:
    try:
        with open(SITE_CONF_PATH) as f:
            return f.read()
    except OSError:
        return ""


def get_server_name() -> str:
    match = _SERVER_NAME_RE.search(_read_site_conf())
    return match.group(1) if match else DEFAULT_SERVER_NAME


def get_base_url() -> str:
    """Builds scheme://host[:port] from the site config's server_name and listen directives.

    Prefers an SSL listen directive (https) over a plain one (http); omits the port
    when it matches the scheme's default (80 for http, 443 for https).
    """
    contents = _read_site_conf()
    host = get_server_name()

    ssl_port = plain_port = None
    for value in _LISTEN_RE.findall(contents):
        port_match = re.search(r"\d+", value)
        port = int(port_match.group()) if port_match else None
        if "ssl" in value:
            ssl_port = ssl_port if ssl_port is not None else port
        else:
            plain_port = plain_port if plain_port is not None else port

    if ssl_port is not None:
        scheme, port, default_port = "https", ssl_port, 443
    else:
        scheme, port, default_port = "http", plain_port, 80

    if port is not None and port != default_port:
        return f"{scheme}://{host}:{port}"
    return f"{scheme}://{host}"
