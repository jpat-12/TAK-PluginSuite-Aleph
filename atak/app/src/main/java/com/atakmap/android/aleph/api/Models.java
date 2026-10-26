package com.atakmap.android.aleph.api;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;

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
        }

        public static ServerInfo parse(JSONObject o) {
            return new ServerInfo(o);
        }

        public boolean compatible() {
            return api == SUPPORTED_API;
        }
    }

    public static final class Estimate {
        public final double areaKm2;
        public final long bytes;
        public final long seconds;
        public final boolean allowed;
        public final double maxAreaKm2;

        Estimate(JSONObject o) {
            areaKm2 = o.optDouble("area_km2", 0);
            bytes = o.optLong("bytes", 0);
            seconds = o.optLong("seconds", 0);
            allowed = o.optBoolean("allowed", false);
            maxAreaKm2 = o.optDouble("max_area_km2", 0);
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
    }

    static List<String> strings(JSONArray array) {
        List<String> out = new ArrayList<>();
        for (int i = 0; array != null && i < array.length(); i++) out.add(array.optString(i));
        return Collections.unmodifiableList(out);
    }
}
