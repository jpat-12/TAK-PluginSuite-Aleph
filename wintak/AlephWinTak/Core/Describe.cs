using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;

namespace AlephWinTak.Core
{
    /// <summary>
    /// The words and numbers the pane shows about a capture before it's made: what each layer
    /// downloads, the imagery zoom choices a source allows, and sizes. No WinTAK/WPF, so it's
    /// unit-tested; the same wording as the CloudTAK panel and the ATAK plugin's api/Describe.java.
    /// </summary>
    public static class Describe
    {
        /// <summary>One line saying what ticking a layer actually downloads and how WinTAK uses it.</summary>
        public static string Layer(string layer, int dtedLevel)
        {
            switch (layer)
            {
                case "imagery":
                    return "Photo imagery of the area as MBTiles (shows in WinTAK's overlays). Pick the source below.";
                case "elevation":
                    return string.Format(CultureInfo.InvariantCulture,
                        "AWS Terrain Tiles (USGS 3DEP in the US, SRTM elsewhere) → DTED level {0} cells (~{1} m posts) + a GeoTIFF; "
                        + "merged into WinTAK's elevation data, filling gaps only.", dtedLevel, dtedLevel == 2 ? 30 : 90);
                case "osm":
                    return "OpenStreetMap via Geofabrik: roads, trails, railways, power lines, waterways, lakes, buildings and airfields → KMZ.";
                case "photos":
                    return "Mapillary street-level photos taken inside the area (CC BY-SA) → map markers with each photo attached.";
                default:
                    return "";
            }
        }

        /// <summary>Up to five imagery zooms ending at the source's limit, never below z12 (the API's minimum).</summary>
        public static IReadOnlyList<int> ZoomChoices(int maxZoom)
        {
            int low = Math.Max(12, maxZoom - 4);
            return Enumerable.Range(low, Math.Max(0, maxZoom - low + 1)).ToList();
        }

        /// <summary>"z17 (~0.9 m)": ground resolution at the area's latitude.</summary>
        public static string ZoomLabel(int zoom, double latitude)
        {
            double metres = 156543.03 * Math.Cos(latitude * Math.PI / 180) / Math.Pow(2, zoom);
            return string.Format(CultureInfo.InvariantCulture, metres < 10 ? "z{0} (~{1:0.0} m)" : "z{0} (~{1:0} m)", zoom, metres);
        }

        /// <summary>The zoom to keep when the source changes: the same one if allowed, else the finest the source has.</summary>
        public static int KeepZoom(int current, IReadOnlyList<int> choices) =>
            choices.Count == 0 || choices.Contains(current) ? current : choices[choices.Count - 1];

        /// <summary>"≈ 6.1 MB"</summary>
        public static string Size(long bytes) => bytes >= 1e9
            ? string.Format(CultureInfo.InvariantCulture, "≈ {0:0.0} GB", bytes / 1e9)
            : string.Format(CultureInfo.InvariantCulture, "≈ {0:0.0} MB", Math.Max(0.1, bytes / 1e6));
    }
}
