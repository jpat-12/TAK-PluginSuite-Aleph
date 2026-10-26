/* eslint-disable */
// Aleph for TAK — CloudTAK server half (copied to <CloudTAK>/api/routes/plugin-aleph.ts).
//
// Relays the panel's JSON calls to the Aleph capture service with a *proxy* token that never
// leaves the server, and names the signed-in CloudTAK user per request (X-Aleph-User) so each
// user sees only their own captures. Map tiles, GeoJSON and package downloads don't pass through
// here: Aleph hands out short-lived signed URLs that the browser fetches directly.
//
// Configuration comes from ALEPH_URL / ALEPH_TOKEN, which cloudtak/install.sh merges into
// <CloudTAK>/api/.env (a JSON file CloudTAK loads at startup and git ignores) — so no core
// CloudTAK file is edited and infra-TAK's CloudTAK updates leave it in place.

import { Type } from '@sinclair/typebox';
import Schema from '@openaddresses/batch-schema';
import Err from '@openaddresses/batch-error';
import Auth from '../lib/auth.js';
import Config from '../lib/config.js';

const TIMEOUT_MS = 30_000;

function upstream(): { url: string; token: string } {
    const url = String(process.env.ALEPH_URL || '').replace(/\/+$/, '');
    const token = String(process.env.ALEPH_TOKEN || '');
    if (!url || !token) {
        throw new Err(503, null, 'Aleph is not configured on this CloudTAK server — run the Aleph installer with --cloudtak.');
    }
    return { url, token };
}

async function relay(user: string | null, method: string, path: string, body?: unknown): Promise<unknown> {
    const { url, token } = upstream();
    const headers: Record<string, string> = {};
    if (user !== null) {
        headers['Authorization'] = `Bearer ${token}`;
        headers['X-Aleph-User'] = user;
    }
    if (body !== undefined) headers['Content-Type'] = 'application/json';

    let response: Response;
    try {
        response = await fetch(`${url}/api/v1${path}`, {
            method,
            headers,
            body: body === undefined ? undefined : JSON.stringify(body),
            signal: AbortSignal.timeout(TIMEOUT_MS),
        });
    } catch (err) {
        throw new Err(502, err instanceof Error ? err : null, `Aleph capture service unreachable at ${url}`);
    }
    const text = await response.text();
    let data: any = {};
    try {
        data = text ? JSON.parse(text) : {};
    } catch {
        data = { error: text.slice(0, 200) };
    }
    if (!response.ok) {
        throw new Err(response.status, null, data && data.error ? String(data.error) : `Aleph returned HTTP ${response.status}`);
    }
    return data;
}

const JobParams = Type.Object({ jobid: Type.String({ pattern: '^j[0-9a-f]{12}$' }) });

export default async function router(schema: Schema, config: Config) {
    await schema.get('/plugin-aleph/info', {
        name: 'Aleph Info',
        group: 'PluginAleph',
        description: 'Capabilities of the connected Aleph capture service (layers, area cap, version)',
        res: Type.Any(),
    }, async (req, res) => {
        try {
            await Auth.as_user(config, req);
            res.json(await relay(null, 'GET', '/info'));
        } catch (err) {
            Err.respond(err, res);
        }
    });

    await schema.post('/plugin-aleph/estimate', {
        name: 'Aleph Estimate',
        group: 'PluginAleph',
        description: 'Size and time estimate for a capture, shown before submitting',
        body: Type.Any(),
        res: Type.Any(),
    }, async (req, res) => {
        try {
            const user = await Auth.as_user(config, req);
            res.json(await relay(user.email, 'POST', '/estimate', req.body));
        } catch (err) {
            Err.respond(err, res);
        }
    });

    await schema.get('/plugin-aleph/job', {
        name: 'Aleph List Captures',
        group: 'PluginAleph',
        description: "The calling user's captures, newest first",
        res: Type.Any(),
    }, async (req, res) => {
        try {
            const user = await Auth.as_user(config, req);
            res.json(await relay(user.email, 'GET', '/jobs'));
        } catch (err) {
            Err.respond(err, res);
        }
    });

    await schema.post('/plugin-aleph/job', {
        name: 'Aleph Create Capture',
        group: 'PluginAleph',
        description: 'Start a capture of an area',
        body: Type.Any(),
        res: Type.Any(),
    }, async (req, res) => {
        try {
            const user = await Auth.as_user(config, req);
            res.json(await relay(user.email, 'POST', '/jobs', req.body));
        } catch (err) {
            Err.respond(err, res);
        }
    });

    await schema.get('/plugin-aleph/job/:jobid', {
        name: 'Aleph Get Capture',
        group: 'PluginAleph',
        description: 'One capture: state, per-layer progress, and signed links once complete',
        params: JobParams,
        res: Type.Any(),
    }, async (req, res) => {
        try {
            const user = await Auth.as_user(config, req);
            res.json(await relay(user.email, 'GET', `/jobs/${req.params.jobid}`));
        } catch (err) {
            Err.respond(err, res);
        }
    });

    await schema.delete('/plugin-aleph/job/:jobid', {
        name: 'Aleph Delete Capture',
        group: 'PluginAleph',
        description: 'Cancel a running capture, or delete a finished one',
        params: JobParams,
        res: Type.Any(),
    }, async (req, res) => {
        try {
            const user = await Auth.as_user(config, req);
            res.json(await relay(user.email, 'DELETE', `/jobs/${req.params.jobid}`));
        } catch (err) {
            Err.respond(err, res);
        }
    });

    await schema.post('/plugin-aleph/job/:jobid/retry', {
        name: 'Aleph Retry Capture',
        group: 'PluginAleph',
        description: 'Re-run a capture; already-downloaded tiles are reused',
        params: JobParams,
        res: Type.Any(),
    }, async (req, res) => {
        try {
            const user = await Auth.as_user(config, req);
            res.json(await relay(user.email, 'POST', `/jobs/${req.params.jobid}/retry`));
        } catch (err) {
            Err.respond(err, res);
        }
    });

    await schema.get('/plugin-aleph/point', {
        name: 'Aleph Point Lookup',
        group: 'PluginAleph',
        description: 'Elevation, nearest address and nearby street-level photos for one location',
        query: Type.Object({
            lat: Type.Number({ minimum: -85, maximum: 85 }),
            lon: Type.Number({ minimum: -180, maximum: 180 }),
        }),
        res: Type.Any(),
    }, async (req, res) => {
        try {
            const user = await Auth.as_user(config, req);
            res.json(await relay(user.email, 'GET', `/point?lat=${req.query.lat}&lon=${req.query.lon}`));
        } catch (err) {
            Err.respond(err, res);
        }
    });
}
