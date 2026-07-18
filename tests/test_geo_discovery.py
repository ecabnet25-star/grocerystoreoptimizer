import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from grocery_optimizer.geo_discovery import (
    GeoPoint,
    discover_food_places,
    geocode_address,
    geocode_postal_code,
)


def _make_http_response(payload):
    """Create a mock urlopen response returning the given JSON-serializable payload."""
    raw = json.dumps(payload).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = raw
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestGeocodePostalCode(unittest.TestCase):
    """Tests for geocode_postal_code() with mocked HTTP calls."""

    @patch("grocery_optimizer.geo_discovery.load_postal_codes")
    def test_returns_local_lookup_when_present(self, mock_load_pc):
        """When the postal code is in local data, Nominatim is not called."""
        from grocery_optimizer.stores import PostalCodeInfo

        mock_load_pc.return_value = {
            "H3A1A1": PostalCodeInfo(
                postal_code="H3A1A1",
                latitude=45.5017,
                longitude=-73.5673,
                city="Montreal",
                province_state="QC",
                country="CA",
            )
        }

        result = geocode_postal_code("H3A1A1")
        self.assertIsNotNone(result)
        self.assertIsInstance(result, GeoPoint)
        self.assertAlmostEqual(result.latitude, 45.5017, places=3)
        self.assertAlmostEqual(result.longitude, -73.5673, places=3)
        self.assertIn("Montreal", result.display_name)
        self.assertEqual(result.country_code, "ca")

    @patch("grocery_optimizer.geo_discovery.load_postal_codes", return_value={})
    @patch("grocery_optimizer.geo_discovery._http_get_json")
    def test_falls_back_to_nominatim(self, mock_http, mock_load_pc):
        """When local data is missing, Nominatim JSON is parsed correctly."""
        mock_http.return_value = [
            {
                "lat": "48.8566",
                "lon": "2.3522",
                "display_name": "Paris, France",
                "address": {"country_code": "fr"},
            }
        ]

        result = geocode_postal_code("75001", country_hint="France")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.latitude, 48.8566, places=3)
        self.assertAlmostEqual(result.longitude, 2.3522, places=3)
        self.assertEqual(result.country_code, "fr")
        self.assertIn("Paris", result.display_name)

    @patch("grocery_optimizer.geo_discovery.load_postal_codes", return_value={})
    @patch("grocery_optimizer.geo_discovery._http_get_json", return_value=None)
    def test_returns_none_when_nominatim_fails(self, mock_http, mock_load_pc):
        result = geocode_postal_code("ZZZZZZ")
        self.assertIsNone(result)

    @patch("grocery_optimizer.geo_discovery.load_postal_codes", return_value={})
    @patch("grocery_optimizer.geo_discovery._http_get_json", return_value=[])
    def test_returns_none_for_empty_nominatim_response(self, mock_http, mock_load_pc):
        result = geocode_postal_code("00000")
        self.assertIsNone(result)

    @patch("grocery_optimizer.geo_discovery.load_postal_codes", return_value={})
    @patch("grocery_optimizer.geo_discovery._http_get_json")
    def test_returns_none_when_lat_lon_missing(self, mock_http, mock_load_pc):
        """If the Nominatim response lacks lat/lon, return None."""
        mock_http.return_value = [{"display_name": "Somewhere", "address": {}}]
        result = geocode_postal_code("ABCDE")
        self.assertIsNone(result)


class TestGeocodeAddress(unittest.TestCase):
    """Tests for geocode_address() with mocked HTTP calls."""

    @patch("grocery_optimizer.geo_discovery._http_get_json")
    def test_parses_nominatim_address_result(self, mock_http):
        mock_http.return_value = [
            {
                "lat": "40.7128",
                "lon": "-74.0060",
                "display_name": "New York, NY, USA",
                "address": {"country_code": "us"},
            }
        ]

        result = geocode_address("New York, NY")
        self.assertIsNotNone(result)
        self.assertIsInstance(result, GeoPoint)
        self.assertAlmostEqual(result.latitude, 40.7128, places=3)
        self.assertAlmostEqual(result.longitude, -74.0060, places=3)
        self.assertEqual(result.country_code, "us")

    @patch("grocery_optimizer.geo_discovery._http_get_json", return_value=None)
    def test_returns_none_on_http_failure(self, mock_http):
        result = geocode_address("nonexistent place 12345")
        self.assertIsNone(result)

    def test_empty_address_returns_none(self):
        result = geocode_address("")
        self.assertIsNone(result)

    def test_whitespace_address_returns_none(self):
        result = geocode_address("   ")
        self.assertIsNone(result)

    @patch("grocery_optimizer.geo_discovery._http_get_json", return_value=[])
    def test_empty_response_returns_none(self, mock_http):
        result = geocode_address("unknown place")
        self.assertIsNone(result)


class TestDiscoverFoodPlaces(unittest.TestCase):
    """Tests for discover_food_places() with mocked HTTP calls."""

    def setUp(self):
        # Clear in-memory caches between tests so results don't leak.
        from grocery_optimizer.geo_discovery import _discovery_cache, _geocode_cache
        _geocode_cache.clear()
        _discovery_cache.clear()

    @patch("grocery_optimizer.geo_discovery.load_stores", return_value=[])
    @patch("grocery_optimizer.geo_discovery._http_get_json")
    @patch("grocery_optimizer.geo_discovery.load_postal_codes")
    def test_returns_stores_from_overpass(self, mock_load_pc, mock_http, mock_load_stores):
        from grocery_optimizer.stores import PostalCodeInfo

        mock_load_pc.return_value = {
            "H3A1A1": PostalCodeInfo(
                postal_code="H3A1A1",
                latitude=45.5017,
                longitude=-73.5673,
                city="Montreal",
                province_state="QC",
                country="CA",
            )
        }

        # First call: geocode_postal_code will use local data (mocked above).
        # Second call: Overpass API response.
        mock_http.return_value = {
            "elements": [
                {
                    "type": "node",
                    "lat": 45.502,
                    "lon": -73.568,
                    "tags": {
                        "name": "Metro Plus",
                        "shop": "supermarket",
                        "brand": "Metro",
                        "addr:street": "Rue Sherbrooke",
                        "addr:housenumber": "1234",
                        "addr:city": "Montreal",
                    },
                },
                {
                    "type": "node",
                    "lat": 45.503,
                    "lon": -73.570,
                    "tags": {
                        "name": "IGA Extra",
                        "shop": "supermarket",
                        "brand": "IGA",
                    },
                },
            ]
        }

        result = discover_food_places("H3A1A1", radius_km=5.0)

        self.assertIn("stores", result)
        self.assertIn("origin", result)
        self.assertIn("count", result)
        self.assertIsInstance(result["stores"], list)
        self.assertEqual(result["count"], len(result["stores"]))
        self.assertGreater(len(result["stores"]), 0)

        # Verify store structure.
        store = result["stores"][0]
        self.assertIn("store_id", store)
        self.assertIn("name", store)
        self.assertIn("chain", store)
        self.assertIn("distance_km", store)
        self.assertIn("price_tier", store)
        self.assertIn("latitude", store)
        self.assertIn("longitude", store)

        # Verify origin structure.
        origin = result["origin"]
        self.assertEqual(origin["postal_code"], "H3A1A1")
        self.assertAlmostEqual(origin["latitude"], 45.5017, places=3)

    @patch("grocery_optimizer.geo_discovery.load_stores", return_value=[])
    @patch("grocery_optimizer.geo_discovery._http_get_json")
    @patch("grocery_optimizer.geo_discovery.load_postal_codes", return_value={})
    def test_geocode_failure_returns_empty(self, mock_load_pc, mock_http, mock_load_stores):
        """If geocoding fails, discover_food_places returns an empty result."""
        # _http_get_json returns None for Nominatim (geocode fails).
        mock_http.return_value = None

        result = discover_food_places("ZZZZZZ", radius_km=5.0)

        self.assertIsNone(result["origin"])
        self.assertEqual(result["stores"], [])
        self.assertEqual(result["count"], 0)

    @patch("grocery_optimizer.geo_discovery.load_stores", return_value=[])
    @patch("grocery_optimizer.geo_discovery._http_get_json")
    @patch("grocery_optimizer.geo_discovery.load_postal_codes")
    def test_overpass_failure_uses_local_fallback(self, mock_load_pc, mock_http, mock_load_stores):
        """If Overpass API fails, function falls back to local store config."""
        from grocery_optimizer.stores import PostalCodeInfo

        mock_load_pc.return_value = {
            "H3A1A1": PostalCodeInfo(
                postal_code="H3A1A1",
                latitude=45.5017,
                longitude=-73.5673,
                city="Montreal",
                province_state="QC",
                country="CA",
            )
        }
        # Overpass returns None (simulating URLError).
        mock_http.return_value = None

        result = discover_food_places("H3A1A1", radius_km=12.0)

        # Should still return a well-formed result with local fallback.
        self.assertIsNotNone(result["origin"])
        self.assertIn("stores", result)
        self.assertIn("source", result)
        self.assertEqual(result["source"], "local_config_fallback")

        from grocery_optimizer.geo_discovery import _discovery_cache

        self.assertNotIn("H3A1A1|12.0|", _discovery_cache)

    @patch("grocery_optimizer.geo_discovery.load_stores", return_value=[])
    @patch("grocery_optimizer.geo_discovery._http_get_json")
    @patch("grocery_optimizer.geo_discovery.load_postal_codes")
    def test_alternate_overpass_provider_recovers(self, mock_load_pc, mock_http, mock_load_stores):
        from grocery_optimizer.stores import PostalCodeInfo

        mock_load_pc.return_value = {
            "H3A1A1": PostalCodeInfo(
                postal_code="H3A1A1",
                latitude=45.5017,
                longitude=-73.5673,
                city="Montreal",
                province_state="QC",
                country="CA",
            )
        }
        mock_http.side_effect = [
            {"elements": []},
            {
                "elements": [
                    {
                        "type": "node",
                        "lat": 45.502,
                        "lon": -73.568,
                        "tags": {"name": "Recovered Market", "shop": "supermarket"},
                    }
                ]
            },
        ]

        result = discover_food_places("H3A1A1", radius_km=5.0)

        self.assertEqual(result["source"], "osm_overpass")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["stores"][0]["name"], "Recovered Market")
        self.assertEqual(mock_http.call_count, 2)
        self.assertTrue(
            mock_http.call_args_list[1].args[0].startswith(
                "https://overpass.private.coffee/api/interpreter?data="
            )
        )

    @patch("grocery_optimizer.geo_discovery.load_stores", return_value=[])
    @patch("grocery_optimizer.geo_discovery._http_get_json")
    @patch("grocery_optimizer.geo_discovery.load_postal_codes")
    def test_transient_fallback_is_retried(self, mock_load_pc, mock_http, mock_load_stores):
        from grocery_optimizer.stores import PostalCodeInfo

        mock_load_pc.return_value = {
            "H3A1A1": PostalCodeInfo(
                postal_code="H3A1A1",
                latitude=45.5017,
                longitude=-73.5673,
                city="Montreal",
                province_state="QC",
                country="CA",
            )
        }
        mock_http.side_effect = [
            None,
            None,
            {
                "elements": [
                    {
                        "type": "node",
                        "lat": 45.502,
                        "lon": -73.568,
                        "tags": {"name": "Retry Grocer", "shop": "supermarket"},
                    }
                ]
            },
        ]

        first = discover_food_places("H3A1A1", radius_km=5.0)
        second = discover_food_places("H3A1A1", radius_km=5.0)

        self.assertEqual(first["source"], "local_config_fallback")
        self.assertEqual(second["source"], "osm_overpass")
        self.assertEqual(second["stores"][0]["name"], "Retry Grocer")

    @patch("grocery_optimizer.geo_discovery.load_stores", return_value=[])
    @patch("grocery_optimizer.geo_discovery._http_get_json")
    @patch("grocery_optimizer.geo_discovery.load_postal_codes")
    def test_elements_without_name_are_skipped(self, mock_load_pc, mock_http, mock_load_stores):
        from grocery_optimizer.stores import PostalCodeInfo

        mock_load_pc.return_value = {
            "H3A1A1": PostalCodeInfo(
                postal_code="H3A1A1",
                latitude=45.5017,
                longitude=-73.5673,
                city="Montreal",
                province_state="QC",
                country="CA",
            )
        }

        mock_http.return_value = {
            "elements": [
                {
                    "type": "node",
                    "lat": 45.502,
                    "lon": -73.568,
                    "tags": {"shop": "supermarket"},
                    # No "name" tag -- should be skipped.
                },
                {
                    "type": "node",
                    "lat": 45.503,
                    "lon": -73.570,
                    "tags": {"name": "Valid Store", "shop": "supermarket"},
                },
            ]
        }

        result = discover_food_places("H3A1A1", radius_km=5.0)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["stores"][0]["name"], "Valid Store")

    @patch("grocery_optimizer.geo_discovery.load_stores", return_value=[])
    @patch("grocery_optimizer.geo_discovery._http_get_json")
    @patch("grocery_optimizer.geo_discovery.load_postal_codes")
    def test_duplicate_stores_are_deduplicated(self, mock_load_pc, mock_http, mock_load_stores):
        from grocery_optimizer.stores import PostalCodeInfo

        mock_load_pc.return_value = {
            "H3A1A1": PostalCodeInfo(
                postal_code="H3A1A1",
                latitude=45.5017,
                longitude=-73.5673,
                city="Montreal",
                province_state="QC",
                country="CA",
            )
        }

        mock_http.return_value = {
            "elements": [
                {
                    "type": "node",
                    "lat": 45.502,
                    "lon": -73.568,
                    "tags": {"name": "Duplicate Store", "shop": "supermarket"},
                },
                {
                    "type": "way",
                    "center": {"lat": 45.502, "lon": -73.568},
                    "tags": {"name": "Duplicate Store", "shop": "supermarket"},
                },
            ]
        }

        result = discover_food_places("H3A1A1", radius_km=5.0)
        # Same name, same (rounded) coordinates should be deduplicated.
        self.assertEqual(result["count"], 1)


class TestHTTPGetJsonErrorHandling(unittest.TestCase):
    """Test that _http_get_json handles errors gracefully."""

    @patch("grocery_optimizer.geo_discovery.urlopen")
    def test_url_error_returns_none(self, mock_urlopen):
        """URLError should be caught and return None."""
        mock_urlopen.side_effect = URLError("Connection refused")

        from grocery_optimizer.geo_discovery import _http_get_json
        result = _http_get_json("http://example.com/test")
        self.assertIsNone(result)

    @patch("grocery_optimizer.geo_discovery.urlopen")
    def test_timeout_returns_none(self, mock_urlopen):
        """TimeoutError should be caught and return None."""
        mock_urlopen.side_effect = TimeoutError("Request timed out")

        from grocery_optimizer.geo_discovery import _http_get_json
        result = _http_get_json("http://example.com/test")
        self.assertIsNone(result)

    @patch("grocery_optimizer.geo_discovery.urlopen")
    def test_invalid_json_returns_none(self, mock_urlopen):
        """Invalid JSON response should be caught and return None."""
        resp = MagicMock()
        resp.read.return_value = b"not valid json {{"
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        from grocery_optimizer.geo_discovery import _http_get_json
        result = _http_get_json("http://example.com/test")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
