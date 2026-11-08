package com.atakmap.android.aleph.api;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Typed views of the Aleph API's JSON (docs/API.md), parsed once at the boundary. Optional
 * fields default instead of throwing, so a newer server adding fields can't break an older
 * plugin; the API major version is what guards incompatible changes.
 */
public final class Models {

    /** Highest Aleph API major this plugin speaks. */
    public static final int SUPPORTED_API = 1;

    private Models() {
    }

    public static final class ServerInfo {
        public final String version;
        public final int api;
        public final List<String> layers;
        public final double maxAreaKm2;
        public final String imageryName;
        public final int imageryMaxZoom;
        public final int defaultZoom;
        public final int ttlHours;
        public final int dtedLevel;
        /** Imagery a capture may pick (service 0.1.4+); empty on older services, which use their default. */
        public final List<ImagerySource> imagerySources;

        ServerInfo(JSONObject o) {
            version = o.optString("version", "?");
            api = o.optInt("api", 0);
            layers = strings(o.optJSONArray("layers"));
            maxAreaKm2 = o.optDouble("max_area_km2", 0);
            JSONObject imagery = o.optJSONObject("imagery");
            imageryName = imagery == null ? null : imagery.optString("name", null);
            imageryMaxZoom = imagery == null ? 18 : imagery.optInt("max_zoom", 18);
            defaultZoom = o.optInt("default_imagery_zoom", 17);
            ttlHours = o.optInt("job_ttl_hours", 72);
            dtedLevel = o.optInt("dted_level", 2);
            List<ImagerySource> sources = new ArrayList<>();
            JSONArray array = o.optJSONArray("imagery_sources");
            for (int i = 0; array != null && i < array.length(); i++) {
                JSONObject item = array.optJSONObject(i);
                if (item != null && !item.optString("id").isEmpty()) sources.add(new ImagerySource(item));
            }
            imagerySources = Collections.unmodifiableList(sources);
        }

        public static ServerInfo parse(JSONObject o) {
            return new ServerInfo(o);
        }

        /** The server's default source, or null when it doesn't list sources. */
        public ImagerySource defaultSource() {
            for (ImagerySource source : imagerySources) if (source.isDefault) return source;
            return imagerySources.isEmpty() ? null : imagerySources.get(0);
        }

        public boolean compatible() {
            return api == SUPPORTED_API;
        }
    }

    /** One choosable imagery source (docs/API.md, info.imagery_sources). */
    public static final class ImagerySource {
        public final String id;
        public final String name;
        public final String description;
        public final String resolution;
        public final String coverage;
        public final String updated;
        public final String licence;
        public final int maxZoom;
        public final boolean isDefault;

        ImagerySource(JSONObject o) {
            id = o.optString("id");
            name = o.optString("name", id);
            description = o.optString("description", "");
            resolution = o.optString("resolution", "");
            coverage = o.optString("coverage", "");
            updated = o.optString("updated", "");
            licence = o.optString("licence", "");
            maxZoom = o.optInt("max_zoom", 18);
            isDefault = o.optBoolean("default", false);
        }

        /** "USGS NAIP aerial · 0.6–1 m" — the picker's label. */
        public String label() {
            return resolution.isEmpty() ? name : name + " · " + resolution;
        }

        /** Description plus "coverage · updated · licence", for the line under the picker. */
        public String details() {
            StringBuilder facts = new StringBuilder();
            for (String part : new String[]{coverage, updated, licence}) {
                if (part.isEmpty()) continue;
                if (facts.length() > 0) facts.append(" · ");
                facts.append(part);
            }
            if (description.isEmpty()) return facts.toString();
            return facts.length() == 0 ? description : description + "\n" + facts;
        }
    }

    public static final class Estimate {
        public final double areaKm2;
        public final long bytes;
        public final long seconds;
        public final boolean allowed;
        public final double maxAreaKm2;
        /** Estimated bytes per layer, for the size shown next to each layer. */
        public final Map<String, Long> layerBytes;

        Estimate(JSONObject o) {
            areaKm2 = o.optDouble("area_km2", 0);
            bytes = o.optLong("bytes", 0);
            seconds = o.optLong("seconds", 0);
            allowed = o.optBoolean("allowed", false);
            maxAreaKm2 = o.optDouble("max_area_km2", 0);
            Map<String, Long> sizes = new HashMap<>();
            JSONObject layers = o.optJSONObject("layers");
            if (layers != null) {
                for (Iterator<String> keys = layers.keys(); keys.hasNext(); ) {
                    String layer = keys.next();
                    JSONObject item = layers.optJSONObject(layer);
                    if (item != null) sizes.put(layer, item.optLong("bytes", 0));
                }
            }
            layerBytes = Collections.unmodifiableMap(sizes);
        }

        public static Estimate parse(JSONObject o) {
            return new Estimate(o);
        }
    }

    public static final class Job {
        public final String id;
        public final String name;
        public final String state;
        public final double areaKm2;
        public final List<String> layers;
        public final double percent;
        public final String phase;
        public final List<String> warnings;
        public final List<String> layerErrors;
        public final String error;
        public final String packageFile;
        public final long packageBytes;
        public final String packageSha256;
        public final String expiresAt;
        /** Imagery tiles still missing after the service's automatic retry (service 0.1.4+). */
        public final int failedTiles;
        /** The imagery source this capture used, when the service reports it. */
        public final String imagerySource;

        Job(JSONObject o) {
            id = o.optString("id");
            name = o.optString("name", id);
            state = o.optString("state", "queued");
            areaKm2 = o.optDouble("area_km2", 0);
            layers = strings(o.optJSONArray("layers"));
            percent = o.optDouble("percent", 0);
            warnings = strings(o.optJSONArray("warnings"));
            error = o.isNull("error") ? null : o.optString("error", null);
            expiresAt = o.optString("expires_at", "");
            String running = null;
            List<String> errors = new ArrayList<>();
            JSONObject progress = o.optJSONObject("progress");
            JSONObject imagery = progress == null ? null : progress.optJSONObject("imagery");
            JSONObject stats = imagery == null ? null : imagery.optJSONObject("stats");
            failedTiles = stats == null ? 0 : stats.optInt("failed_tiles", 0);
            imagerySource = stats == null || stats.isNull("source") ? null : stats.optString("source", null);
            if (progress != null) {
                for (Iterator<String> keys = progress.keys(); keys.hasNext(); ) {
                    String layer = keys.next();
                    JSONObject p = progress.optJSONObject(layer);
                    if (p == null) continue;
                    if ("running".equals(p.optString("state"))) {
                        String label = p.isNull("phase") ? layer : p.optString("phase", layer);
                        running = p.isNull("total") ? label : label + " " + p.optInt("done") + "/" + p.optInt("total");
                    } else if ("failed".equals(p.optString("state"))) {
                        errors.add(layer + ": " + p.optString("error", "failed"));
                    }
                }
            }
            phase = running;
            layerErrors = Collections.unmodifiableList(errors);
            JSONObject pkg = o.optJSONObject("package");
            packageFile = pkg == null ? null : pkg.optString("filename", null);
            packageBytes = pkg == null ? 0 : pkg.optLong("bytes", 0);
            packageSha256 = pkg == null ? null : pkg.optString("sha256", null);
        }

        public static Job parse(JSONObject o) {
            return new Job(o);
        }

        public static List<Job> parseList(JSONObject o) {
            List<Job> jobs = new ArrayList<>();
            JSONArray array = o.optJSONArray("jobs");
            for (int i = 0; array != null && i < array.length(); i++) {
                JSONObject item = array.optJSONObject(i);
                if (item != null) jobs.add(new Job(item));
            }
            return jobs;
        }

        public boolean isActive() {
            return "queued".equals(state) || "running".equals(state);
        }

        public boolean isComplete() {
            return "complete".equals(state) && packageFile != null;
        }

        public boolean canRetry() {
            return "failed".equals(state) || "cancelled".equals(state) || !layerErrors.isEmpty();
        }

        /** Complete, but some imagery tiles never downloaded: offer "Retry N missing tiles". */
        public boolean hasMissingTiles() {
            return "complete".equals(state) && failedTiles > 0 && !canRetry();
        }
    }

    /** GET /point (docs/API.md), with the text the panel shows. */
    public static final class Point {
        public final double lat;
        public final double lon;
        public final Double elevationM;
        public final String streetAddress;
        public final boolean streetAddressExact;
        public final Double streetAddressDistanceM;
        public final String nearestPlace;
        public final int photoCount;

        Point(JSONObject o, double lat, double lon) {
            this.lat = o.optDouble("lat", lat);
            this.lon = o.optDouble("lon", lon);
            elevationM = o.isNull("elevation_m") || !o.has("elevation_m") ? null : o.optDouble("elevation_m");
            JSONObject street = o.optJSONObject("street_address");
            streetAddress = street == null ? null : street.optString("label", null);
            streetAddressExact = street != null && street.optBoolean("exact", false);
            streetAddressDistanceM = street == null || street.isNull("distance_m") || !street.has("distance_m")
                    ? null : street.optDouble("distance_m");
            JSONObject address = o.optJSONObject("address");
            nearestPlace = address == null ? null : address.optString("label", null);
            JSONArray photos = o.optJSONArray("photos");
            photoCount = photos == null ? -1 : photos.length();
        }

        public static Point parse(JSONObject o, double lat, double lon) {
            return new Point(o, lat, lon);
        }

        /** Multi-line summary: coordinates, elevation, street address, nearest place, photos. */
        public String describe() {
            StringBuilder text = new StringBuilder(String.format(Locale.US, "%.5f, %.5f", lat, lon));
            if (elevationM != null) {
                text.append(String.format(Locale.US, "\nElevation %.0f m (%.0f ft)", elevationM, elevationM * 3.28084));
            }
            if (streetAddress != null && !streetAddress.isEmpty()) {
                text.append("\n").append(streetAddress);
                if (!streetAddressExact) text.append(" (street only)");
                if (streetAddressDistanceM != null) {
                    text.append(String.format(Locale.US, " · %.0f m away", streetAddressDistanceM));
                }
            }
            if (nearestPlace != null && !nearestPlace.isEmpty()) text.append("\nNear ").append(nearestPlace);
            if (photoCount >= 0) text.append("\n").append(photoCount).append(" street-level photo(s) within 150 m");
            return text.toString();
        }
    }

    static List<String> strings(JSONArray array) {
        List<String> out = new ArrayList<>();
        for (int i = 0; array != null && i < array.length(); i++) out.add(array.optString(i));
        return Collections.unmodifiableList(out);
    }
}
