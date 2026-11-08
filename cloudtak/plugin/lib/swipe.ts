// Swipe compare: a capture's own area becomes a slider. West of the divider shows the captured
// data (imagery + OSM + photos), east of it the live basemap; drag the handle (or the panel's
// range input) to see more of either — e.g. what the capture holds vs. what changed since NAIP flew.
//
// MapLibre can't clip a layer, so this is the maplibre-gl-compare technique: a second,
// non-interactive map holding only the capture's layers sits over the main canvas, follows its
// camera, and is CSS-clipped to the data side of the area. The main map keeps the area outline;
// its copies of the data layers are made transparent (not hidden, which would drop their
// attribution) until the compare stops. Everything here is removed by stopSwipe().
import * as mapgl from 'maplibre-gl';
import type { LayerSpecification, Map as MapLibreMap, StyleSpecification } from 'maplibre-gl';
import { pluginApi } from './plugin-api.ts';
import { addJobData, jobDataLayers, shownDatasets } from './map-layers.ts';
import type { Job } from './types.ts';

export interface SwipeState {
    jobId: string;
    fraction: number;                   // divider position, 0 = west edge (all basemap) … 1 = east edge (all capture)
}

const ACCENT = '#06b6d4';
const KEY_STEP = 0.05;
const HANDLE_MARGIN = 24;               // keep the handle this far inside the viewport
type PaintProperty = Parameters<MapLibreMap['setPaintProperty']>[1];
const OPACITY: Partial<Record<LayerSpecification['type'], PaintProperty[]>> = {
    raster: ['raster-opacity'], fill: ['fill-opacity'], line: ['line-opacity'],
    circle: ['circle-opacity', 'circle-stroke-opacity'],
};

interface Swipe extends SwipeState {
    bbox: [number, number, number, number];
    overlay: MapLibreMap;
    root: HTMLDivElement;
    clip: HTMLDivElement;
    divider: SVGLineElement;
    handle: HTMLDivElement;
    muted: { layer: string; prop: PaintProperty; value: Parameters<MapLibreMap['setPaintProperty']>[2] }[];
    detach: () => void;
    frame: number | null;
}

let active: Swipe | null = null;
const listeners = new Set<(state: SwipeState | null) => void>();

function map(): MapLibreMap {
    return pluginApi().map;
}

function notify(): void {
    const state = swipeState();
    for (const listener of listeners) listener(state);
}

export function swipeState(): SwipeState | null {
    return active ? { jobId: active.jobId, fraction: active.fraction } : null;
}

/** Follow the compare from the panel (it can outlive the panel). Returns the unsubscribe. */
export function onSwipeChange(listener: (state: SwipeState | null) => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
}

function areaBbox(job: Job): [number, number, number, number] {
    const ring = job.area.coordinates[0];
    const lons = ring.map((p) => p[0]);
    const lats = ring.map((p) => p[1]);
    return [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)];
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, css: string): HTMLElementTagNameMap[K] {
    const node = document.createElement(tag);
    node.style.cssText = css;
    return node;
}

function label(text: string, side: 'left' | 'right'): HTMLSpanElement {
    const node = el('span', `position:absolute;top:50%;${side === 'left' ? 'right' : 'left'}:40px;transform:translateY(-50%);`
        + 'padding:2px 6px;border-radius:4px;background:rgba(0,0,0,.65);color:#fff;font:600 11px/1.4 sans-serif;white-space:nowrap;');
    node.textContent = text;
    return node;
}

/**
 * The part of segment a→b inside the viewport (Liang–Barsky), as [u0, u1] along it, or null.
 * The handle sits at the middle of that part so it stays grabbable when the area is half off-screen.
 */
function visibleSpan(a: mapgl.Point, b: mapgl.Point, width: number, height: number): [number, number] | null {
    let u0 = 0;
    let u1 = 1;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const edges: [number, number][] = [
        [-dx, a.x - HANDLE_MARGIN], [dx, width - HANDLE_MARGIN - a.x],
        [-dy, a.y - HANDLE_MARGIN], [dy, height - HANDLE_MARGIN - a.y],
    ];
    for (const [p, q] of edges) {
        if (p === 0) {
            if (q < 0) return null;
            continue;
        }
        const r = q / p;
        if (p < 0) u0 = Math.max(u0, r);
        else u1 = Math.min(u1, r);
        if (u0 > u1) return null;
    }
    return [u0, u1];
}

function layout(): void {
    if (!active) return;
    active.frame = null;
    const m = map();
    const [west, south, east, north] = active.bbox;
    const x = west + (east - west) * active.fraction;
    const [nw, nx, sx, sw] = [[west, north], [x, north], [x, south], [west, south]]
        .map(([lon, lat]) => m.project([lon, lat]));
    active.clip.style.clipPath = `polygon(${[nw, nx, sx, sw].map((p) => `${p.x}px ${p.y}px`).join(', ')})`;
    active.divider.setAttribute('x1', String(nx.x));
    active.divider.setAttribute('y1', String(nx.y));
    active.divider.setAttribute('x2', String(sx.x));
    active.divider.setAttribute('y2', String(sx.y));
    const { clientWidth, clientHeight } = m.getContainer();
    const span = visibleSpan(nx, sx, clientWidth, clientHeight);
    active.handle.style.display = span ? 'flex' : 'none';
    active.handle.setAttribute('aria-valuenow', String(Math.round(active.fraction * 100)));
    if (span) {
        const u = (span[0] + span[1]) / 2;
        active.handle.style.left = `${nx.x + (sx.x - nx.x) * u}px`;
        active.handle.style.top = `${nx.y + (sx.y - nx.y) * u}px`;
    }
}

function scheduleLayout(): void {
    if (active && active.frame === null) active.frame = requestAnimationFrame(layout);
}

export function setSwipeFraction(fraction: number): void {
    if (!active || !Number.isFinite(fraction)) return;
    active.fraction = Math.min(1, Math.max(0, fraction));
    scheduleLayout();
    notify();
}

function overlayStyle(m: MapLibreMap): StyleSpecification {
    const style: StyleSpecification = { version: 8, sources: {}, layers: [] };
    const projection = m.getProjection();
    if (projection) style.projection = projection;          // globe if the user picked it
    // With 3D terrain on, the overlay must drape over the same surface or the two halves shear.
    const terrain = m.getTerrain();
    const terrainSource = terrain ? m.getStyle().sources?.[terrain.source] : undefined;
    if (terrain && terrainSource) {
        style.sources[terrain.source] = terrainSource;
        style.terrain = terrain;
    }
    return style;
}

/** Start comparing `job` (already shown on the map) against the basemap. Replaces any running compare. */
export function startSwipe(job: Job, imagerySource?: string, fraction = 0.5): void {
    stopSwipe();
    const m = map();
    const container = m.getContainer();

    const root = el('div', 'position:absolute;inset:0;pointer-events:none;overflow:hidden;');
    root.className = 'plugin-aleph-swipe';
    const clip = el('div', 'position:absolute;inset:0;pointer-events:none;');
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('style', 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;overflow:visible;');
    const divider = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    divider.setAttribute('stroke', ACCENT);
    divider.setAttribute('stroke-width', '3');
    svg.appendChild(divider);
    const handle = el('div', 'position:absolute;width:32px;height:32px;margin:-16px 0 0 -16px;border-radius:50%;'
        + `background:#fff;border:3px solid ${ACCENT};box-shadow:0 1px 4px rgba(0,0,0,.5);cursor:ew-resize;`
        + 'pointer-events:auto;touch-action:none;display:flex;align-items:center;justify-content:center;'
        + `color:${ACCENT};user-select:none;`);
    handle.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" '
        + 'stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l-6 6 6 6M15 6l6 6-6 6"/></svg>';
    handle.tabIndex = 0;
    handle.setAttribute('role', 'slider');
    handle.setAttribute('aria-label', 'Capture / base map divider');
    handle.setAttribute('aria-valuemin', '0');
    handle.setAttribute('aria-valuemax', '100');
    handle.title = 'Drag: left of the line is the capture, right of it the base map';
    handle.append(label('Capture', 'left'), label('Base map', 'right'));
    root.append(clip, svg, handle);
    // Right after the canvas so MapLibre's controls (later siblings) stay on top of it.
    container.insertBefore(root, m.getCanvasContainer().nextSibling);

    const overlay = new mapgl.Map({
        container: clip,
        style: overlayStyle(m),
        interactive: false,
        attributionControl: false,
        fadeDuration: 0,
        renderWorldCopies: m.getRenderWorldCopies(),
        minZoom: m.getMinZoom(), maxZoom: m.getMaxZoom(),
        minPitch: m.getMinPitch(), maxPitch: m.getMaxPitch(),
        center: m.getCenter(), zoom: m.getZoom(), bearing: m.getBearing(), pitch: m.getPitch(), roll: m.getRoll(),
    });
    const datasets = shownDatasets(job.id);           // the overlay shows what the panel has switched on
    overlay.once('load', () => addJobData(overlay, job, imagerySource, datasets));
    overlay.on('error', (e) => console.warn('[plugin-aleph] compare overlay:', e.error));

    // Transparent, not hidden: hidden sources drop out of the attribution control.
    const muted: Swipe['muted'] = [];
    for (const layer of jobDataLayers(job.id)) {
        for (const prop of OPACITY[layer.type] ?? []) {
            muted.push({ layer: layer.id, prop, value: m.getPaintProperty(layer.id, prop) });
            m.setPaintProperty(layer.id, prop, 0);
        }
    }

    const sync = () => {
        overlay.jumpTo({
            center: m.getCenter(), zoom: m.getZoom(), bearing: m.getBearing(), pitch: m.getPitch(), roll: m.getRoll(),
            padding: m.getPadding(),
        });
        scheduleLayout();
    };
    const resize = () => {
        overlay.resize();
        sync();
    };

    let dragging = false;
    const bbox = areaBbox(job);
    const onDown = (e: PointerEvent) => {
        e.preventDefault();
        e.stopPropagation();
        dragging = true;
        handle.setPointerCapture(e.pointerId);
    };
    const onDrag = (e: PointerEvent) => {
        if (!dragging) return;
        e.stopPropagation();
        const rect = container.getBoundingClientRect();
        // The divider is a meridian, so the pointer's longitude places it at any bearing or pitch.
        const lon = m.unproject([e.clientX - rect.left, e.clientY - rect.top]).lng;
        setSwipeFraction((lon - bbox[0]) / (bbox[2] - bbox[0]));
    };
    const onUp = (e: PointerEvent) => {
        dragging = false;
        if (handle.hasPointerCapture(e.pointerId)) handle.releasePointerCapture(e.pointerId);
    };
    const onKey = (e: KeyboardEvent) => {
        if (!active) return;
        const step = { ArrowLeft: -KEY_STEP, ArrowDown: -KEY_STEP, ArrowRight: KEY_STEP, ArrowUp: KEY_STEP }[e.key];
        const jump = { Home: 0, End: 1 }[e.key];
        if (step === undefined && jump === undefined) return;
        e.preventDefault();
        setSwipeFraction(jump ?? active.fraction + (step ?? 0));
    };
    handle.addEventListener('pointerdown', onDown);
    handle.addEventListener('pointermove', onDrag);
    handle.addEventListener('pointerup', onUp);
    handle.addEventListener('pointercancel', onUp);
    handle.addEventListener('keydown', onKey);
    m.on('move', sync);
    m.on('resize', resize);

    active = {
        jobId: job.id, fraction: Math.min(1, Math.max(0, fraction)), bbox, overlay, root, clip, divider, handle, muted, frame: null,
        detach: () => {
            m.off('move', sync);
            m.off('resize', resize);
        },
    };
    sync();
    notify();
}

/** Re-request a source's tiles on the compare overlay too (map-layers' tile reload). */
export function refreshSwipeSource(sourceId: string): void {
    if (active?.overlay.getSource(sourceId)) active.overlay.refreshTiles(sourceId);
}

/** End the compare (only if it's `jobId`'s, when given) and put the main map's layers back. */
export function stopSwipe(jobId?: string): void {
    if (!active || (jobId !== undefined && active.jobId !== jobId)) return;
    const swipe = active;
    active = null;
    if (swipe.frame !== null) cancelAnimationFrame(swipe.frame);
    swipe.detach();
    try {
        const m = map();
        for (const { layer, prop, value } of swipe.muted) {
            if (m.getLayer(layer)) m.setPaintProperty(layer, prop, value);
        }
    } catch {
        /* map already torn down — nothing to restore */
    }
    swipe.overlay.remove();
    swipe.root.remove();
    notify();
}
