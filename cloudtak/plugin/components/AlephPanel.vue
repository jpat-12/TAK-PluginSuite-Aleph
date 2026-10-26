<template>
    <MenuTemplate name='Aleph Capture'>
        <div class='px-2 py-2'>
            <div
                v-if='error'
                class='alert alert-danger py-2 mb-2'
            >
                {{ error }}
            </div>
            <div
                v-if='!info && !error'
                class='text-secondary small'
            >
                Connecting to the capture service…
            </div>

            <template v-if='info'>
                <!-- 1. Area -->
                <div class='subheader mb-1'>
                    1 · Area
                </div>
                <div class='btn-list mb-2'>
                    <button
                        class='btn btn-sm'
                        @click='useMapView'
                    >
                        <IconViewfinder :size='16' />&nbsp;Map view
                    </button>
                    <button
                        class='btn btn-sm'
                        :class='{ "btn-primary": drawing }'
                        @click='startDrawing'
                    >
                        <IconSquare :size='16' />&nbsp;{{ drawing ? "Click 2 corners…" : "Draw box" }}
                    </button>
                </div>
                <select
                    v-if='candidates.length'
                    v-model='candidateId'
                    class='form-select form-select-sm mb-2'
                    @change='useCandidate'
                >
                    <option value=''>
                        Or use a shape on the map…
                    </option>
                    <option
                        v-for='c in candidates'
                        :key='c.id'
                        :value='c.id'
                    >
                        {{ c.label }}
                    </option>
                </select>
                <div
                    v-if='area'
                    class='small mb-2'
                    :class='areaKm > info.max_area_km2 ? "text-danger" : "text-secondary"'
                >
                    {{ areaKm.toFixed(2) }} km² selected (limit {{ info.max_area_km2 }} km²)
                </div>

                <!-- 2. Layers -->
                <div class='subheader mb-1 mt-3'>
                    2 · Layers
                </div>
                <label
                    v-for='layer in info.layers'
                    :key='layer'
                    class='form-check mb-1'
                >
                    <input
                        v-model='layers'
                        class='form-check-input'
                        type='checkbox'
                        :value='layer'
                        @change='refreshEstimate'
                    >
                    <span class='form-check-label'>{{ LAYER_LABELS[layer] }}</span>
                </label>
                <div
                    v-if='layers.includes("imagery") && info.imagery'
                    class='d-flex align-items-center gap-2 small mb-2'
                >
                    <span class='text-secondary'>Detail</span>
                    <select
                        v-model.number='zoom'
                        class='form-select form-select-sm w-auto'
                        @change='refreshEstimate'
                    >
                        <option
                            v-for='z in zoomChoices'
                            :key='z'
                            :value='z'
                        >
                            z{{ z }} · ~{{ resolution(z) }} m
                        </option>
                    </select>
                    <span class='text-secondary'>{{ info.imagery.name }}</span>
                </div>

                <!-- 3. Estimate + submit -->
                <div class='subheader mb-1 mt-3'>
                    3 · Capture
                </div>
                <input
                    v-model='name'
                    class='form-control form-control-sm mb-2'
                    placeholder='Name (e.g. Lake Springfield sector 3)'
                    maxlength='40'
                >
                <div
                    v-if='estimateResult'
                    class='small text-secondary mb-2'
                >
                    ≈ {{ mb(estimateResult.bytes) }} package · ~{{ minutes(estimateResult.seconds) }}
                    <span
                        v-if='!estimateResult.allowed'
                        class='text-danger'
                    > — area too large</span>
                </div>
                <button
                    class='btn btn-primary w-100'
                    :disabled='!canSubmit'
                    @click='submit'
                >
                    <IconDownload :size='16' />&nbsp;Capture area
                </button>

                <!-- Captures -->
                <div class='subheader mb-1 mt-4 d-flex align-items-center'>
                    Captures
                    <span class='ms-auto text-secondary'>kept {{ info.job_ttl_hours }} h</span>
                </div>
                <div
                    v-if='!jobs.length'
                    class='text-secondary small'
                >
                    None yet.
                </div>
                <div
                    v-for='job in jobs'
                    :key='job.id'
                    class='card card-sm mb-2'
                >
                    <div class='card-body p-2'>
                        <div class='d-flex align-items-center'>
                            <strong
                                class='text-truncate'
                                :title='job.name'
                            >{{ job.name }}</strong>
                            <span
                                class='badge ms-auto'
                                :class='STATE_BADGE[job.state]'
                            >{{ job.state }}</span>
                        </div>
                        <div class='small text-secondary'>
                            {{ job.area_km2 }} km² · {{ job.layers.join(", ") }}
                        </div>
                        <div
                            v-if='job.state === "running" || job.state === "queued"'
                            class='progress progress-sm my-1'
                        >
                            <div
                                class='progress-bar'
                                :style='{ width: `${job.percent}%` }'
                            />
                        </div>
                        <div
                            v-if='job.state === "running"'
                            class='small text-secondary'
                        >
                            {{ phase(job) }}
                        </div>
                        <div
                            v-for='(warning, i) in job.warnings'
                            :key='i'
                            class='small text-warning'
                        >
                            {{ warning }}
                        </div>
                        <div
                            v-for='failure in failedLayers(job)'
                            :key='failure.layer'
                            class='small text-danger'
                        >
                            {{ LAYER_LABELS[failure.layer] }}: {{ failure.error }}
                        </div>
                        <div
                            v-if='job.error'
                            class='small text-danger'
                        >
                            {{ job.error }}
                        </div>
                        <div class='btn-list mt-1'>
                            <template v-if='job.state === "complete" && job.links'>
                                <button
                                    class='btn btn-sm'
                                    @click='toggleOnMap(job)'
                                >
                                    <IconMap :size='14' />&nbsp;{{ shown[job.id] ? "Hide" : "Show" }}
                                </button>
                                <a
                                    class='btn btn-sm'
                                    :href='job.links.package'
                                    :title='`TAK data package for ATAK/WinTAK import (${mb(job.package?.bytes ?? 0)})`'
                                >
                                    <IconPackage :size='14' />&nbsp;{{ mb(job.package?.bytes ?? 0) }}
                                </a>
                            </template>
                            <button
                                v-if='["failed", "cancelled"].includes(job.state) || failedLayers(job).length'
                                class='btn btn-sm'
                                @click='retry(job)'
                            >
                                <IconRefresh :size='14' />&nbsp;Retry
                            </button>
                            <button
                                class='btn btn-sm btn-ghost-danger'
                                @click='remove(job)'
                            >
                                <IconTrash :size='14' />
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Point mode -->
                <div class='subheader mb-1 mt-4'>
                    Point lookup
                </div>
                <button
                    class='btn btn-sm w-100 mb-2'
                    :class='{ "btn-primary": picking }'
                    @click='lookupPoint'
                >
                    <IconMapPin :size='16' />&nbsp;{{ picking ? "Click the map…" : "Tap a spot: elevation, address, photos" }}
                </button>
                <div
                    v-if='pointResult'
                    class='card card-sm'
                >
                    <div class='card-body p-2 small'>
                        <div>{{ pointResult.lat.toFixed(5) }}, {{ pointResult.lon.toFixed(5) }}</div>
                        <div v-if='pointResult.elevation_m !== null'>
                            Elevation <strong>{{ pointResult.elevation_m }} m</strong>
                            ({{ Math.round(pointResult.elevation_m * 3.28084) }} ft)
                        </div>
                        <div v-if='pointResult.address'>
                            Near {{ pointResult.address.label }}
                        </div>
                        <div
                            v-if='pointResult.photos && pointResult.photos.length'
                            class='d-flex gap-1 mt-1 flex-wrap'
                        >
                            <a
                                v-for='photo in pointResult.photos'
                                :key='photo.id'
                                :href='photo.image_url ?? undefined'
                                target='_blank'
                                rel='noopener'
                            >
                                <img
                                    v-if='photo.thumb_url'
                                    :src='photo.thumb_url'
                                    :title='`${photo.distance_m} m away`'
                                    style='width:72px;height:54px;object-fit:cover;border-radius:4px'
                                >
                            </a>
                        </div>
                        <div
                            v-for='(message, part) in pointResult.errors'
                            :key='part'
                            class='text-warning'
                        >
                            {{ part }} unavailable: {{ message }}
                        </div>
                    </div>
                </div>
                <div class='small text-secondary mt-3'>
                    Aleph {{ info.version }} · open data only: {{ info.imagery?.name ?? "no imagery" }}, AWS Terrain Tiles,
                    © OpenStreetMap contributors{{ info.layers.includes("photos") ? ", Mapillary (CC BY-SA)" : "" }}.
                </div>
            </template>
        </div>
    </MenuTemplate>
</template>

<script setup lang='ts'>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue';
import {
    IconDownload, IconMap, IconMapPin, IconPackage, IconRefresh, IconSquare, IconTrash, IconViewfinder,
} from '@tabler/icons-vue';
// Internal reach-in: CloudTAK's standard menu-panel chrome (header, back button), so the panel
// looks native. Re-verify the path on CloudTAK upgrades (AGENTS.md §4).
import MenuTemplate from '../../../src/components/CloudTAK/util/MenuTemplate.vue';
import * as aleph from '../lib/client.ts';
import { areaKm2, featureAreas, mapViewArea, type AreaCandidate } from '../lib/area.ts';
import { cancelInteraction, drawRectangle, hideJob, isShown, pickPoint, showDraft, showJob, zoomTo } from '../lib/map-layers.ts';
import type { AlephInfo, Estimate, Job, LayerName, LayerProgress, Polygon, PointResult } from '../lib/types.ts';

const LAYER_LABELS: Record<LayerName, string> = {
    imagery: 'Imagery (MBTiles)',
    elevation: 'Elevation (DTED + GeoTIFF)',
    osm: 'Roads, trails, buildings, water (KMZ)',
    photos: 'Street-level photos',
};
const STATE_BADGE: Record<string, string> = {
    queued: 'bg-secondary-lt', running: 'bg-blue-lt', complete: 'bg-green-lt', failed: 'bg-red-lt', cancelled: 'bg-secondary-lt',
};
const POLL_MS = 3000;

const info = ref<AlephInfo | null>(null);
const error = ref<string | null>(null);
const area = ref<Polygon | null>(null);
const candidates = ref<AreaCandidate[]>([]);
const candidateId = ref('');
const layers = ref<LayerName[]>([]);
const zoom = ref(17);
const name = ref('');
const estimateResult = ref<Estimate | null>(null);
const jobs = ref<Job[]>([]);
const shown = reactive<Record<string, boolean>>({});
const drawing = ref(false);
const picking = ref(false);
const submitting = ref(false);
const pointResult = ref<PointResult | null>(null);
let timer: ReturnType<typeof setInterval> | null = null;

const areaKm = computed(() => (area.value ? areaKm2(area.value) : 0));
const zoomChoices = computed(() => {
    const max = info.value?.imagery?.max_zoom ?? 18;
    return [15, 16, 17, 18, 19].filter((z) => z <= max);
});
const canSubmit = computed(() => Boolean(area.value && layers.value.length && !submitting.value
    && (!estimateResult.value || estimateResult.value.allowed)));

function errorText(err: unknown): string {
    return err instanceof Error ? err.message : String(err);
}

function mb(bytes: number): string {
    return bytes >= 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : `${Math.max(0.1, bytes / 1e6).toFixed(1)} MB`;
}

function minutes(seconds: number): string {
    return seconds < 90 ? `${Math.max(1, Math.round(seconds))} s` : `${Math.round(seconds / 60)} min`;
}

function resolution(z: number): string {
    const lat = area.value ? area.value.coordinates[0][0][1] : 40;
    return (156543.03 * Math.cos(lat * Math.PI / 180) / 2 ** z).toFixed(1);
}

function phase(job: Job): string {
    const running = Object.entries(job.progress).find(([, p]) => p.state === 'running');
    if (!running) return 'Packaging…';
    const [, p] = running;
    return p.total ? `${p.phase ?? running[0]} ${p.done}/${p.total}` : (p.phase ?? running[0]);
}

function failedLayers(job: Job): { layer: LayerName; error: string }[] {
    return (Object.entries(job.progress) as [LayerName, LayerProgress][])
        .filter(([, p]) => p.state === 'failed')
        .map(([layer, p]) => ({ layer, error: p.error ?? 'failed' }));
}

function setArea(polygon: Polygon): void {
    area.value = polygon;
    showDraft(polygon);
    void refreshEstimate();
}

function useMapView(): void {
    candidateId.value = '';
    setArea(mapViewArea());
}

async function startDrawing(): Promise<void> {
    if (drawing.value) {
        cancelInteraction();
        return;
    }
    drawing.value = true;
    picking.value = false;
    const polygon = await drawRectangle();
    drawing.value = false;
    if (polygon) {
        candidateId.value = '';
        setArea(polygon);
    }
}

function useCandidate(): void {
    const chosen = candidates.value.find((c) => c.id === candidateId.value);
    if (chosen) {
        setArea(chosen.polygon);
        zoomTo(chosen.polygon);
    }
}

function request(): aleph.CaptureRequest | null {
    if (!area.value || !layers.value.length) return null;
    return { area: area.value, layers: layers.value, name: name.value || undefined, options: { imagery_zoom: zoom.value } };
}

async function refreshEstimate(): Promise<void> {
    const body = request();
    if (!body) {
        estimateResult.value = null;
        return;
    }
    try {
        estimateResult.value = await aleph.estimate(body);
        error.value = null;
    } catch (err) {
        estimateResult.value = null;
        error.value = errorText(err);
    }
}

async function refreshJobs(): Promise<void> {
    try {
        jobs.value = await aleph.listJobs();
        for (const job of jobs.value) shown[job.id] = isShown(job);
    } catch (err) {
        error.value = errorText(err);
    }
}

async function submit(): Promise<void> {
    const body = request();
    if (!body) return;
    submitting.value = true;
    try {
        await aleph.createJob(body);
        name.value = '';
        await refreshJobs();
    } catch (err) {
        error.value = errorText(err);
    } finally {
        submitting.value = false;
    }
}

function toggleOnMap(job: Job): void {
    if (shown[job.id]) {
        hideJob(job.id);
        shown[job.id] = false;
    } else {
        showJob(job, info.value?.imagery?.name);
        shown[job.id] = true;
        zoomTo(job.area);
    }
}

async function retry(job: Job): Promise<void> {
    try {
        await aleph.retryJob(job.id);
        await refreshJobs();
    } catch (err) {
        error.value = errorText(err);
    }
}

async function remove(job: Job): Promise<void> {
    try {
        hideJob(job.id);
        await aleph.deleteJob(job.id);
        await refreshJobs();
    } catch (err) {
        error.value = errorText(err);
    }
}

async function lookupPoint(): Promise<void> {
    if (picking.value) {
        cancelInteraction();
        return;
    }
    picking.value = true;
    drawing.value = false;
    const spot = await pickPoint();
    picking.value = false;
    if (!spot) return;
    try {
        pointResult.value = await aleph.point(spot[1], spot[0]);
    } catch (err) {
        error.value = errorText(err);
    }
}

onMounted(async () => {
    try {
        const result = await aleph.info();
        if (Math.floor(result.api) !== aleph.SUPPORTED_API) {
            error.value = `Aleph service speaks API v${result.api}; this plugin needs v${aleph.SUPPORTED_API}. Update one of them.`;
            return;
        }
        info.value = result;
        layers.value = result.layers.filter((l) => l !== 'photos');
        zoom.value = result.default_imagery_zoom;
        candidates.value = await featureAreas();
    } catch (err) {
        error.value = errorText(err);
        return;
    }
    await refreshJobs();
    timer = setInterval(() => {
        if (jobs.value.some((j) => j.state === 'queued' || j.state === 'running')) void refreshJobs();
    }, POLL_MS);
});

onUnmounted(() => {
    if (timer) clearInterval(timer);
    cancelInteraction();
    showDraft(null);
});
</script>
