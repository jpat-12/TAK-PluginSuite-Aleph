package com.atakmap.android.aleph;

import android.content.Context;
import android.content.Intent;

import com.atakmap.android.aleph.api.AlephClient;
import com.atakmap.android.aleph.api.AlephConfig;
import com.atakmap.android.dropdown.DropDownMapComponent;
import com.atakmap.android.ipc.AtakBroadcast.DocumentedIntentFilter;
import com.atakmap.android.maps.MapView;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Owns the plugin's long-lived objects and their teardown: settings, the HTTP client, the one
 * worker thread all network/file work runs on, and the panel.
 */
public class AlephMapComponent extends DropDownMapComponent {

    /** Own prefs file inside ATAK's data dir — keeps our token out of ATAK's settings screens. */
    private static final String PREFS_NAME = "aleph";

    private ExecutorService worker;

    @Override
    public void onCreate(Context context, Intent intent, MapView view) {
        context.setTheme(com.atakmap.android.aleph.plugin.R.style.ATAKPluginTheme);
        super.onCreate(context, intent, view);
        AlephConfig config = new AlephConfig(view.getContext().getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE));
        // One thread: requests are small and sequential, and a download should never race an import.
        worker = Executors.newSingleThreadExecutor(r -> new Thread(r, "aleph-worker"));
        AlephDropDownReceiver dropDown = new AlephDropDownReceiver(view, context, config, new AlephClient(config), worker);
        DocumentedIntentFilter filter = new DocumentedIntentFilter();
        filter.addAction(AlephDropDownReceiver.SHOW_PLUGIN, "Show the Aleph capture panel");
        registerDropDownReceiver(dropDown, filter);
    }

    @Override
    protected void onDestroyImpl(Context context, MapView view) {
        if (worker != null) worker.shutdownNow();
        super.onDestroyImpl(context, view);
    }
}
