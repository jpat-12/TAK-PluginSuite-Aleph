package com.atakmap.android.aleph.api;

import android.content.SharedPreferences;

import java.net.URI;
import java.util.Locale;

/**
 * Connection settings, persisted in the plugin's own prefs file (inside ATAK's private data
 * dir, so other apps can't read the token). The token is never logged.
 */
public final class AlephConfig {

    private static final String KEY_URL = "server_url";
    private static final String KEY_TOKEN = "token";
    private static final String KEY_WIFI_ONLY = "wifi_only";

    private final SharedPreferences prefs;

    public AlephConfig(SharedPreferences prefs) {
        this.prefs = prefs;
    }

    public String serverUrl() {
        return prefs.getString(KEY_URL, "");
    }

    public String token() {
        return prefs.getString(KEY_TOKEN, "");
    }

    /** Default on: a 100 MB package over field LTE can eat a team's data plan. */
    public boolean wifiOnly() {
        return prefs.getBoolean(KEY_WIFI_ONLY, true);
    }

    public boolean isConfigured() {
        return !serverUrl().isEmpty() && !token().isEmpty();
    }

    public void save(String url, String token) {
        prefs.edit().putString(KEY_URL, normalizeUrl(url)).putString(KEY_TOKEN, token.trim()).apply();
    }

    public void setWifiOnly(boolean wifiOnly) {
        prefs.edit().putBoolean(KEY_WIFI_ONLY, wifiOnly).apply();
    }

    /**
     * HTTPS only, no credentials or paths smuggled in — the token goes to whatever host this
     * names, so it must be a plain origin (CLAUDE.md §12: validate before use).
     */
    public static String normalizeUrl(String raw) {
        String url = raw == null ? "" : raw.trim();
        while (url.endsWith("/")) url = url.substring(0, url.length() - 1);
        if (url.isEmpty()) return "";
        URI uri;
        try {
            uri = URI.create(url);
        } catch (IllegalArgumentException e) {
            throw new IllegalArgumentException("Not a valid URL: " + raw);
        }
        if (!"https".equals(String.valueOf(uri.getScheme()).toLowerCase(Locale.US))) {
            throw new IllegalArgumentException("Server URL must start with https://");
        }
        if (uri.getHost() == null || uri.getUserInfo() != null || uri.getQuery() != null || uri.getFragment() != null) {
            throw new IllegalArgumentException("Use just the server address, e.g. https://aleph.example.org");
        }
        String path = uri.getPath() == null ? "" : uri.getPath();
        return "https://" + uri.getHost() + (uri.getPort() > 0 ? ":" + uri.getPort() : "") + path;
    }
}
