// Calls to this plugin's server half (api/routes/plugin-aleph.ts), which relays them to the
// Aleph capture service with a server-side token.
//
// Internal reach-in (AGENTS.md §4): `std` is CloudTAK's authenticated fetch. The public plugin
// API has no HTTP client, and std attaches the user's CloudTAK token for us. Re-verify this
// import path on every CloudTAK upgrade.
import { std } from '../../../src/std.ts';
import type { AlephInfo, Estimate, Job, LayerName, Polygon, PointResult } from './types.ts';

// The newest Aleph API major this plugin speaks; refuse others instead of failing mid-capture.
export const SUPPORTED_API = 1;

export interface CaptureRequest {
    area: Polygon;
    layers: LayerName[];
    name?: string;
    options?: { imagery_zoom?: number; dted_level?: 1 | 2 };
}

export async function info(): Promise<AlephInfo> {
    return await std('/api/plugin-aleph/info') as AlephInfo;
}

export async function estimate(request: CaptureRequest): Promise<Estimate> {
    return await std('/api/plugin-aleph/estimate', { method: 'POST', body: request }) as Estimate;
}

export async function listJobs(): Promise<Job[]> {
    const result = await std('/api/plugin-aleph/job') as { jobs?: Job[] };
    return Array.isArray(result?.jobs) ? result.jobs : [];
}

export async function createJob(request: CaptureRequest): Promise<Job> {
    return await std('/api/plugin-aleph/job', { method: 'POST', body: request }) as Job;
}

export async function deleteJob(id: string): Promise<void> {
    await std(`/api/plugin-aleph/job/${id}`, { method: 'DELETE' });
}

export async function retryJob(id: string): Promise<Job> {
    return await std(`/api/plugin-aleph/job/${id}/retry`, { method: 'POST' }) as Job;
}

export async function point(lat: number, lon: number): Promise<PointResult> {
    return await std(`/api/plugin-aleph/point?lat=${lat}&lon=${lon}`) as PointResult;
}
