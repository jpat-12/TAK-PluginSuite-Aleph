// The PluginAPI handed to install(), shared with components and lib helpers. Getters on it pull
// the live Pinia stores on access, so keep the API object, never a cached `api.map`.
import type { PluginAPI } from '@tak-ps/cloudtak';

let current: PluginAPI | null = null;

export function setPluginApi(api: PluginAPI): void {
    current = api;
}

export function pluginApi(): PluginAPI {
    if (!current) throw new Error('[plugin-aleph] used before install()');
    return current;
}
