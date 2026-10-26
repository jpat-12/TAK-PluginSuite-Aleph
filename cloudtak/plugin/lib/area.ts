// Where a capture area comes from: the current map view, a rectangle drawn on the map, or an
// existing CloudTAK feature (a drawn polygon, an LPB search ring, an ICS 204 segment...).
import type { DBFeature } from '@tak-ps/cloudtak';
import type { Polygon } from './types.ts';
import { pluginApi } from './plugin-api.ts';

const EARTH_RADIUS_M = 6_371_008.8;

export function bboxPolygon(west: number, south: number, east: number, north: number): Polygon {
    return {
        type: 'Polygon',
        coordinates: [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
    };
}

export function mapViewArea(): Polygon {
    const bounds = pluginApi().map.getBounds();
    return bboxPolygon(bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth());
}

/** Approximate ground area (km²) on a local equirectangular plane — fine at capture scale. */
export function areaKm2(polygon: Polygon): number {
    const ring = polygon.coordinates[0] ?? [];
    if (ring.length < 4) return 0;
    const lat0 = ring.reduce((sum, p) => sum + p[1], 0) / ring.length * Math.PI / 180;
    let twice = 0;
    for (let i = 0; i < ring.length - 1; i++) {
        const [x1, y1] = ring[i];
        const [x2, y2] = ring[i + 1];
        twice += (x1 * Math.cos(lat0)) * y2 - (x2 * Math.cos(lat0)) * y1;
    }
    const degree = Math.PI / 180 * EARTH_RADIUS_M;
    return Math.abs(twice) / 2 * degree * degree / 1e6;
}

export interface AreaCandidate {
    id: string;
    label: string;
    polygon: Polygon;
}

/** Polygon-shaped features already on the map, so a team can capture an existing search area. */
export async function featureAreas(): Promise<AreaCandidate[]> {
    const features: DBFeature[] = await pluginApi().feature.list({
        filter: (f) => f.geometry?.type === 'Polygon',
    });
    return features.map((f) => {
        const props = (f.properties ?? {}) as Record<string, unknown>;
        const name = String(props.callsign ?? props.name ?? f.id);
        const geometry = f.geometry as unknown as Polygon;
        return { id: f.id, label: name, polygon: { type: 'Polygon' as const, coordinates: [geometry.coordinates[0]] } };
    }).sort((a, b) => a.label.localeCompare(b.label));
}

export function centroid(polygon: Polygon): [number, number] {
    const ring = polygon.coordinates[0].slice(0, -1);
    const lon = ring.reduce((s, p) => s + p[0], 0) / ring.length;
    const lat = ring.reduce((s, p) => s + p[1], 0) / ring.length;
    return [lon, lat];
}
