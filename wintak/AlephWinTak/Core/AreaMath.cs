using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace AlephWinTak.Core
{
    /// <summary>
    /// Capture-area geometry with no WinTAK dependencies. Rings are lists of (lon, lat) — GeoJSON
    /// order, which is what the Aleph API takes. Same formulas as the ATAK and CloudTAK clients.
    /// </summary>
    public static class AreaMath
    {
        private const double EarthRadiusM = 6_371_008.8;

        public static List<(double Lon, double Lat)> Bbox(double west, double south, double east, double north) =>
            new List<(double, double)> { (west, south), (east, south), (east, north), (west, north) };

        /// <summary>Approximate ground area on a local equirectangular plane.</summary>
        public static double AreaKm2(IReadOnlyList<(double Lon, double Lat)> ring)
        {
            int n = ring.Count;
            if (n < 3) return 0;
            double cos = Math.Cos(ring.Average(p => p.Lat) * Math.PI / 180);
            double twice = 0;
            for (int i = 0; i < n; i++)
            {
                var a = ring[i];
                var b = ring[(i + 1) % n];
                twice += a.Lon * cos * b.Lat - b.Lon * cos * a.Lat;
            }
            double degree = Math.PI / 180 * EarthRadiusM;
            return Math.Abs(twice) / 2 * degree * degree / 1e6;
        }

        /// <summary>Drop a repeated closing vertex and consecutive duplicates (shapes often include both).</summary>
        public static List<(double Lon, double Lat)> Normalize(IEnumerable<(double Lon, double Lat)> ring)
        {
            var output = new List<(double Lon, double Lat)>();
            foreach (var p in ring)
                if (output.Count == 0 || !Same(output[output.Count - 1], p)) output.Add(p);
            if (output.Count > 1 && Same(output[0], output[output.Count - 1])) output.RemoveAt(output.Count - 1);
            return output;
        }

        private static bool Same((double Lon, double Lat) a, (double Lon, double Lat) b) =>
            Math.Abs(a.Lon - b.Lon) < 1e-9 && Math.Abs(a.Lat - b.Lat) < 1e-9;

        /// <summary>GeoJSON Polygon with a closed ring.</summary>
        public static JObject ToGeoJson(IReadOnlyList<(double Lon, double Lat)> ring)
        {
            var open = Normalize(ring);
            var coordinates = new JArray();
            for (int i = 0; i <= open.Count; i++)
            {
                var p = open[i % open.Count];
                coordinates.Add(new JArray(p.Lon, p.Lat));
            }
            // Not `new JArray(coordinates)`: that copies the ring's items instead of nesting the
            // ring, producing [[lon,lat],…] where GeoJSON needs [[[lon,lat],…]].
            var rings = new JArray();
            rings.Add(coordinates);
            return new JObject { ["type"] = "Polygon", ["coordinates"] = rings };
        }
    }
}
