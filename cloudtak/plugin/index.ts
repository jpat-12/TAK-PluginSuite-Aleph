// Aleph for TAK — CloudTAK plugin entry. Lands at <CloudTAK>/api/web/plugins/aleph/index.ts
// (discovered by CloudTAK's `plugins/*/index.ts` glob at build time).
//
// Draw or pick an area → choose layers → see the size estimate → capture → preview the result
// on the map and download the TAK data package for ATAK/WinTAK. Plus point lookup.
//
// Lifecycle (AGENTS.md §2): routes in install() only; enable()/disable() add/remove just the
// menu item and our map overlays — disable() runs before the first enable().
import type { App } from 'vue';
import { markRaw } from 'vue';
import type { MenuItemConfig, PluginAPI, PluginInstance } from '@tak-ps/cloudtak';
import { IconSatellite } from '@tabler/icons-vue';
import AlephPanel from './components/AlephPanel.vue';
import { setPluginApi } from './lib/plugin-api.ts';
import { removeAll } from './lib/map-layers.ts';

const MENU_KEY = 'plugin-aleph';
const ROUTE_NAME = 'home-menu-plugin-aleph';

export default class AlephPlugin implements PluginInstance {
    api: PluginAPI;

    constructor(api: PluginAPI) {
        this.api = api;
    }

    static async install(app: App, api: PluginAPI): Promise<AlephPlugin> {
        void app;
        setPluginApi(api);
        api.routes.add({ path: 'plugin-aleph', name: ROUTE_NAME, component: markRaw(AlephPanel) }, 'home-menu');
        return new AlephPlugin(api);
    }

    async enable(): Promise<void> {
        this.api.menu.add({
            key: MENU_KEY,
            label: 'Aleph Capture',
            route: ROUTE_NAME,
            tooltip: 'Capture an area for offline use',
            description: 'Imagery, elevation, OSM and photos of an area as a TAK data package',
            icon: markRaw(IconSatellite) as unknown as MenuItemConfig['icon'],
        } as MenuItemConfig);
    }

    async disable(): Promise<void> {
        try {
            this.api.menu.remove(MENU_KEY);
        } catch {
            /* map not loaded yet — nothing to remove */
        }
        removeAll();
    }
}
