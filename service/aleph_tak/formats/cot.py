"""CoT events for photo markers. Type b-i-x-i is ATAK's own Quick Pic marker, so a photo shows
up as an image point whose attachment (linked by UID in the package manifest) opens on tap."""

from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import quoteattr, escape


def _stamp(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def photo_marker(uid, lat, lon, callsign, remarks, *, stale_days=365):
    moment = datetime.now(timezone.utc)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<event version="2.0" uid={quoteattr(uid)} type="b-i-x-i" how="h-e" '
        f'time="{_stamp(moment)}" start="{_stamp(moment)}" stale="{_stamp(moment + timedelta(days=stale_days))}">'
        f'<point lat="{lat:.7f}" lon="{lon:.7f}" hae="9999999.0" ce="9999999.0" le="9999999.0"/>'
        f'<detail><contact callsign={quoteattr(callsign)}/><remarks>{escape(remarks)}</remarks>'
        '<archive/></detail></event>\n'
    )
