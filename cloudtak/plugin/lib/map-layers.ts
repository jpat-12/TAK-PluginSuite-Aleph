// Capture previews on the CloudTAK map, plus the two map interactions the panel needs
// (drag-free rectangle drawing and one-shot point picking).
//
// Deliberate deviation from AGENTS.md's "data goes through the worker DB": a capture is a
// reference overlay (imagery tiles + thousands of OSM features), not CoT. Pushing it through
// the feature DB would broadcast it as CoT and swamp DataSync, so it's drawn as plain MapLibre
// sources/layers, all prefixed `plugin-aleph-` and removed on disable(). Tiles and GeoJSON load
// straight from Aleph via the signed URLs in the job record.
import type { GeoJSONSource, LayerSpecification, Map as MapLibreMap, MapMouseEvent } from 'maplibre-gl';
import { pluginApi } from './plugin-api.ts';
import { bboxPolygon } from './area.ts';
import type { Job, Polygon } from './types.ts';

const PREFIX = 'plugin-aleph-';
const DRAFT = `${PREFIX}draft`;

// Same palette as the KMZ in the package (aleph_tak/formats/kml.py), so web and TAK agree.
const LINE_COLORS: [string, string][] = [
    ['roads_major', '#ffd700'], ['roads_minor', '#ffffff'], ['trails', '#a56a2a'],
    ['railways', '#555555'], ['power', '#ff0000'], ['waterways', '#3399ff'], ['water', '#3399ff'],
    ['buildings', '#ff8000'], ['aero', '#ff00ff'],
];

function map(): MapLibreMap {
    return pluginApi().map;
}

/** Put overlays under CloudTAK's own symbols so CoT markers stay on top of imagery. */
function firstSymbolLayer(): string | undefined {
    return map().getStyle().layers?.find((layer) => layer.type === 'symbol' || layer.type === 'circle')?.id;
}

function addLayer(layer: LayerSpecification, below = true): void {
    if (!map().getLayer(layer.id)) map().addLayer(layer, below ? firstSymbolLayer() : undefined);
}

function colorByLayer(fallback: string): unknown[] {
    return ['match', ['get', 'layer'], ...LINE_COLORS.flat(), fallback];
}

export function isShown(job: Job): boolean {
    return Boolean(map().getSource(`${PREFIX}${job.id}-area`));
}

export function showJob(job: Job, imagerySource = 'open-data imagery'): void {
    const links = job.links;
    if (!links) return;
    const id = `${PREFIX}${job.id}`;
    const m = map();
    if (links.tiles && links.tiles_info && !m.getSource(`${id}-img`)) {
        m.addSource(`${id}-img`, {
            type: 'raster', tiles: [links.tiles], tileSize: 256,
            minzoom: links.tiles_info.min_zoom, maxzoom: links.tiles_info.max_zoom,
            bounds: links.tiles_info.bounds, attribution: `Imagery: ${imagerySource}`,
        });
        addLayer({ id: `${id}-img`, type: 'raster', source: `${id}-img` });
    }
    if (links.osm && !m.getSource(`${id}-osm`)) {
        m.addSource(`${id}-osm`, { type: 'geojson', data: links.osm, attribution: '© OpenStreetMap contributors' });
        addLayer({ id: `${id}-osm-fill`, type: 'fill', source: `${id}-osm`, filter: ['==', ['geometry-type'], 'Polygon'],
            paint: { 'fill-color': colorByLayer('#ff8000') as never, 'fill-opacity': 0.25 } });
        addLayer({ id: `${id}-osm-line`, type: 'line', source: `${id}-osm`,
            filter: ['in', ['geometry-type'], ['literal', ['LineString', 'MultiLineString', 'Polygon']]],
            paint: { 'line-color': colorByLayer('#ffffff') as never, 'line-width': 1.5 } });
    }
    if (links.photos && !m.getSource(`${id}-photos`)) {
        m.addSource(`${id}-photos`, { type: 'geojson', data: links.photos, attribution: 'Photos © Mapillary contributors, CC BY-SA' });
        addLayer({ id: `${id}-photos`, type: 'circle', source: `${id}-photos`,
            paint: { 'circle-radius': 5, 'circle-color': '#06b6d4', 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 1 } }, false);
    }
    m.addSource(`${id}-area`, { type: 'geojson', data: links.area });
    addLayer({ id: `${id}-area`, type: 'line', source: `${id}-area`,
        paint: { 'line-color': '#06b6d4', 'line-width': 2, 'line-dasharray': [2, 2] } }, false);
}

export function hideJob(jobId: string): void {
    const m = map();
    const prefix = `${PREFIX}${jobId}`;
    for (const layer of [...(m.getStyle().layers ?? [])]) {
        if (layer.id.startsWith(prefix)) m.removeLayer(layer.id);
    }
    for (const source of Object.keys(m.getStyle().sources ?? {})) {
        if (source.startsWith(prefix)) m.removeSource(source);
    }
}

export function zoomTo(polygon: Polygon): void {
    const ring = polygon.coordinates[0];
    const lons = ring.map((p) => p[0]);
    const lats = ring.map((p) => p[1]);
    map().fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: 60 });
}

/** Everything this plugin ever put on the map. Safe when the map isn't loaded yet. */
export function removeAll(): void {
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
