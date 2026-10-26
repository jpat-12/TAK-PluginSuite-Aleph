package com.atakmap.android.aleph.api;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;

/**
 * Blocking calls to the Aleph capture service's /api/v1 (docs/API.md). Never call on the UI
 * thread — AlephMapComponent owns the single worker executor these run on.
 */
public final class AlephClient {

    private static final int CONNECT_TIMEOUT_MS = 15_000;
    private static final int READ_TIMEOUT_MS = 30_000;

    /** An HTTP error from the service, carrying its {"error": "..."} message for the operator. */
    public static final class AlephException extends IOException {
        public final int status;

        AlephException(int status, String message) {
            super(message);
            this.status = status;
        }
    }

    private final AlephConfig config;

    public AlephClient(AlephConfig config) {
        this.config = config;
    }

    public Models.ServerInfo info() throws IOException {
        return Models.ServerInfo.parse(request("GET", "/info", null, false));
    }

    public Models.Estimate estimate(JSONObject capture) throws IOException {
        return Models.Estimate.parse(request("POST", "/estimate", capture, true));
    }

    public Models.Job create(JSONObject capture) throws IOException {
        return Models.Job.parse(request("POST", "/jobs", capture, true));
    }

    public List<Models.Job> jobs() throws IOException {
        return Models.Job.parseList(request("GET", "/jobs", null, true));
    }

    public void delete(String jobId) throws IOException {
        request("DELETE", "/jobs/" + jobId, null, true);
    }

    public Models.Job retry(String jobId) throws IOException {
        return Models.Job.parse(request("POST", "/jobs/" + jobId + "/retry", null, true));
    }

    public JSONObject point(double lat, double lon) throws IOException {
        return request("GET", String.format(Locale.US, "/point?lat=%.6f&lon=%.6f", lat, lon), null, true);
    }

    /** Package downloads stream through PackageDownloader; it needs the same URL + auth. */
    public HttpURLConnection openPackage(String jobId) throws IOException {
        HttpURLConnection connection = open("GET", "/jobs/" + jobId + "/package", true);
        connection.setReadTimeout(60_000);
        return connection;
    }

    private HttpURLConnection open(String method, String path, boolean auth) throws IOException {
        if (config.serverUrl().isEmpty()) throw new AlephException(0, "Set the Aleph server URL first.");
        HttpURLConnection connection = (HttpURLConnection) new URL(config.serverUrl() + "/api/v1" + path).openConnection();
        connection.setRequestMethod(method);
        connection.setConnectTimeout(CONNECT_TIMEOUT_MS);
        connection.setReadTimeout(READ_TIMEOUT_MS);
        connection.setRequestProperty("Accept", "application/json");
        connection.setInstanceFollowRedirects(false);  // never forward the token to another host
        if (auth) connection.setRequestProperty("Authorization", "Bearer " + config.token());
        return connection;
    }

    private JSONObject request(String method, String path, JSONObject body, boolean auth) throws IOException {
        HttpURLConnection connection = open(method, path, auth);
        try {
            if (body != null) {
                byte[] bytes = body.toString().getBytes(StandardCharsets.UTF_8);
                connection.setDoOutput(true);
                connection.setRequestProperty("Content-Type", "application/json");
                connection.setFixedLengthStreamingMode(bytes.length);
                try (OutputStream out = connection.getOutputStream()) {
                    out.write(bytes);
                }
            }
            int status = connection.getResponseCode();
            String text = read(status >= 400 ? connection.getErrorStream() : connection.getInputStream());
            JSONObject json;
            try {
                json = text.isEmpty() ? new JSONObject() : new JSONObject(text);
            } catch (JSONException e) {
                throw new AlephException(status, "Unexpected response from " + config.serverUrl() + " (HTTP " + status + ")");
            }
            if (status >= 300) {
                String message = json.optString("error", "");
                if (status == 401) message = "The server rejected the token — check it in Settings. " + message;
                throw new AlephException(status, message.isEmpty() ? "HTTP " + status : message);
            }
            return json;
        } finally {
            connection.disconnect();
        }
    }

    private static String read(InputStream in) throws IOException {
        if (in == null) return "";
        try (InputStream stream = in) {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buffer = new byte[8192];
            int n;
            while ((n = stream.read(buffer)) > 0) out.write(buffer, 0, n);
            return out.toString("UTF-8");
        }
    }
}
