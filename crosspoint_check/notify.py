"""One message per scan that changed something, as JSON to a webhook (Home Assistant, ntfy, ...)."""
import json
import urllib.request


def summary(repaired, failed):
    parts = []
    if repaired:
        parts.append('repaired %s' % ', '.join(b['title'] for b in repaired))
    if failed:
        parts.append('cannot repair %s' % ', '.join(b['title'] for b in failed))
    return '; '.join(parts)


def send(url, repaired, failed, page_url='', log=print):
    """POST {title, message, repaired, failed, url}. Never raises: a lost message must not stop a scan."""
    if not url or not (repaired or failed):
        return False
    body = {
        'title': 'crosspoint-check',
        'message': summary(repaired, failed),
        'repaired': [{'id': b['id'], 'title': b['title'], 'author': b['author']} for b in repaired],
        'failed': [{'id': b['id'], 'title': b['title'], 'author': b['author']} for b in failed],
        'url': page_url,
    }
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method='POST',
                                 headers={'Content-Type': 'application/json', 'User-Agent': 'crosspoint-check'})
    try:
        with urllib.request.urlopen(req, timeout=20):
            return True
    except Exception as e:
        log('notification not sent: %s' % e)
        return False
