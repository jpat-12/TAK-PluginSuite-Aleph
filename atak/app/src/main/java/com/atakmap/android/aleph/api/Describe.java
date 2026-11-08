package com.atakmap.android.aleph.api;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

/**
 * The words and numbers the panel shows about a capture before it's made: what each layer
 * downloads, the imagery zoom choices a source allows, and sizes. Pure Java (no Android), so
 * it's unit-tested; the same wording as the CloudTAK panel and WinTAK's Core/Describe.cs.
 */
public final class Describe {

    private Describe() {
    }

    /** One line saying what ticking a layer actually downloads and how ATAK uses it. */
    public static String layer(String layer, int dtedLevel) {
        switch (layer) {
            case "imagery":
                return "Photo imagery of the area as MBTiles (shows in Overlay Manager). Pick the source below.";
            case "elevation":
                return String.format(Locale.US, "AWS Terrain Tiles (USGS 3DEP in the US, SRTM elsewhere) → DTED level %d "
                        + "cells (~%d m posts) + a GeoTIFF; merged into ATAK's elevation data, filling gaps only.",
                        dtedLevel, dtedLevel == 2 ? 30 : 90);
            case "osm":
                return "OpenStreetMap via Geofabrik: roads, trails, railways, power lines, waterways, lakes, buildings "
                        + "and airfields → KMZ.";
            case "photos":
                return "Mapillary street-level photos taken inside the area (CC BY-SA) → map markers with each photo attached.";
            default:
                return "";
        }
    }

    /** Up to five imagery zooms ending at the source's limit, never below z12 (the API's minimum). */
    public static List<Integer> zoomChoices(int maxZoom) {
        List<Integer> zooms = new ArrayList<>();
        for (int z = Math.max(12, maxZoom - 4); z <= maxZoom; z++) zooms.add(z);
        return Collections.unmodifiableList(zooms);
    }

    /** "z17 (~0.9 m)": ground resolution at the area's latitude. */
    public static String zoomLabel(int zoom, double latitude) {
        double metres = 156543.03 * Math.cos(Math.toRadians(latitude)) / Math.pow(2, zoom);
        return String.format(Locale.US, "Imagery detail z%d (~%s m)", zoom,
                metres < 10 ? String.format(Locale.US, "%.1f", metres) : String.format(Locale.US, "%.0f", metres));
    }

    /** The zoom to keep when the source changes: the same one if allowed, else the finest the source has. */
    public static int keepZoom(int current, List<Integer> choices) {
        if (choices.isEmpty() || choices.contains(current)) return current;
        return choices.get(choices.size() - 1);
    }

    /** "≈ 6.1 MB" */
    public static String size(long bytes) {
        return bytes >= 1e9 ? String.format(Locale.US, "≈ %.1f GB", bytes / 1e9)
                : String.format(Locale.US, "≈ %.1f MB", Math.max(0.1, bytes / 1e6));
    }
}
