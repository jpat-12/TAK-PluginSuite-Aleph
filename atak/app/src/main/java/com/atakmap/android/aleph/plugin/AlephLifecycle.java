package com.atakmap.android.aleph.plugin;

import com.atak.plugins.impl.AbstractPlugin;
import com.atak.plugins.impl.PluginContextProvider;
import com.atakmap.android.aleph.AlephMapComponent;

import gov.tak.api.plugin.IServiceController;

/** Plugin entry point (named in assets/plugin.xml). */
public class AlephLifecycle extends AbstractPlugin {

    public AlephLifecycle(IServiceController serviceController) {
        super(serviceController,
                new AlephTool(serviceController.getService(PluginContextProvider.class).getPluginContext()),
                new AlephMapComponent());
    }
}
