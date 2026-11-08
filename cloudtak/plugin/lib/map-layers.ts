// Capture previews on the CloudTAK map, plus the two map interactions the panel needs
// (drag-free rectangle drawing and one-shot point picking). Swipe-compare lives in swipe.ts.
//
// Deliberate deviation from AGENTS.md's "data goes through the worker DB": a capture is a
// reference overlay (imagery tiles + thousands of OSM features), not CoT. Pushing it through
// the feature DB would broadcast it as CoT and swamp DataSync, so it's drawn as plain MapLibre
// sources/layers, all prefixed `plugin-aleph-` and removed on disable(). Tiles and GeoJSON load
// straight from Aleph via the signed URLs in the job record.
import type { GeoJSONSource, LayerSpecification, Map as MapLibreMap, MapMouseEvent } from 'maplibre-gl';
import { pluginApi } from './plugin-api.ts';
import { bboxPolygon } from './area.ts';
import { refreshSwipeSource, startSwipe, stopSwipe, swipeState } from './swipe.ts';
import { legendAdd, legendClear, legendRemove } from './legend.ts';
import type { Job, Polygon } from './types.ts';

const PREFIX = 'plugin-aleph-';
const DRAFT = `${PREFIX}draft`;

// Same palette and names as the KMZ in the package (aleph_tak/formats/kml.py STYLES), so web,
// TAK and the legend (legend.ts) agree. `area` = drawn as a filled polygon.
export const OSM_STYLES: { key: string; label: string; color: string; area: boolean }[] = [
    { key: 'roads_major', label: 'Major roads', color: '#ffd700', area: false },
    { key: 'roads_minor', label: 'Local roads', color: '#ffffff', area: false },
    { key: 'trails', label: 'Trails & tracks', color: '#a56a2a', area: false },
    { key: 'railways', label: 'Railways', color: '#555555', area: false },
    { key: 'power', label: 'Power lines', color: '#ff0000', area: false },
    { key: 'waterways', label: 'Waterways', color: '#3399ff', area: false },
    { key: 'water', label: 'Water', color: '#3399ff', area: true },
    { key: 'buildings', label: 'Buildings', color: '#ff8000', area: true },
    { key: 'aero', label: 'Airfields & helipads', color: '#ff00ff', area: true },
];
const LINE_COLORS = OSM_STYLES.map((style) => [style.key, style.color]);

function map(): MapLibreMap {
    return pluginApi().map;
}

/** Put overlays under CloudTAK's own symbols so CoT markers stay on top of imagery. */
function firstSymbolLayer(target: MapLibreMap): string | undefined {
    return target.getStyle().layers?.find((layer) => layer.type === 'symbol' || layer.type === 'circle')?.id;
}

function addLayer(layer: LayerSpecification, below = true, target: MapLibreMap = map()): void {
    if (!target.getLayer(layer.id)) target.addLayer(layer, below ? firstSymbolLayer(target) : undefined);
}

function colorByLayer(fallback: string): unknown[] {
    return ['match', ['get', 'layer'], ...LINE_COLORS.flat(), fallback];
}

export type Dataset = 'imagery' | 'osm' | 'photos';

/** What a capture can put on the map, in panel order. Elevation has no map preview. */
export const DATASETS: { key: Dataset; label: string }[] = [
    { key: 'imagery', label: 'Imagery' }, { key: 'osm', label: 'OSM' }, { key: 'photos', label: 'Photos' },
];
const SOURCE_SUFFIX: Record<Dataset, string> = { imagery: 'img', osm: 'osm', photos: 'photos' };

function sourceId(jobId: string, dataset: Dataset): string {
    return `${PREFIX}${jobId}-${SOURCE_SUFFIX[dataset]}`;
}

export function isShown(job: Job): boolean {
    return Boolean(map().getSource(`${PREFIX}${job.id}-area`));
}

export function availableDatasets(job: Job): Dataset[] {
    const links = job.links;
    const has: Record<Dataset, boolean> = {
        imagery: Boolean(links?.tiles && links.tiles_info), osm: Boolean(links?.osm), photos: Boolean(links?.photos),
    };
    return DATASETS.map((d) => d.key).filter((d) => has[d]);
}

/** Datasets of the job currently on the main map. */
export function shownDatasets(jobId: string): Dataset[] {
    const m = map();
    return DATASETS.map((d) => d.key).filter((d) => Boolean(m.getSource(sourceId(jobId, d))));
}

/** True if the capture has anything to compare against the basemap (imagery or OSM). */
export function hasMapData(job: Job): boolean {
    return availableDatasets(job).some((d) => d !== 'photos');
}

/**
 * The capture's data layers (imagery, OSM, photos — not the area outline) on `target`, limited to
 * `datasets`. Shared by the main map and the swipe-compare overlay (swipe.ts), so both draw the same thing.
 */
export function addJobData(target: MapLibreMap, job: Job, imagerySource = 'open-data imagery',
    datasets: Dataset[] = availableDatasets(job)): void {
    const links = job.links;
    if (!links) return;
    const id = `${PREFIX}${job.id}`;
    if (datasets.includes('imagery') && links.tiles && links.tiles_info && !target.getSource(`${id}-img`)) {
        target.addSource(`${id}-img`, {
            type: 'raster', tiles: [links.tiles], tileSize: 256,
            minzoom: links.tiles_info.min_zoom, maxzoom: links.tiles_info.max_zoom,
            bounds: links.tiles_info.bounds, attribution: `Imagery: ${imagerySource}`,
        });
        // Imagery always sits under the capture's own OSM lines, even when switched on after them.
        const layer: LayerSpecification = { id: `${id}-img`, type: 'raster', source: `${id}-img` };
        if (target.getLayer(`${id}-osm-fill`)) target.addLayer(layer, `${id}-osm-fill`);
        else addLayer(layer, true, target);
    }
    if (datasets.includes('osm') && links.osm && !target.getSource(`${id}-osm`)) {
        target.addSource(`${id}-osm`, { type: 'geojson', data: links.osm, attribution: '© OpenStreetMap contributors' });
        addLayer({ id: `${id}-osm-fill`, type: 'fill', source: `${id}-osm`, filter: ['==', ['geometry-type'], 'Polygon'],
            paint: { 'fill-color': colorByLayer('#ff8000') as never, 'fill-opacity': 0.25 } }, true, target);
        addLayer({ id: `${id}-osm-line`, type: 'line', source: `${id}-osm`,
            filter: ['in', ['geometry-type'], ['literal', ['LineString', 'MultiLineString', 'Polygon']]],
            paint: { 'line-color': colorByLayer('#ffffff') as never, 'line-width': 1.5 } }, true, target);
    }
    if (datasets.includes('photos') && links.photos && !target.getSource(`${id}-photos`)) {
        target.addSource(`${id}-photos`, { type: 'geojson', data: links.photos, attribution: 'Photos © Mapillary contributors, CC BY-SA' });
        addLayer({ id: `${id}-photos`, type: 'circle', source: `${id}-photos`,
            paint: { 'circle-radius': 5, 'circle-color': '#06b6d4', 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 1 } }, false, target);
    }
}

function removeJobData(target: MapLibreMap, jobId: string, dataset: Dataset): void {
    const source = sourceId(jobId, dataset);
    for (const layer of [...(target.getStyle().layers ?? [])]) {
        if ('source' in layer && layer.source === source) target.removeLayer(layer.id);
    }
    if (target.getSource(source)) target.removeSource(source);
}

/** Ids of the main map's data layers for a job (everything but the area outline). */
export function jobDataLayers(jobId: string): LayerSpecification[] {
    const prefix = `${PREFIX}${jobId}`;
    return (map().getStyle().layers ?? []).filter((layer) => layer.id.startsWith(prefix) && layer.id !== `${prefix}-area`);
}

/**
 * Show exactly `datasets` of a capture (plus its outline); none hides the capture. A running
 * compare of this capture is rebuilt with the new selection at the same divider position.
 */
export function setJobDatasets(job: Job, datasets: Dataset[], imagerySource = 'open-data imagery'): void {
    const links = job.links;
    if (!links) return;
    const want = availableDatasets(job).filter((d) => datasets.includes(d));
    if (!want.length) {
        hideJob(job.id);
        return;
    }
    const swipe = swipeState();
    const fraction = swipe?.jobId === job.id ? swipe.fraction : null;
    stopSwipe(job.id);                      // restores the main layers' opacity before they change
    const m = map();
    for (const dataset of availableDatasets(job)) {
        if (!want.includes(dataset)) removeJobData(m, job.id, dataset);
    }
    addJobData(m, job, imagerySource, want);
    const id = `${PREFIX}${job.id}`;
    if (!m.getSource(`${id}-area`)) {
        m.addSource(`${id}-area`, { type: 'geojson', data: links.area });
        addLayer({ id: `${id}-area`, type: 'line', source: `${id}-area`,
            paint: { 'line-color': '#06b6d4', 'line-width': 2, 'line-dasharray': [2, 2] } }, false);
    }
    legendAdd(job, imagerySource, want);
    if (want.includes('imagery')) watchTiles(job.id);
    else forgetTiles(job.id);
    if (fraction !== null && want.some((d) => d !== 'photos')) startSwipe(job, imagerySource, fraction);
}

export function showJob(job: Job, imagerySource = 'open-data imagery'): void {
    setJobDatasets(job, availableDatasets(job), imagerySource);
}

export function hideJob(jobId: string): void {
    stopSwipe(jobId);
    legendRemove(jobId);
    forgetTiles(jobId);
    const m = map();
    const prefix = `${PREFIX}${jobId}`;
    for (const layer of [...(m.getStyle().layers ?? [])]) {
        if (layer.id.startsWith(prefix)) m.removeLayer(layer.id);
    }
    for (const source of Object.keys(m.getStyle().sources ?? {})) {
        if (source.startsWith(prefix)) m.removeSource(source);
    }
}

// Preview tiles that fail to load (Aleph restarting, a dropped connection, an expired signed
// link): MapLibre doesn't re-request a failed tile, so after errors settle we reload the
// capture's imagery once by ourselves; if tiles still fail, the panel offers "Reload tiles".
// Empty tiles (HTTP 204: no coverage) are not errors and never trigger this.
const TILE_SETTLE_MS = 3000;
const tileWatch = new Map<string, { errors: number; retried: boolean; timer: ReturnType<typeof setTimeout> | null }>();
const troubleListeners = new Set<(jobIds: string[]) => void>();
let errorHandler: ((e: object) => void) | null = null;

function troubled(): string[] {
    return [...tileWatch.entries()].filter(([, w]) => w.retried && w.errors > 0 && !w.timer).map(([id]) => id);
}

function notifyTrouble(): void {
    const ids = troubled();
    for (const listener of troubleListeners) listener(ids);
}

/** Jobs whose imagery preview still fails after the automatic reload. Returns the unsubscribe. */
export function onTileTrouble(listener: (jobIds: string[]) => void): () => void {
    troubleListeners.add(listener);
    listener(troubled());
    return () => troubleListeners.delete(listener);
}

function refreshImagery(jobId: string): void {
    const source = sourceId(jobId, 'imagery');
    if (map().getSource(source)) map().refreshTiles(source);
    refreshSwipeSource(source);
}

/** The panel's "Reload tiles": start the error count over and re-request every imagery tile. */
export function reloadTiles(jobId: string): void {
    const watch = tileWatch.get(jobId);
    if (!watch) return;
    if (watch.timer) clearTimeout(watch.timer);
    Object.assign(watch, { errors: 0, retried: true, timer: null });
    notifyTrouble();
    refreshImagery(jobId);
}

function onTileError(jobId: string): void {
    const watch = tileWatch.get(jobId);
    if (!watch) return;
    watch.errors += 1;
    if (watch.timer) clearTimeout(watch.timer);
    // Wait for the burst to settle, then either reload once automatically or report it.
    watch.timer = setTimeout(() => {
        watch.timer = null;
        if (!watch.retried) {
            watch.retried = true;
            watch.errors = 0;
            refreshImagery(jobId);
        }
        notifyTrouble();
    }, TILE_SETTLE_MS);
}

function watchTiles(jobId: string): void {
    if (!tileWatch.has(jobId)) tileWatch.set(jobId, { errors: 0, retried: false, timer: null });
    if (errorHandler) return;
    errorHandler = (e) => {
        // A tile failure carries the source and tile; style/other errors don't (same test as CloudTAK's own handler).
        const { sourceId: source, tile } = e as { sourceId?: string; tile?: unknown };
        const match = tile && source ? /^plugin-aleph-(.+)-img$/.exec(source) : null;
        if (match) onTileError(match[1]);
    };
    map().on('error', errorHandler);
}

function forgetTiles(jobId?: string): void {
    for (const [id, watch] of [...tileWatch.entries()]) {
        if (jobId !== undefined && id !== jobId) continue;
        if (watch.timer) clearTimeout(watch.timer);
        tileWatch.delete(id);
    }
    if (!tileWatch.size && errorHandler) {
        try {
            map().off('error', errorHandler);
        } catch {
            /* map gone */
        }
        errorHandler = null;
    }
    notifyTrouble();
}

export function zoomTo(polygon: Polygon): void {
    const ring = polygon.coordinates[0];
    const lons = ring.map((p) => p[0]);
    const lats = ring.map((p) => p[1]);
    map().fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: 60 });
}

/** Everything this plugin ever put on the map. Safe when the map isn't loaded yet. */
export function removeAll(): void {
    stopSwipe();
    legendClear();
    forgetTiles();
    try {
        const m = map();
        for (const layer of [...(m.getStyle()?.layers ?? [])]) {
            if (layer.id.startsWith(PREFIX)) m.removeLayer(layer.id);
        }
        for (const source of Object.keys(m.getStyle()?.sources ?? {})) {
            if (source.startsWith(PREFIX)) m.removeSource(source);
        }
    } catch {
        /* map not loaded — nothing of ours is on it */
    }
    cancelInteraction();
}

export function showDraft(polygon: Polygon | null): void {
    const m = map();
    const data = polygon ?? { type: 'FeatureCollection' as const, features: [] };
    const source = m.getSource(DRAFT) as GeoJSONSource | undefined;
    if (source) {
        source.setData(data as never);
        return;
    }
    m.addSource(DRAFT, { type: 'geojson', data: data as never });
    addLayer({ id: `${DRAFT}-fill`, type: 'fill', source: DRAFT, paint: { 'fill-color': '#06b6d4', 'fill-opacity': 0.12 } }, false);
    addLayer({ id: `${DRAFT}-line`, type: 'line', source: DRAFT, paint: { 'line-color': '#06b6d4', 'line-width': 2 } }, false);
}

// One map interaction at a time (rectangle or point); a new one cancels the old.
let cancelCurrent: (() => void) | null = null;

export function cancelInteraction(): void {
    cancelCurrent?.();
    cancelCurrent = null;
}

/** Click one corner, then the opposite corner. Resolves with the rectangle, or null if cancelled. */
export function drawRectangle(): Promise<Polygon | null> {
    cancelInteraction();
    const m = map();
    return new Promise((resolve) => {
        let first: [number, number] | null = null;
        const box = (a: [number, number], b: [number, number]) =>
            bboxPolygon(Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1]));
        const onMove = (e: MapMouseEvent) => {
            if (first) showDraft(box(first, [e.lngLat.lng, e.lngLat.lat]));
        };
        const onClick = (e: MapMouseEvent) => {
            const here: [number, number] = [e.lngLat.lng, e.lngLat.lat];
            if (!first) {
                first = here;
                return;
            }
            finish(box(first, here));
        };
        const finish = (result: Polygon | null) => {
            m.off('click', onClick);
            m.off('mousemove', onMove);
            m.getCanvas().style.cursor = '';
            cancelCurrent = null;
            resolve(result);
        };
        m.getCanvas().style.cursor = 'crosshair';
        m.on('click', onClick);
        m.on('mousemove', onMove);
        cancelCurrent = () => finish(null);
    });
}

/** Resolve with the next clicked map location (lon, lat), or null if cancelled. */
export function pickPoint(): Promise<[number, number] | null> {
    cancelInteraction();
    const m = map();
    return new Promise((resolve) => {
        const onClick = (e: MapMouseEvent) => finish([e.lngLat.lng, e.lngLat.lat]);
        const finish = (result: [number, number] | null) => {
            m.off('click', onClick);
            m.getCanvas().style.cursor = '';
            cancelCurrent = null;
            resolve(result);
        };
        m.getCanvas().style.cursor = 'crosshair';
        m.on('click', onClick);
        cancelCurrent = () => finish(null);
    });
}
