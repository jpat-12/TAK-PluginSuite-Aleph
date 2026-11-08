// Shapes of the Aleph capture service API (/api/v1 — docs/API.md in this repo). The CloudTAK
// server half relays them unchanged, so these are the one place the web half learns them.

export type LayerName = 'imagery' | 'elevation' | 'osm' | 'photos';
export type JobState = 'queued' | 'running' | 'complete' | 'failed' | 'cancelled';

export interface Polygon {
    type: 'Polygon';
    coordinates: number[][][];          // [lon, lat], first ring is the outline
}

export interface AlephInfo {
    service: string;
    version: string;
    api: number;
    layers: LayerName[];
    max_area_km2: number;
    imagery: { name: string; coverage: string; max_zoom: number } | null;     // the default source
    imagery_sources?: ImagerySource[];                                          // service 0.1.4+
    default_imagery_zoom: number;
    dted_level: number;
    job_ttl_hours: number;
}

export interface ImagerySource {
    id: string;
    default: boolean;
    name: string;
    coverage: string;
    max_zoom: number;
    resolution: string;
    updated: string;
    licence: string;
    description: string;
}

export interface Estimate {
    area_km2: number;
    bytes: number;
    seconds: number;
    allowed: boolean;
    max_area_km2: number;
    layers: Partial<Record<LayerName, { bytes: number; seconds: number; tiles?: number; note?: string; source?: string }>>;
}

export interface LayerProgress {
    state: 'queued' | 'running' | 'complete' | 'failed';
    phase: string | null;
    done: number;
    total: number | null;
    error?: string | null;
    // Set when the layer completes. failed_tiles: imagery tiles still missing after the automatic retry.
    stats?: { failed_tiles?: number; [key: string]: unknown };
}

export interface JobLinks {
    package: string;
    area: string;
    tiles?: string;                     // XYZ template with {z}/{x}/{y}, signed
    tiles_info?: { min_zoom: number; max_zoom: number; bounds: [number, number, number, number] };
    osm?: string;
    photos?: string;
    photo_image?: string;               // template with {id}
}

export interface Job {
    id: string;
    name: string;
    owner: string;
    state: JobState;
    created_at: string;
    expires_at: string;
    area: Polygon;
    area_km2: number;
    layers: LayerName[];
    progress: Record<LayerName, LayerProgress>;
    percent: number;
    warnings: string[];
    error: string | null;
    package: { filename: string; bytes: number; sha256: string } | null;
    links?: JobLinks;
}

export interface PointResult {
    lat: number;
    lon: number;
    elevation_m: number | null;
    address: { label: string; distance_m?: number } | null;
    // Nearest house address; `exact` false = only the street is known there. Service 0.1.4+.
    street_address?: { label: string; exact: boolean; distance_m?: number | null } | null;
    photos: Array<{ id: string; distance_m: number; thumb_url: string | null; image_url: string | null; captured_at: number | null }> | null;
    errors: Record<string, string>;
    attribution: string[];
}
