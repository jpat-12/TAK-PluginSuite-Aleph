package com.atakmap.android.aleph.area;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

/**
 * Capture-area geometry with no ATAK dependencies (unit-tested on the JVM). Rings are
 * {@code double[n][2]} of {lon, lat} — GeoJSON order, which is what the Aleph API takes.
 */
public final class AreaMath {

    private static final double EARTH_RADIUS_M = 6_371_008.8;

    private AreaMath() {
    }

    public static double[][] bbox(double west, double south, double east, double north) {
        return new double[][] {{west, south}, {east, south}, {east, north}, {west, north}};
    }

    /** Approximate ground area on a local equirectangular plane; same formula as the CloudTAK panel. */
    public static double areaKm2(double[][] ring) {
        int n = ring.length;
        if (n < 3) return 0;
        double meanLat = 0;
        for (double[] p : ring) meanLat += p[1];
        double cos = Math.cos(Math.toRadians(meanLat / n));
        double twice = 0;
        for (int i = 0; i < n; i++) {
            double[] a = ring[i];
            double[] b = ring[(i + 1) % n];
            twice += a[0] * cos * b[1] - b[0] * cos * a[1];
        }
        double degree = Math.toRadians(1) * EARTH_RADIUS_M;
        return Math.abs(twice) / 2 * degree * degree / 1e6;
    }

    /** Drop a repeated closing vertex and consecutive duplicates (shapes often include both). */
    public static double[][] normalize(double[][] ring) {
        java.util.List<double[]> out = new java.util.ArrayList<>();
        for (double[] p : ring) {
            if (out.isEmpty() || !same(out.get(out.size() - 1), p)) out.add(p);
        }
        if (out.size() > 1 && same(out.get(0), out.get(out.size() - 1))) out.remove(out.size() - 1);
        return out.toArray(new double[0][]);
    }

    private static boolean same(double[] a, double[] b) {
        return Math.abs(a[0] - b[0]) < 1e-9 && Math.abs(a[1] - b[1]) < 1e-9;
    }

    /** GeoJSON Polygon with a closed ring. */
    public static JSONObject toGeoJson(double[][] ring) throws JSONException {
        double[][] open = normalize(ring);
        JSONArray coordinates = new JSONArray();
        for (int i = 0; i <= open.length; i++) {
            double[] p = open[i % open.length];
            coordinates.put(new JSONArray().put(p[0]).put(p[1]));
        }
        return new JSONObject().put("type", "Polygon").put("coordinates", new JSONArray().put(coordinates));
    }
}
