using System.Collections.Generic;
using System.Globalization;
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
        public int DtedLevel { get; private set; }
        /// <summary>Imagery a capture may pick (service 0.1.4+); empty on older services, which use their default.</summary>
        public IReadOnlyList<ImagerySource> ImagerySources { get; private set; }

        public bool Compatible => ApiVersion == Api.SupportedApi;

        /// <summary>The server's default source, or null when it doesn't list sources.</summary>
        public ImagerySource DefaultSource => ImagerySources.FirstOrDefault(s => s.IsDefault) ?? ImagerySources.FirstOrDefault();

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
                DtedLevel = (int?)o["dted_level"] ?? 2,
                ImagerySources = (o["imagery_sources"] as JArray)?.OfType<JObject>()
                    .Where(s => !string.IsNullOrEmpty((string)s["id"])).Select(ImagerySource.Parse).ToList()
                    ?? new List<ImagerySource>(),
            };
        }
    }

    /// <summary>One choosable imagery source (docs/API.md, info.imagery_sources).</summary>
    public sealed class ImagerySource
    {
        public string Id { get; private set; }
        public string Name { get; private set; }
        public string Description { get; private set; }
        public string Resolution { get; private set; }
        public string Coverage { get; private set; }
        public string Updated { get; private set; }
        public string Licence { get; private set; }
        public int MaxZoom { get; private set; }
        public bool IsDefault { get; private set; }

        /// <summary>"USGS NAIP aerial · 0.6–1 m" — the picker's label.</summary>
        public string Label => Resolution.Length == 0 ? Name : Name + " · " + Resolution;

        /// <summary>Description plus "coverage · updated · licence", for the line under the picker.</summary>
        public string Details
        {
            get
            {
                var facts = string.Join(" · ", new[] { Coverage, Updated, Licence }.Where(p => p.Length > 0));
                if (Description.Length == 0) return facts;
                return facts.Length == 0 ? Description : Description + "\n" + facts;
            }
        }

        public static ImagerySource Parse(JObject o) => new ImagerySource
        {
            Id = (string)o["id"],
            Name = (string)o["name"] ?? (string)o["id"],
            Description = (string)o["description"] ?? "",
            Resolution = (string)o["resolution"] ?? "",
            Coverage = (string)o["coverage"] ?? "",
            Updated = (string)o["updated"] ?? "",
            Licence = (string)o["licence"] ?? "",
            MaxZoom = (int?)o["max_zoom"] ?? 18,
            IsDefault = (bool?)o["default"] ?? false,
        };
    }

    public sealed class Estimate
    {
        public double AreaKm2 { get; private set; }
        public long Bytes { get; private set; }
        public long Seconds { get; private set; }
        public bool Allowed { get; private set; }
        /// <summary>Estimated bytes per layer, for the size shown next to each layer.</summary>
        public IReadOnlyDictionary<string, long> LayerBytes { get; private set; }

        public static Estimate Parse(JObject o) => new Estimate
        {
            AreaKm2 = (double?)o["area_km2"] ?? 0,
            Bytes = (long?)o["bytes"] ?? 0,
            Seconds = (long?)o["seconds"] ?? 0,
            Allowed = (bool?)o["allowed"] ?? false,
            LayerBytes = (o["layers"] as JObject)?.Properties().Where(p => p.Value is JObject)
                .ToDictionary(p => p.Name, p => (long?)p.Value["bytes"] ?? 0) ?? new Dictionary<string, long>(),
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
        /// <summary>Imagery tiles still missing after the service's automatic retry (service 0.1.4+).</summary>
        public int FailedTiles { get; private set; }
        /// <summary>The imagery source this capture used, when the service reports it.</summary>
        public string ImagerySource { get; private set; }

        public bool IsActive => State == "queued" || State == "running";
        public bool IsComplete => State == "complete" && PackageFile != null;
        public bool CanRetry => State == "failed" || State == "cancelled" || LayerErrors.Count > 0;
        /// <summary>Complete, but some imagery tiles never downloaded: offer "Retry N missing tiles".</summary>
        public bool HasMissingTiles => State == "complete" && FailedTiles > 0 && !CanRetry;

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
            var stats = o["progress"]?["imagery"]?["stats"] as JObject;
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
                FailedTiles = (int?)stats?["failed_tiles"] ?? 0,
                ImagerySource = stats?["source"]?.Type == JTokenType.String ? (string)stats["source"] : null,
            };
        }

        public static List<Job> ParseList(JObject o) =>
            (o["jobs"] as JArray)?.OfType<JObject>().Select(Parse).ToList() ?? new List<Job>();
    }

    /// <summary>GET /point (docs/API.md), with the text the pane shows.</summary>
    public sealed class PointResult
    {
        public double Lat { get; private set; }
        public double Lon { get; private set; }
        public double? ElevationM { get; private set; }
        public string StreetAddress { get; private set; }
        public bool StreetAddressExact { get; private set; }
        public double? StreetAddressDistanceM { get; private set; }
        public string NearestPlace { get; private set; }
        /// <summary>-1 when the server has no photo layer.</summary>
        public int PhotoCount { get; private set; }

        public static PointResult Parse(JObject o, double lat, double lon)
        {
            var street = o["street_address"] as JObject;
            return new PointResult
            {
                Lat = (double?)o["lat"] ?? lat,
                Lon = (double?)o["lon"] ?? lon,
                ElevationM = IsNumber(o["elevation_m"]) ? (double?)o["elevation_m"] : null,
                StreetAddress = (string)street?["label"],
                StreetAddressExact = (bool?)street?["exact"] ?? false,
                StreetAddressDistanceM = IsNumber(street?["distance_m"]) ? (double?)street["distance_m"] : null,
                NearestPlace = (o["address"] as JObject)?["label"]?.ToString(),
                PhotoCount = (o["photos"] as JArray)?.Count ?? -1,
            };
        }

        private static bool IsNumber(JToken t) => t != null && (t.Type == JTokenType.Float || t.Type == JTokenType.Integer);

        /// <summary>Multi-line summary: coordinates, elevation, street address, nearest place, photos.</summary>
        public string Describe()
        {
            var c = CultureInfo.InvariantCulture;
            var lines = new List<string> { string.Format(c, "{0:0.00000}, {1:0.00000}", Lat, Lon) };
            if (ElevationM.HasValue)
                lines.Add(string.Format(c, "Elevation {0:0} m ({1:0} ft)", ElevationM.Value, ElevationM.Value * 3.28084));
            if (!string.IsNullOrEmpty(StreetAddress))
            {
                var line = StreetAddress + (StreetAddressExact ? "" : " (street only)");
                if (StreetAddressDistanceM.HasValue) line += string.Format(c, " · {0:0} m away", StreetAddressDistanceM.Value);
                lines.Add(line);
            }
            if (!string.IsNullOrEmpty(NearestPlace)) lines.Add("Near " + NearestPlace);
            if (PhotoCount >= 0) lines.Add($"{PhotoCount} street-level photo(s) within 150 m");
            return string.Join("\n", lines);
        }
    }
}
