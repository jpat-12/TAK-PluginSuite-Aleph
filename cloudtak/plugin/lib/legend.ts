// Map legend for shown captures: what each colour/swatch on the map is, and — while comparing —
// which side of the slider is which. A MapLibre control in the bottom-left slot, which CloudTAK
// already lifts above its GPS panel. It lists only what's on the map: imagery if any shown
// capture has it, and only the OSM categories that actually occur in the shown captures.
// Present while at least one capture is shown; collapsible (header click), remembered for the session.
import type { GeoJSONSource, IControl, Map as MapLibreMap } from 'maplibre-gl';
import { pluginApi } from './plugin-api.ts';
import { OSM_STYLES, type Dataset } from './map-layers.ts';
import { onSwipeChange, swipeState } from './swipe.ts';
import type { Job } from './types.ts';

const ACCENT = '#06b6d4';
const CHIP_BG = '#4b5563';             // dark chip so white/yellow lines stay visible in light theme

interface Entry {
    job: Job;
    imagery: string;
    datasets: Dataset[];                // what the panel has switched on for this capture
    osm: Set<string> | null;            // OSM categories in the capture; null until its GeoJSON has been read
}

const entries = new Map<string, Entry>();
let collapsed = false;
let unsubscribeSwipe: (() => void) | null = null;

function map(): MapLibreMap {
    return pluginApi().map;
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, css = ''): HTMLElementTagNameMap[K] {
    const node = document.createElement(tag);
    node.style.cssText = css;
    return node;
}

function chip(): HTMLSpanElement {
    return el('span', `flex:none;position:relative;display:inline-block;width:24px;height:12px;border-radius:2px;background:${CHIP_BG};`);
}

function lineSwatch(color: string, dashed = false): HTMLSpanElement {
    const swatch = chip();
    swatch.append(el('span', `position:absolute;left:3px;right:3px;top:5px;border-top:2px ${dashed ? 'dashed' : 'solid'} ${color};`));
    return swatch;
}

function areaSwatch(color: string): HTMLSpanElement {
    const swatch = chip();
    swatch.append(el('span', `position:absolute;inset:2px 5px;border:1.5px solid ${color};background:${color}66;`));
    return swatch;
}

function dotSwatch(color: string): HTMLSpanElement {
    const swatch = chip();
    swatch.append(el('span', `position:absolute;left:8px;top:2px;width:8px;height:8px;border-radius:50%;background:${color};border:1px solid #fff;`));
    return swatch;
}

function imagerySwatch(): HTMLSpanElement {
    const swatch = chip();
    swatch.style.background = 'linear-gradient(135deg,#4d7c3a 0%,#8a9a5b 45%,#b8a06a 70%,#5b7fa6 100%)';
    return swatch;
}

function row(swatch: HTMLElement, text: string): HTMLDivElement {
    const line = el('div', 'display:flex;align-items:center;gap:6px;margin-top:3px;');
    const label = el('span', 'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;');
    label.textContent = text;
    label.title = text;
    line.append(swatch, label);
    return line;
}

function heading(text: string): HTMLDivElement {
    const node = el('div', 'margin-top:6px;font-weight:600;opacity:.7;text-transform:uppercase;font-size:10px;letter-spacing:.04em;');
    node.textContent = text;
    return node;
}

class LegendControl implements IControl {
    container = el('div', 'pointer-events:auto;max-width:220px;padding:6px 8px;border-radius:6px;'
        + 'background:var(--tblr-bg-surface,#fff);color:var(--tblr-body-color,#182433);'
        + 'border:1px solid var(--tblr-border-color,#dce1e7);box-shadow:0 1px 4px rgba(0,0,0,.25);font:12px/1.35 sans-serif;');

    constructor() {
        this.container.className = 'maplibregl-ctrl plugin-aleph-legend';
    }

    onAdd(): HTMLElement {
        return this.container;
    }

    onRemove(): void {
        this.container.remove();
    }

    render(): void {
        const header = el('button', 'all:unset;cursor:pointer;display:flex;align-items:center;gap:6px;width:100%;font-weight:600;');
        header.type = 'button';
        header.setAttribute('aria-expanded', String(!collapsed));
        header.title = collapsed ? 'Show legend' : 'Hide legend';
        header.append(el('span', `width:10px;height:10px;border-radius:2px;background:${ACCENT};`),
            Object.assign(el('span'), { textContent: 'Aleph capture legend' }),
            Object.assign(el('span', 'margin-left:auto;opacity:.6;'), { textContent: collapsed ? '▸' : '▾' }));
        header.addEventListener('click', () => {
            collapsed = !collapsed;
            this.render();
        });
        this.container.replaceChildren(header);
        if (collapsed) return;

        const shown = [...entries.values()];
        const body = el('div');
        body.append(row(lineSwatch(ACCENT, true), shown.length > 1 ? `Capture areas (${shown.length})` : 'Capture area'));

        const swipe = swipeState();
        const compared = swipe ? entries.get(swipe.jobId) : undefined;
        if (swipe && compared) {
            body.append(heading('Slider'));
            body.append(row(lineSwatch(ACCENT), `◀ ${compared.job.name || 'capture'}  |  base map ▶`));
            body.append(row(el('span', 'flex:none;width:24px;'), `Divider at ${Math.round(swipe.fraction * 100)}% of the area`));
        }

        const imagery = [...new Set(shown.filter((e) => e.datasets.includes('imagery')).map((e) => e.imagery))];
        if (imagery.length) {
            body.append(heading('Imagery'));
            for (const name of imagery) body.append(row(imagerySwatch(), name));
        }

        const withOsm = shown.filter((e) => e.datasets.includes('osm'));
        if (withOsm.length) {
            body.append(heading('OpenStreetMap'));
            const loading = withOsm.some((e) => e.osm === null);
            const present = new Set(withOsm.flatMap((e) => [...(e.osm ?? [])]));
            // Until the GeoJSON is in, show the whole palette rather than an empty section.
            const styles = loading && !present.size ? OSM_STYLES : OSM_STYLES.filter((s) => present.has(s.key));
            for (const style of styles) body.append(row(style.area ? areaSwatch(style.color) : lineSwatch(style.color), style.label));
            if (!styles.length) body.append(row(el('span', 'flex:none;width:24px;'), 'No mapped features'));
        }

        if (shown.some((e) => e.datasets.includes('photos'))) {
            body.append(heading('Photos'));
            body.append(row(dotSwatch(ACCENT), 'Street-level photo (Mapillary)'));
        }
        this.container.append(body);
    }
}

let control: LegendControl | null = null;

function refresh(): void {
    if (!entries.size) {
        legendClear();
        return;
    }
    if (!control) {
        control = new LegendControl();
        map().addControl(control, 'bottom-left');
    }
    control.render();
}

/** Learn which OSM categories the capture has, once its GeoJSON source has loaded on the map. */
function loadCategories(entry: Entry): void {
    const m = map();
    const sourceId = `plugin-aleph-${entry.job.id}-osm`;
    const read = () => {
        const source = m.getSource(sourceId) as GeoJSONSource | undefined;
        if (!source) return;
        source.getData().then((data) => {
            const features = data.type === 'FeatureCollection' ? data.features : [];
            entry.osm = new Set(features.map((f) => String((f.properties ?? {}).layer)));
        }).catch(() => {
            entry.osm = new Set(OSM_STYLES.map((s) => s.key));      // unreadable: fall back to the full palette
        }).finally(() => {
            if (entries.get(entry.job.id) === entry) refresh();
        });
    };
    if (m.getSource(sourceId) && m.isSourceLoaded(sourceId)) {
        read();
        return;
    }
    const onData = (e: { sourceId?: string; isSourceLoaded?: boolean }) => {
        if (e.sourceId !== sourceId || !e.isSourceLoaded) return;
        m.off('sourcedata', onData);
        read();
    };
    m.on('sourcedata', onData);
}

/** Add or update a shown capture. OSM categories already read for it are kept. */
export function legendAdd(job: Job, imagery: string, datasets: Dataset[]): void {
    const entry: Entry = { job, imagery, datasets, osm: entries.get(job.id)?.osm ?? null };
    entries.set(job.id, entry);
    unsubscribeSwipe ??= onSwipeChange(() => control?.render());
    if (entry.osm === null && datasets.includes('osm')) loadCategories(entry);
    refresh();
}

export function legendRemove(jobId: string): void {
    if (entries.delete(jobId)) refresh();
}

/** Remove the legend entirely (plugin disabled / everything hidden). Safe before the map loads. */
export function legendClear(): void {
    entries.clear();
    unsubscribeSwipe?.();
    unsubscribeSwipe = null;
    if (control) {
        try {
            map().removeControl(control);
        } catch {
            /* map already gone */
        }
        control = null;
    }
}
