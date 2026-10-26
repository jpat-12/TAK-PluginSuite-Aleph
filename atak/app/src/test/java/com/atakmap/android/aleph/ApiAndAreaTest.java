package com.atakmap.android.aleph;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import com.atakmap.android.aleph.api.AlephConfig;
import com.atakmap.android.aleph.api.Models;
import com.atakmap.android.aleph.area.AreaMath;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;

/** JSON parsing at the API boundary, URL validation, and area geometry. */
public class ApiAndAreaTest {

    @Test
    public void jobParsingMatchesServiceShape() throws Exception {
        JSONObject job = new JSONObject("{\"id\":\"j0123456789ab\",\"name\":\"Sector 3\",\"state\":\"running\","
                + "\"area_km2\":1.88,\"layers\":[\"imagery\",\"osm\"],\"percent\":40,\"warnings\":[],\"error\":null,"
                + "\"progress\":{\"imagery\":{\"state\":\"running\",\"phase\":\"Downloading imagery\",\"done\":12,\"total\":49},"
                + "\"osm\":{\"state\":\"failed\",\"error\":\"Geofabrik down\",\"phase\":null,\"done\":0,\"total\":null}},"
                + "\"package\":null,\"some_future_field\":{}}");
        Models.Job parsed = Models.Job.parse(job);
        assertEquals("Downloading imagery 12/49", parsed.phase);
        assertEquals("osm: Geofabrik down", parsed.layerErrors.get(0));
        assertNull(parsed.error);
        assertTrue(parsed.isActive());
        assertFalse(parsed.isComplete());
        assertTrue(parsed.canRetry());
    }

    @Test
    public void completeJobExposesPackage() throws Exception {
        JSONObject wrapper = new JSONObject().put("jobs", new JSONArray().put(new JSONObject(
                "{\"id\":\"j1\",\"state\":\"complete\",\"progress\":{},\"package\":{\"filename\":\"a.zip\","
                        + "\"bytes\":1261776,\"sha256\":\"b55f\"}}")));
        Models.Job job = Models.Job.parseList(wrapper).get(0);
        assertTrue(job.isComplete());
        assertEquals(1261776L, job.packageBytes);
        assertEquals("a.zip", job.packageFile);
    }

    @Test
    public void infoChecksApiMajor() throws Exception {
        Models.ServerInfo info = Models.ServerInfo.parse(new JSONObject(
                "{\"version\":\"0.1.0\",\"api\":1,\"layers\":[\"imagery\",\"elevation\"],\"max_area_km2\":25,"
                        + "\"imagery\":{\"name\":\"USGS NAIP\",\"max_zoom\":18}}"));
        assertTrue(info.compatible());
        assertEquals(18, info.imageryMaxZoom);
        assertFalse(Models.ServerInfo.parse(new JSONObject("{\"api\":2}")).compatible());
    }

    @Test
    public void serverUrlMustBeAPlainHttpsOrigin() {
        assertEquals("https://aleph.prod.ilwg.us", AlephConfig.normalizeUrl(" https://aleph.prod.ilwg.us/ "));
        assertEquals("https://10.0.0.5:8443", AlephConfig.normalizeUrl("https://10.0.0.5:8443"));
        for (String bad : new String[] {"http://aleph.example.org", "https://user:pw@aleph.example.org",
                "https://aleph.example.org/?x=1", "ftp://x"}) {
            try {
                AlephConfig.normalizeUrl(bad);
                fail("accepted " + bad);
            } catch (IllegalArgumentException expected) {
                // rejected, as it should be
            }
        }
    }

    @Test
    public void areaMatchesServiceWithinOnePercent() {
        // The service measures this test area as 1.883 km² (live Lake Springfield capture).
        double[][] ring = AreaMath.bbox(-89.6200, 39.7000, -89.6035, 39.7120);
        assertEquals(1.883, AreaMath.areaKm2(ring), 0.02);
    }

    @Test
    public void geoJsonRingIsClosedOnceWithDuplicatesDropped() throws Exception {
        double[][] ring = {{0, 0}, {1, 0}, {1, 0}, {1, 1}, {0, 1}, {0, 0}};
        JSONArray coordinates = AreaMath.toGeoJson(ring).getJSONArray("coordinates").getJSONArray(0);
        assertEquals(5, coordinates.length());
        assertEquals(coordinates.getJSONArray(0).toString(), coordinates.getJSONArray(4).toString());
    }
}
