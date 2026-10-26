"""Tile downloading that survives flaky public servers.

Aleph's fetch() stops at the first tile that still fails after its retries; one USGS 502 then
throws away a whole imagery layer (seen in the first live Illinois capture). Here each tile's
outcome is reported on its own: bytes, None (the source has no data there — HTTP 404), or the
exception. The layer decides how many failures it tolerates, and since failed tiles aren't
written to disk, retrying the job fetches only the gaps.
"""

from collections import deque
from concurrent.futures import ThreadPoolExecutor

from .core.common import MissingImagery


def fetch_each(client, addresses, workers):
    def get(address):
        try:
            return client.get(address, missing_ok=True)
        except MissingImagery:
            return None
        except Exception as error:  # reported per tile; cancellation is re-checked by the caller
            return error

    pending = deque()
    addresses = iter(addresses)
    with ThreadPoolExecutor(workers) as pool:
        try:
            for address in addresses:
                pending.append(pool.submit(get, address))
                if len(pending) >= 2 * workers:
                    client.check_cancel()
                    yield pending.popleft().result()
            while pending:
                client.check_cancel()
                yield pending.popleft().result()
        finally:
            for future in pending:
                future.cancel()


class Failures:
    """Count per-tile errors; raise if too many to be worth packaging."""

    def __init__(self, label, total, tolerance=0.25):
        self.label, self.total, self.tolerance = label, total, tolerance
        self.count, self.first = 0, None

    def add(self, error):
        self.count += 1
        self.first = self.first or error

    def check(self, downloaded_any):
        if self.count and (not downloaded_any or self.count > self.total * self.tolerance):
            raise OSError(f"{self.label}: {self.count} of {self.total} tiles failed ({self.first}). "
                          "Retry the capture to fetch only the missing tiles.")

    def warning(self):
        if self.count:
            return (f"{self.label}: {self.count} of {self.total} tiles failed to download and are blank; "
                    "retry the capture to fill them in.")
        return None
