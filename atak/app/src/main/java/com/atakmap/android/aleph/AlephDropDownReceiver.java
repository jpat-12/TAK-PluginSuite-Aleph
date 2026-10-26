package com.atakmap.android.aleph;

import android.content.Context;
import android.content.Intent;
import android.graphics.Typeface;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.util.Log;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import com.atakmap.android.aleph.api.AlephClient;
import com.atakmap.android.aleph.api.AlephConfig;
import com.atakmap.android.aleph.api.Models;
import com.atakmap.android.aleph.area.AreaMath;
import com.atakmap.android.aleph.area.AreaPicker;
import com.atakmap.android.aleph.download.DtedInstaller;
import com.atakmap.android.aleph.download.PackageDownloader;
import com.atakmap.android.aleph.download.PackageImporter;
import com.atakmap.android.aleph.plugin.R;
import com.atakmap.android.dropdown.DropDown;
import com.atakmap.android.dropdown.DropDownReceiver;
import com.atakmap.android.maps.MapView;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * The Aleph panel: settings → area → layers → estimate → capture → download & import, plus
 * point lookup. UI only — HTTP lives in {@link AlephClient}, downloads/imports in
 * {@code download/}, map taps in {@link AreaPicker}. Everything slow runs on the component's
 * single worker thread; results come back to the UI thread through {@link #ui}.
 */
public class AlephDropDownReceiver extends DropDownReceiver implements DropDown.OnStateListener {

    public static final String SHOW_PLUGIN = "com.atakmap.android.aleph.SHOW_PLUGIN";
    private static final String TAG = "AlephTAK";
    private static final long POLL_MS = 4000;
    private static final String[] LAYER_LABELS = {
            "imagery", "Imagery (MBTiles)", "elevation", "Elevation (DTED)",
            "osm", "Roads, trails, buildings (KMZ)", "photos", "Street-level photos",
    };

    private final Context plugin;
    private final AlephConfig config;
    private final AlephClient client;
    private final ExecutorService worker;
    private final AreaPicker picker;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final AtomicBoolean cancelDownload = new AtomicBoolean();

    private View root;
    private TextView status;
    private EditText urlField;
    private EditText tokenField;
    private TextView areaLabel;
    private LinearLayout layersBox;
    private Spinner zoomSpinner;
    private EditText nameField;
    private TextView estimateLabel;
    private Button captureButton;
    private LinearLayout jobsBox;
    private TextView pointLabel;
    private CheckBox wifiOnly;

    private Models.ServerInfo info;
    private double[][] area;
    private final List<CheckBox> layerBoxes = new ArrayList<>();
    private final List<Integer> zoomChoices = new ArrayList<>();
    private List<Models.Job> jobs = new ArrayList<>();
    private volatile boolean downloading;  // set on the UI thread, cleared on the worker

    private final Runnable poll = new Runnable() {
        @Override
        public void run() {
            if (!isVisible()) return;
            boolean active = false;
            for (Models.Job job : jobs) active |= job.isActive();
            if (active) refreshJobs();
            handler.postDelayed(this, POLL_MS);
        }
    };

    public AlephDropDownReceiver(MapView mapView, Context plugin, AlephConfig config, AlephClient client,
                                 ExecutorService worker) {
        super(mapView);
        this.plugin = plugin;
        this.config = config;
        this.client = client;
        this.worker = worker;
        this.picker = new AreaPicker(mapView);
    }

    @Override
    public void onReceive(Context context, Intent intent) {
        if (!SHOW_PLUGIN.equals(intent.getAction())) return;
        if (root == null) root = build();
        showDropDown(root, HALF_WIDTH, FULL_HEIGHT, FULL_WIDTH, HALF_HEIGHT, this);
        connect();
    }

    // --- UI construction ------------------------------------------------------------------

    private View build() {
        ScrollView scroll = new ScrollView(plugin);
        LinearLayout col = new LinearLayout(plugin);
        col.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(10);
        col.setPadding(pad, pad, pad, pad);
        scroll.addView(col);

        status = text(col, "Not connected.", false);

        header(col, "Server");
        urlField = field(col, "https://aleph.example.org", config.serverUrl(), InputType.TYPE_TEXT_VARIATION_URI);
        tokenField = field(col, "API token (from the Aleph admin page)", config.token(),
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        LinearLayout serverRow = row(col);
        button(serverRow, "Save & connect", v -> saveSettings());
        wifiOnly = new CheckBox(plugin);
        wifiOnly.setText("Download on Wi-Fi only");
        wifiOnly.setChecked(config.wifiOnly());
        wifiOnly.setOnCheckedChangeListener((b, checked) -> config.setWifiOnly(checked));
        serverRow.addView(wifiOnly);

        header(col, "1 · Area");
        LinearLayout areaRow = row(col);
        button(areaRow, "Map view", v -> setArea(picker.mapViewRing(), "Map view"));
        button(areaRow, "Pick a shape", v -> pickShape());
        areaLabel = text(col, "No area selected. Draw one with ATAK's shape tools, then pick it.", false);

        header(col, "2 · Layers");
        layersBox = new LinearLayout(plugin);
        layersBox.setOrientation(LinearLayout.VERTICAL);
        col.addView(layersBox);
        zoomSpinner = new Spinner(plugin);
        zoomSpinner.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(android.widget.AdapterView<?> parent, View view, int position, long id) {
                refreshEstimate();
            }

            @Override
            public void onNothingSelected(android.widget.AdapterView<?> parent) {
            }
        });
        col.addView(zoomSpinner);

        header(col, "3 · Capture");
        nameField = field(col, "Name (e.g. Sector 3)", "", InputType.TYPE_CLASS_TEXT);
        estimateLabel = text(col, "", false);
        captureButton = button(col, "Capture area", v -> submit());

        header(col, "Captures");
        jobsBox = new LinearLayout(plugin);
        jobsBox.setOrientation(LinearLayout.VERTICAL);
        col.addView(jobsBox);

        header(col, "Point lookup");
        button(col, "Tap a spot: elevation, address, photos", v -> lookupPoint());
        pointLabel = text(col, "", false);
        return scroll;
    }

    private int dp(int value) {
        return Math.round(value * plugin.getResources().getDisplayMetrics().density);
    }

    private TextView text(ViewGroup parent, String value, boolean bold) {
        TextView view = new TextView(plugin);
        view.setText(value);
        view.setTextColor(plugin.getResources().getColor(bold ? R.color.al_text_primary : R.color.al_text_secondary));
        if (bold) view.setTypeface(Typeface.DEFAULT_BOLD);
        parent.addView(view);
        return view;
    }

    private void header(ViewGroup parent, String value) {
        TextView view = text(parent, value, true);
        view.setPadding(0, dp(14), 0, dp(4));
    }

    private EditText field(ViewGroup parent, String hint, String value, int type) {
        EditText field = new EditText(plugin);
        field.setHint(hint);
        field.setText(value);
        field.setInputType(type);
        field.setSingleLine(true);
        parent.addView(field);
        return field;
    }

    private LinearLayout row(ViewGroup parent) {
        LinearLayout row = new LinearLayout(plugin);
        row.setOrientation(LinearLayout.HORIZONTAL);
        parent.addView(row);
        return row;
    }

    private Button button(ViewGroup parent, String label, View.OnClickListener onClick) {
        Button button = new Button(plugin);
        button.setText(label);
        button.setAllCaps(false);
        button.setOnClickListener(onClick);
        parent.addView(button);
        return button;
    }

    // --- actions -----------------------------------------------------------------------------

    /** Run on the worker; surface any failure to the operator instead of dying silently (§8). */
    private void background(String what, Task task) {
        worker.submit(() -> {
            try {
                task.run();
            } catch (Exception e) {
                Log.e(TAG, what + " failed", e);
                ui(() -> {
                    status.setText(what + " failed: " + e.getMessage());
                    toast(what + " failed: " + e.getMessage());
                });
            }
        });
    }

    private interface Task {
        void run() throws Exception;
    }

    private void ui(Runnable runnable) {
        handler.post(runnable);
    }

    private void toast(String message) {
        Toast.makeText(getMapView().getContext(), message, Toast.LENGTH_LONG).show();
    }

    private void saveSettings() {
        try {
            config.save(urlField.getText().toString(), tokenField.getText().toString());
            urlField.setText(config.serverUrl());
            connect();
        } catch (IllegalArgumentException e) {
            status.setText(e.getMessage());
        }
    }

    private void connect() {
        if (!config.isConfigured()) {
            status.setText("Enter the Aleph server URL and your token, then Save & connect.");
            return;
        }
        status.setText("Connecting…");
        background("Connect", () -> {
            Models.ServerInfo result = client.info();
            List<Models.Job> list = client.jobs();  // also proves the token works
            ui(() -> {
                if (!result.compatible()) {
                    status.setText("Server speaks Aleph API v" + result.api + "; this plugin needs v"
                            + Models.SUPPORTED_API + ". Update the plugin or the server.");
                    return;
                }
                info = result;
                status.setText(String.format(Locale.US, "Connected · Aleph %s · up to %.0f km² · kept %d h",
                        result.version, result.maxAreaKm2, result.ttlHours));
                buildLayerChoices();
                showJobs(list);
                handler.removeCallbacks(poll);
                handler.postDelayed(poll, POLL_MS);
            });
        });
    }

    private void buildLayerChoices() {
        layersBox.removeAllViews();
        layerBoxes.clear();
        for (int i = 0; i < LAYER_LABELS.length; i += 2) {
            if (!info.layers.contains(LAYER_LABELS[i])) continue;
            CheckBox box = new CheckBox(plugin);
            box.setText(LAYER_LABELS[i + 1]);
            box.setTag(LAYER_LABELS[i]);
            box.setChecked(!"photos".equals(LAYER_LABELS[i]));
            box.setOnCheckedChangeListener((b, c) -> refreshEstimate());
            layersBox.addView(box);
            layerBoxes.add(box);
        }
        zoomChoices.clear();
        List<String> labels = new ArrayList<>();
        for (int z = 15; z <= Math.min(19, info.imageryMaxZoom); z++) {
            zoomChoices.add(z);
            // Ground resolution at ~40°N (cos ≈ 0.77), close enough for the contiguous US.
            labels.add(String.format(Locale.US, "Imagery detail z%d (~%.1f m)", z, 156543.03 * 0.77 / Math.pow(2, z)));
        }
        zoomSpinner.setAdapter(new ArrayAdapter<>(plugin, android.R.layout.simple_spinner_dropdown_item, labels));
        zoomSpinner.setSelection(Math.max(0, zoomChoices.indexOf(info.defaultZoom)));
    }

    private void pickShape() {
        toast("Tap a shape on the map");
        picker.pickShape(new AreaPicker.AreaCallback() {
            @Override
            public void onArea(double[][] ring, String label) {
                setArea(ring, label);
            }

            @Override
            public void onRejected(String reason) {
                toast(reason);
            }
        });
    }

    private void setArea(double[][] ring, String label) {
        area = AreaMath.normalize(ring);
        double km2 = AreaMath.areaKm2(area);
        String limit = info == null ? "" : String.format(Locale.US, " (limit %.0f km²)", info.maxAreaKm2);
        areaLabel.setText(String.format(Locale.US, "%s · %.2f km²%s", label, km2, limit));
        refreshEstimate();
    }

    private JSONObject captureRequest() throws JSONException {
        if (area == null || info == null) return null;
        JSONArray layers = new JSONArray();
        for (CheckBox box : layerBoxes) if (box.isChecked()) layers.put(box.getTag());
        if (layers.length() == 0) return null;
        JSONObject request = new JSONObject().put("area", AreaMath.toGeoJson(area)).put("layers", layers);
        if (zoomSpinner.getSelectedItemPosition() >= 0 && !zoomChoices.isEmpty()) {
            request.put("options", new JSONObject().put("imagery_zoom", zoomChoices.get(zoomSpinner.getSelectedItemPosition())));
        }
        String name = nameField.getText().toString().trim();
        if (!name.isEmpty()) request.put("name", name);
        return request;
    }

    private void refreshEstimate() {
        final JSONObject request;
        try {
            request = captureRequest();
        } catch (JSONException e) {
            return;
        }
        if (request == null) {
            estimateLabel.setText("");
            return;
        }
        background("Estimate", () -> {
            Models.Estimate e = client.estimate(request);
            ui(() -> {
                estimateLabel.setText(String.format(Locale.US, "≈ %.1f MB package · ~%d min%s", e.bytes / 1e6,
                        Math.max(1, e.seconds / 60), e.allowed ? "" : " — area too large"));
                captureButton.setEnabled(e.allowed);
            });
        });
    }

    private void submit() {
        final JSONObject request;
        try {
            request = captureRequest();
        } catch (JSONException e) {
            return;
        }
        if (request == null) {
            toast("Choose an area and at least one layer first.");
            return;
        }
        captureButton.setEnabled(false);
        background("Capture", () -> {
            Models.Job job = client.create(request);
            ui(() -> {
                captureButton.setEnabled(true);
                toast("Capture started: " + job.name);
            });
            refreshJobs();
        });
    }

    private void refreshJobs() {
        background("Refresh", () -> {
            List<Models.Job> list = client.jobs();
            ui(() -> showJobs(list));
        });
    }

    private void showJobs(List<Models.Job> list) {
        jobs = list;
        jobsBox.removeAllViews();
        if (list.isEmpty()) text(jobsBox, "No captures yet.", false);
        for (Models.Job job : list) {
            LinearLayout card = new LinearLayout(plugin);
            card.setOrientation(LinearLayout.VERTICAL);
            card.setPadding(0, dp(6), 0, dp(6));
            jobsBox.addView(card);
            text(card, String.format(Locale.US, "%s · %s · %.2f km²", job.name, job.state, job.areaKm2), true);
            if (job.isActive()) {
                text(card, String.format(Locale.US, "%.0f%% %s", job.percent, job.phase == null ? "" : job.phase), false);
            }
            for (String warning : job.warnings) text(card, "⚠ " + warning, false);
            for (String error : job.layerErrors) text(card, "✗ " + error, false);
            if (job.error != null) text(card, "✗ " + job.error, false);
            LinearLayout actions = row(card);
            if (job.isComplete()) {
                button(actions, String.format(Locale.US, "Download & import (%.1f MB)", job.packageBytes / 1e6),
                        v -> downloadAndImport(job));
            }
            if (job.canRetry()) button(actions, "Retry", v -> background("Retry", () -> {
                client.retry(job.id);
                refreshJobs();
            }));
            button(actions, job.isActive() ? "Cancel" : "Delete", v -> background("Delete", () -> {
                client.delete(job.id);
                refreshJobs();
            }));
        }
    }

    private void downloadAndImport(Models.Job job) {
        if (downloading) {
            toast("A download is already running.");
            return;
        }
        if (config.wifiOnly() && !PackageDownloader.onUnmeteredNetwork(getMapView().getContext())) {
            toast("Wi-Fi only is on and you're not on Wi-Fi. Untick it under Server to use mobile data.");
            return;
        }
        downloading = true;
        cancelDownload.set(false);
        status.setText("Downloading " + job.name + "…");
        background("Download", () -> {
            try {
                File dir = PackageImporter.downloadDir();
                PackageDownloader.checkStorage(dir, job.packageBytes);
                File pkg = PackageDownloader.download(client, job, dir, (done, total) -> ui(() ->
                        status.setText(String.format(Locale.US, "Downloading %s: %.1f / %.1f MB", job.name, done / 1e6, total / 1e6))),
                        cancelDownload);
                DtedInstaller.Result dted = PackageImporter.installElevation(pkg);
                PackageImporter.importPackage(pkg);
                ui(() -> {
                    status.setText(String.format(Locale.US, "Imported %s. Elevation: %d new cell(s), %d merged, %d left as-is.",
                            job.name, dted.added, dted.merged, dted.skipped));
                    toast("Imported " + job.name + " — it's in Overlay Manager and works offline.");
                });
            } finally {
                downloading = false;
            }
        });
    }

    private void lookupPoint() {
        if (!config.isConfigured()) {
            toast("Connect to an Aleph server first.");
            return;
        }
        toast("Tap a spot on the map");
        picker.pickPoint((lat, lon) -> {
            pointLabel.setText("Looking up…");
            background("Point lookup", () -> {
                JSONObject r = client.point(lat, lon);
                StringBuilder text = new StringBuilder(String.format(Locale.US, "%.5f, %.5f", lat, lon));
                if (!r.isNull("elevation_m")) {
                    double m = r.optDouble("elevation_m");
                    text.append(String.format(Locale.US, "\nElevation %.0f m (%.0f ft)", m, m * 3.28084));
                }
                JSONObject address = r.optJSONObject("address");
                if (address != null) text.append("\nNear ").append(address.optString("label"));
                JSONArray photos = r.optJSONArray("photos");
                if (photos != null) text.append("\n").append(photos.length()).append(" street-level photo(s) within 150 m");
                ui(() -> pointLabel.setText(text.toString()));
            });
        });
    }

    // --- DropDown lifecycle -----------------------------------------------------------------

    @Override
    protected void disposeImpl() {
        handler.removeCallbacksAndMessages(null);
        picker.cancel();
        cancelDownload.set(true);
    }

    @Override
    public void onDropDownSelectionRemoved() {
    }

    @Override
    public void onDropDownVisible(boolean visible) {
        if (visible && info != null) {
            handler.removeCallbacks(poll);
            handler.post(poll);
        }
    }

    @Override
    public void onDropDownSizeChanged(double width, double height) {
    }

    @Override
    public void onDropDownClose() {
        handler.removeCallbacks(poll);
        picker.cancel();
    }
}
