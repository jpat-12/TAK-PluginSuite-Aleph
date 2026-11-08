using AlephWinTak.Core;
using Newtonsoft.Json.Linq;
using Xunit;

namespace AlephWinTak.Tests
{
    /// <summary>Imagery sources, per-layer sizes, missing tiles and the point summary (service 0.1.4 fields).</summary>
    public class ModelsTests
    {
        private const string Info = @"{""version"":""0.1.4"",""api"":1,""layers"":[""imagery"",""elevation""],""dted_level"":1,
            ""imagery"":{""name"":""USGS NAIP aerial"",""max_zoom"":18},""imagery_sources"":[
            {""id"":""usgs-naip"",""default"":true,""name"":""USGS NAIP aerial"",""max_zoom"":18,""resolution"":""0.6–1 m"",
             ""coverage"":""Contiguous United States"",""updated"":""Flown every 2–3 years"",""licence"":""Public domain"",""description"":""Aerial photos.""},
            {""id"":""eox-s2cloudless-2016"",""default"":false,""name"":""Sentinel-2 cloudless 2016 (EOX)"",""max_zoom"":14,""resolution"":""10 m"",
             ""coverage"":""Worldwide"",""updated"":""2016 mosaic"",""licence"":""CC BY 4.0"",""description"":""Cloud-free mosaic.""}]}";

        [Fact]
        public void ImagerySourcesAreParsedWithTheDefault()
        {
            var info = ServerInfo.Parse(JObject.Parse(Info));
            Assert.Equal(2, info.ImagerySources.Count);
            Assert.Equal("usgs-naip", info.DefaultSource.Id);
            Assert.Equal(1, info.DtedLevel);
            var eox = info.ImagerySources[1];
            Assert.Equal(14, eox.MaxZoom);
            Assert.Equal("Sentinel-2 cloudless 2016 (EOX) · 10 m", eox.Label);
            Assert.Equal("Cloud-free mosaic.\nWorldwide · 2016 mosaic · CC BY 4.0", eox.Details);
        }

        [Fact]
        public void OlderServicesListNoSources()
        {
            var info = ServerInfo.Parse(JObject.Parse(@"{""api"":1,""imagery"":{""max_zoom"":18}}"));
            Assert.Empty(info.ImagerySources);
            Assert.Null(info.DefaultSource);
            Assert.Equal(2, info.DtedLevel);
        }

        [Fact]
        public void ZoomChoicesFollowTheSourceLimit()
        {
            Assert.Equal(new[] { 14, 15, 16, 17, 18 }, Describe.ZoomChoices(18));
            Assert.Equal(new[] { 12, 13, 14 }, Describe.ZoomChoices(14));
            Assert.Equal(14, Describe.KeepZoom(17, Describe.ZoomChoices(14)));
            Assert.Equal(16, Describe.KeepZoom(16, Describe.ZoomChoices(18)));
            Assert.Equal("z17 (~0.9 m)", Describe.ZoomLabel(17, 40));
            Assert.Equal("z12 (~29 m)", Describe.ZoomLabel(12, 40));
        }

        [Fact]
        public void LayerDescriptionsSayWhatIsDownloaded()
        {
            Assert.Contains("DTED level 2 cells (~30 m posts)", Describe.Layer("elevation", 2));
            Assert.Contains("(~90 m posts)", Describe.Layer("elevation", 1));
            Assert.Contains("KMZ", Describe.Layer("osm", 2));
            Assert.Equal("", Describe.Layer("future-layer", 2));
            Assert.Equal("≈ 6.1 MB", Describe.Size(6_100_000));
            Assert.Equal("≈ 0.1 MB", Describe.Size(1_000));
        }

        [Fact]
        public void EstimateCarriesPerLayerBytes()
        {
            var estimate = Estimate.Parse(JObject.Parse(@"{""bytes"":9000000,""allowed"":true,
                ""layers"":{""imagery"":{""bytes"":6100000,""source"":""USGS NAIP aerial""},""elevation"":{""bytes"":2900000}}}"));
            Assert.Equal(6_100_000, estimate.LayerBytes["imagery"]);
            Assert.Equal(2_900_000, estimate.LayerBytes["elevation"]);
            Assert.False(estimate.LayerBytes.ContainsKey("osm"));
        }

        [Fact]
        public void CompleteJobWithFailedTilesOffersTheirRetry()
        {
            var job = Job.Parse(JObject.Parse(@"{""id"":""j1"",""state"":""complete"",""package"":{""filename"":""a.zip""},
                ""progress"":{""imagery"":{""state"":""complete"",""stats"":{""failed_tiles"":3,""source"":""USGS NAIP aerial""}}}}"));
            Assert.Equal(3, job.FailedTiles);
            Assert.Equal("USGS NAIP aerial", job.ImagerySource);
            Assert.True(job.HasMissingTiles);
            Assert.False(job.CanRetry);
            var old = Job.Parse(JObject.Parse(@"{""id"":""j2"",""state"":""complete"",""progress"":{""imagery"":{""state"":""complete""}}}"));
            Assert.Equal(0, old.FailedTiles);
            Assert.False(old.HasMissingTiles);
        }

        [Fact]
        public void PointSummaryLeadsWithTheStreetAddress()
        {
            var point = PointResult.Parse(JObject.Parse(@"{""lat"":39.79841,""lon"":-89.64401,""elevation_m"":181.2,
                ""street_address"":{""label"":""413 North 5th Street, Springfield, Illinois 62702"",""exact"":true,""distance_m"":12.4},
                ""address"":{""label"":""Lincoln Park, Springfield""},""photos"":null}"), 0, 0);
            Assert.Equal("39.79841, -89.64401\nElevation 181 m (594 ft)\n413 North 5th Street, Springfield, Illinois 62702 · 12 m away"
                + "\nNear Lincoln Park, Springfield", point.Describe());
            var street = PointResult.Parse(JObject.Parse(@"{""elevation_m"":null,""street_address"":{""label"":""County Road 12, Chatham"",
                ""exact"":false,""distance_m"":null},""address"":null,""photos"":[]}"), 39.7, -89.6);
            Assert.Equal("39.70000, -89.60000\nCounty Road 12, Chatham (street only)\n0 street-level photo(s) within 150 m", street.Describe());
        }
    }
}
