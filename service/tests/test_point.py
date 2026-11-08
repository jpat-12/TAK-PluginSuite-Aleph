"""Point lookup's street address, with Photon replaced by canned reverse-geocoding answers."""

import json
import unittest
from urllib.parse import parse_qs, urlsplit

from aleph_tak import point
from aleph_tak.config import DEFAULTS, merge

SETTINGS = merge(DEFAULTS, {})
HERE = (39.7984, -89.6440)


def feature(osm_id, lon, lat, **props):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": dict(osm_type="N", osm_id=osm_id, **props)}


class FakeClient:
    def __init__(self, features):
        self.features, self.requests = features, []

    def get(self, address, **_):
        self.requests.append(address)
        return json.dumps({"type": "FeatureCollection", "features": self.features}).encode()


class StreetAddressTests(unittest.TestCase):
    def test_nearest_house_number_wins_over_a_closer_street_only_result(self):
        client = FakeClient([
            feature(1, -89.64401, 39.79841, name="Lincoln Park", city="Springfield", state="Illinois"),
            feature(2, -89.64405, 39.79845, street="North 5th Street", city="Springfield", state="Illinois"),
            feature(3, -89.64410, 39.79850, housenumber="413", street="North 5th Street", postcode="62702",
                    city="Springfield", state="Illinois", country="United States"),
        ])
        found = point.street_address(client, SETTINGS, *HERE)
        self.assertEqual(found["label"], "413 North 5th Street, Springfield, Illinois 62702")
        self.assertTrue(found["exact"])
        self.assertEqual((found["housenumber"], found["postcode"]), ("413", "62702"))
        query = parse_qs(urlsplit(client.requests[0]).query)
        self.assertEqual(query["layer"], ["house"])
        self.assertEqual(urlsplit(client.requests[0]).path, "/reverse/")

    def test_falls_back_to_the_street_and_to_town_names(self):
        client = FakeClient([feature(2, -89.6441, 39.7985, street="County Road 12", village="Chatham", state="Illinois")])
        found = point.street_address(client, SETTINGS, *HERE)
        self.assertEqual(found["label"], "County Road 12, Chatham, Illinois")
        self.assertFalse(found["exact"])

    def test_nothing_with_a_street_is_none(self):
        self.assertIsNone(point.street_address(FakeClient([feature(1, -89.6441, 39.7985, name="Lake Springfield")]),
                                               SETTINGS, *HERE))

    def test_lookup_reports_a_geocoder_outage_per_part(self):
        class Down:
            def get(self, address, **_):
                raise OSError("photon down")
        result = point.lookup(Down(), SETTINGS, *HERE)
        self.assertIsNone(result["street_address"])
        self.assertIn("street_address", result["errors"])
        self.assertIn("elevation", result["errors"])


if __name__ == "__main__":
    unittest.main()
