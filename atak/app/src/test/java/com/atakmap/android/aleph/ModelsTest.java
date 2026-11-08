package com.atakmap.android.aleph;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import com.atakmap.android.aleph.api.Describe;
import com.atakmap.android.aleph.api.Models;

import org.json.JSONObject;
import org.junit.Test;

import java.util.Arrays;

/** Imagery sources, per-layer sizes, missing tiles and the point summary (service 0.1.4 fields). */
public class ModelsTest {

    private static final String INFO = "{\"version\":\"0.1.4\",\"api\":1,\"layers\":[\"imagery\",\"elevation\"],"
            + "\"dted_level\":1,\"imagery\":{\"name\":\"USGS NAIP aerial\",\"max_zoom\":18},\"imagery_sources\":["
            + "{\"id\":\"usgs-naip\",\"default\":true,\"name\":\"USGS NAIP aerial\",\"max_zoom\":18,\"resolution\":\"0.6–1 m\","
            + "\"coverage\":\"Contiguous United States\",\"updated\":\"Flown every 2–3 years\",\"licence\":\"Public domain\","
            + "\"description\":\"Aerial photos.\"},"
            + "{\"id\":\"eox-s2cloudless-2016\",\"default\":false,\"name\":\"Sentinel-2 cloudless 2016 (EOX)\",\"max_zoom\":14,"
            + "\"resolution\":\"10 m\",\"coverage\":\"Worldwide\",\"updated\":\"2016 mosaic\",\"licence\":\"CC BY 4.0\","
            + "\"description\":\"Cloud-free mosaic.\"}]}";

    @Test
    public void imagerySourcesAreParsedWithTheDefault() throws Exception {
        Models.ServerInfo info = Models.ServerInfo.parse(new JSONObject(INFO));
        assertEquals(2, info.imagerySources.size());
        assertEquals("usgs-naip", info.defaultSource().id);
        assertEquals(1, info.dtedLevel);
        Models.ImagerySource eox = info.imagerySources.get(1);
        assertEquals(14, eox.maxZoom);
        assertEquals("Sentinel-2 cloudless 2016 (EOX) · 10 m", eox.label());
        assertEquals("Cloud-free mosaic.\nWorldwide · 2016 mosaic · CC BY 4.0", eox.details());
    }

    @Test
    public void olderServicesListNoSources() throws Exception {
        Models.ServerInfo info = Models.ServerInfo.parse(new JSONObject("{\"api\":1,\"imagery\":{\"max_zoom\":18}}"));
        assertTrue(info.imagerySources.isEmpty());
        assertNull(info.defaultSource());
        assertEquals(2, info.dtedLevel);
    }

    @Test
    public void zoomChoicesFollowTheSourceLimit() {
        assertEquals(Arrays.asList(14, 15, 16, 17, 18), Describe.zoomChoices(18));
        assertEquals(Arrays.asList(12, 13, 14), Describe.zoomChoices(14));
        assertEquals(14, Describe.keepZoom(17, Describe.zoomChoices(14)));   // NAIP z17 → EOX tops out at z14
        assertEquals(16, Describe.keepZoom(16, Describe.zoomChoices(18)));
        assertEquals("Imagery detail z17 (~0.9 m)", Describe.zoomLabel(17, 40));
        assertEquals("Imagery detail z12 (~29 m)", Describe.zoomLabel(12, 40));
    }

    @Test
    public void layerDescriptionsSayWhatIsDownloaded() {
        assertTrue(Describe.layer("elevation", 2).contains("DTED level 2 cells (~30 m posts)"));
        assertTrue(Describe.layer("elevation", 1).contains("(~90 m posts)"));
        assertTrue(Describe.layer("osm", 2).contains("KMZ"));
        assertEquals("", Describe.layer("future-layer", 2));
        assertEquals("≈ 6.1 MB", Describe.size(6_100_000));
        assertEquals("≈ 0.1 MB", Describe.size(1_000));
    }

    @Test
    public void estimateCarriesPerLayerBytes() throws Exception {
        Models.Estimate estimate = Models.Estimate.parse(new JSONObject("{\"bytes\":9000000,\"allowed\":true,"
                + "\"layers\":{\"imagery\":{\"bytes\":6100000,\"source\":\"USGS NAIP aerial\"},\"elevation\":{\"bytes\":2900000}}}"));
        assertEquals(Long.valueOf(6_100_000), estimate.layerBytes.get("imagery"));
        assertEquals(Long.valueOf(2_900_000), estimate.layerBytes.get("elevation"));
        assertNull(estimate.layerBytes.get("osm"));
    }

    @Test
    public void completeJobWithFailedTilesOffersTheirRetry() throws Exception {
        Models.Job job = Models.Job.parse(new JSONObject("{\"id\":\"j1\",\"state\":\"complete\",\"package\":{\"filename\":\"a.zip\"},"
                + "\"progress\":{\"imagery\":{\"state\":\"complete\",\"stats\":{\"failed_tiles\":3,\"source\":\"USGS NAIP aerial\"}}}}"));
        assertEquals(3, job.failedTiles);
        assertEquals("USGS NAIP aerial", job.imagerySource);
        assertTrue(job.hasMissingTiles());
        assertFalse(job.canRetry());
        Models.Job old = Models.Job.parse(new JSONObject("{\"id\":\"j2\",\"state\":\"complete\",\"progress\":{\"imagery\":{\"state\":\"complete\"}}}"));
        assertEquals(0, old.failedTiles);
        assertFalse(old.hasMissingTiles());
    }

    @Test
    public void pointSummaryLeadsWithTheStreetAddress() throws Exception {
        Models.Point point = Models.Point.parse(new JSONObject("{\"lat\":39.79841,\"lon\":-89.64401,\"elevation_m\":181.2,"
                + "\"street_address\":{\"label\":\"413 North 5th Street, Springfield, Illinois 62702\",\"exact\":true,\"distance_m\":12.4},"
                + "\"address\":{\"label\":\"Lincoln Park, Springfield\"},\"photos\":null}"), 0, 0);
        assertEquals("39.79841, -89.64401\nElevation 181 m (594 ft)\n413 North 5th Street, Springfield, Illinois 62702 · 12 m away"
                + "\nNear Lincoln Park, Springfield", point.describe());
        Models.Point street = Models.Point.parse(new JSONObject("{\"elevation_m\":null,\"street_address\":{\"label\":\"County Road 12, Chatham\","
                + "\"exact\":false,\"distance_m\":null},\"address\":null,\"photos\":[]}"), 39.7, -89.6);
        assertEquals("39.70000, -89.60000\nCounty Road 12, Chatham (street only)\n0 street-level photo(s) within 150 m", street.describe());
    }
}
