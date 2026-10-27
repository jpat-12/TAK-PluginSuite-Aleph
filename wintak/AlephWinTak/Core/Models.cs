using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace AlephWinTak.Core
{
    /// <summary>
    /// Typed views of the Aleph API's JSON (docs/API.md), parsed once at the boundary. Optional
    /// fields default instead of throwing, so a newer server adding fields can't break an older
    /// plugin; the API major version is what guards incompatible changes.
    /// </summary>
    public static class Api
    {
        /// <summary>Highest Aleph API major this plugin speaks.</summary>
        public const int SupportedApi = 1;
    }

    public sealed class ServerInfo
    {
        public string Version { get; private set; }
        public int ApiVersion { get; private set; }
        public IReadOnlyList<string> Layers { get; private set; }
        public double MaxAreaKm2 { get; private set; }
        public string ImageryName { get; private set; }
        public int ImageryMaxZoom { get; private set; }
        public int DefaultZoom { get; private set; }
        public int TtlHours { get; private set; }

        public bool Compatible => ApiVersion == Api.SupportedApi;

        public static ServerInfo Parse(JObject o)
        {
            var imagery = o["imagery"] as JObject;
            return new ServerInfo
            {
                Version = (string)o["version"] ?? "?",
                ApiVersion = (int?)o["api"] ?? 0,
                Layers = (o["layers"] as JArray)?.Select(t => (string)t).ToList() ?? new List<string>(),
                MaxAreaKm2 = (double?)o["max_area_km2"] ?? 0,
                ImageryName = (string)imagery?["name"],
                ImageryMaxZoom = (int?)imagery?["max_zoom"] ?? 18,
                DefaultZoom = (int?)o["default_imagery_zoom"] ?? 17,
                TtlHours = (int?)o["job_ttl_hours"] ?? 72,
            };
        }
    }

    public sealed class Estimate
    {
        public double AreaKm2 { get; private set; }
        public long Bytes { get; private set; }
        public long Seconds { get; private set; }
        public bool Allowed { get; private set; }

        public static Estimate Parse(JObject o) => new Estimate
        {
            AreaKm2 = (double?)o["area_km2"] ?? 0,
            Bytes = (long?)o["bytes"] ?? 0,
            Seconds = (long?)o["seconds"] ?? 0,
            Allowed = (bool?)o["allowed"] ?? false,
        };
    }

    public sealed class Job
    {
        public string Id { get; private set; }
        public string Name { get; private set; }
        public string State { get; private set; }
        public double AreaKm2 { get; private set; }
        public IReadOnlyList<string> Layers { get; private set; }
        public double Percent { get; private set; }
        public string Phase { get; private set; }
        public IReadOnlyList<string> Warnings { get; private set; }
        public IReadOnlyList<string> LayerErrors { get; private set; }
        public string Error { get; private set; }
        public string PackageFile { get; private set; }
        public long PackageBytes { get; private set; }
        public string PackageSha256 { get; private set; }

        public bool IsActive => State == "queued" || State == "running";
        public bool IsComplete => State == "complete" && PackageFile != null;
        public bool CanRetry => State == "failed" || State == "cancelled" || LayerErrors.Count > 0;

        public static Job Parse(JObject o)
        {
            string phase = null;
            var errors = new List<string>();
            if (o["progress"] is JObject progress)
            {
                foreach (var entry in progress.Properties())
                {
                    if (!(entry.Value is JObject p)) continue;
                    var state = (string)p["state"];
                    if (state == "running")
                    {
                        var label = (string)p["phase"] ?? entry.Name;
                        phase = p["total"]?.Type == JTokenType.Integer ? $"{label} {(int?)p["done"] ?? 0}/{(int)p["total"]}" : label;
                    }
                    else if (state == "failed")
                    {
                        errors.Add($"{entry.Name}: {(string)p["error"] ?? "failed"}");
                    }
                }
            }
            var pkg = o["package"] as JObject;
            return new Job
            {
                Id = (string)o["id"],
                Name = (string)o["name"] ?? (string)o["id"],
                State = (string)o["state"] ?? "queued",
                AreaKm2 = (double?)o["area_km2"] ?? 0,
                Layers = (o["layers"] as JArray)?.Select(t => (string)t).ToList() ?? new List<string>(),
                Percent = (double?)o["percent"] ?? 0,
                Phase = phase,
                Warnings = (o["warnings"] as JArray)?.Select(t => (string)t).ToList() ?? new List<string>(),
                LayerErrors = errors,
                Error = o["error"]?.Type == JTokenType.String ? (string)o["error"] : null,
                PackageFile = (string)pkg?["filename"],
                PackageBytes = (long?)pkg?["bytes"] ?? 0,
                PackageSha256 = (string)pkg?["sha256"],
            };
        }

        public static List<Job> ParseList(JObject o) =>
            (o["jobs"] as JArray)?.OfType<JObject>().Select(Parse).ToList() ?? new List<Job>();
    }
}
