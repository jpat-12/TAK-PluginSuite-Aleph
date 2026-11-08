"""Tile downloading that survives flaky public servers.

Aleph's fetch() stops at the first tile that still fails after its retries; one USGS 502 then
throws away a whole imagery layer (seen in the first live Illinois capture). Here each tile's
outcome is reported on its own: bytes, None (the source has no data there — HTTP 404), or the
exception. The layer decides how many failures it tolerates, and since failed tiles aren't
written to disk, retrying the job fetches only the gaps.

Before a layer gives up on a tile it gets one automatic second pass (fetch_retrying): bursts of
502s from a rendering ImageServer usually clear within seconds, so most gaps never reach the user.
Whatever still fails is counted (Failures.count → the layer's `failed_tiles` stat) and the
clients offer a "Retry missing tiles" button, which re-runs the job and fetches only those.
"""

import time
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


RETRY_PAUSE_S = 5.0  # module-level so tests can zero it


def fetch_retrying(fetch, client, addresses, workers, on_retry=None):
    """Run `fetch` (fetch_each, or a test fake), then retry the tiles that errored once more after a
    short pause at half the concurrency. Yields (index, outcome) exactly once per address, failures
    from the first pass only after their second attempt."""
    failed = []
    for index, outcome in enumerate(fetch(client, addresses, workers)):
        if isinstance(outcome, Exception):
            failed.append(index)
        else:
            yield index, outcome
    if not failed:
        return
    if on_retry:
        on_retry(len(failed))
    deadline = time.monotonic() + RETRY_PAUSE_S
    while time.monotonic() < deadline:
        if client is not None:
            client.check_cancel()
        time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))
    yield from zip(failed, fetch(client, [addresses[i] for i in failed], max(1, workers // 2)))


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
