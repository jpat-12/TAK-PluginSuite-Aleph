package com.atakmap.android.aleph.plugin;

import android.content.Context;

import com.atak.plugins.impl.AbstractPluginTool;
import com.atakmap.android.aleph.AlephDropDownReceiver;

/** Toolbar button; fires SHOW_PLUGIN, which opens the panel. */
public class AlephTool extends AbstractPluginTool {

    public AlephTool(Context context) {
        super(context,
                context.getString(R.string.app_name),
                context.getString(R.string.app_name),
                context.getResources().getDrawable(R.drawable.ic_launcher),
                AlephDropDownReceiver.SHOW_PLUGIN);
    }
}
