using System;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;
using AlephWinTak.Core;
using Newtonsoft.Json.Linq;
using Xunit;

namespace AlephWinTak.Tests
{
    /// <summary>
    /// DTED merge against a package the Python service really wrote: one DTED1 cell w090/n39 with
    /// a 10×10 block of 200 m posts at profiles 100–109, posts 200–209, one post at -12 m.
    /// </summary>
    public class DtedTests : IDisposable
    {
        private readonly string _dir = Path.Combine(Path.GetTempPath(), "aleph-wintak-" + Guid.NewGuid().ToString("N"));
        private readonly string _package;
        private readonly string _dtedRoot;

        public DtedTests()
        {
            Directory.CreateDirectory(_dir);
            _package = Path.Combine(_dir, "package.zip");
            File.Copy(Path.Combine(AppContext.BaseDirectory, "aleph-package-dted1.zip"), _package);
            _dtedRoot = Path.Combine(_dir, "DTED");
        }

        public void Dispose() => Directory.Delete(_dir, true);

        private string CellPath => Path.Combine(_dtedRoot, "w090", "n39.dt1");

        [Fact]
        public void NewCellIsCopiedAndReadsBackExactly()
        {
            var result = DtedInstaller.Install(_package, _dtedRoot);
            Assert.Equal(1, result.Added);
            var cell = DtedCell.Read(CellPath);
            Assert.Equal(200, cell.Height(100, 200));
            Assert.Equal(-12, cell.Height(105, 205));
            Assert.Equal(DtedCell.Void, cell.Height(0, 0));
        }

        [Fact]
        public void PathTraversalEntriesAreNeverWritten()
        {
            DtedInstaller.Install(_package, _dtedRoot);
            Assert.False(File.Exists(Path.Combine(_dir, "evil.dt1")));
            Assert.False(File.Exists(Path.Combine(_dtedRoot, "evil.dt1")));
        }

        [Fact]
        public void ExistingHeightsAreNeverOverwrittenOnlyVoidsFilled()
        {
            DtedInstaller.Install(_package, _dtedRoot);
            var existing = DtedCell.Read(CellPath);
            existing.Set(0, 0, 321);           // device data outside the capture
            existing.Set(100, 200, 199);       // device data inside the capture
            existing.Set(101, 201, DtedCell.Void);
            existing.Write(CellPath);

            var result = DtedInstaller.Install(_package, _dtedRoot);
            Assert.Equal(1, result.Merged);
            var merged = DtedCell.Read(CellPath);
            Assert.Equal(321, merged.Height(0, 0));
            Assert.Equal(199, merged.Height(100, 200));
            Assert.Equal(200, merged.Height(101, 201));
        }

        [Fact]
        public void RewrittenCellKeepsValidChecksums()
        {
            DtedInstaller.Install(_package, _dtedRoot);
            var cell = DtedCell.Read(CellPath);
            cell.Set(5, 5, -400);
            cell.Write(CellPath);
            Assert.Equal(-400, DtedCell.Read(CellPath).Height(5, 5));  // Read re-validates checksums
        }
    }

    public class ApiAndAreaTests
    {
        [Fact]
        public void JobParsingMatchesServiceShape()
        {
            var job = Job.Parse(JObject.Parse(@"{""id"":""j0123456789ab"",""name"":""Sector 3"",""state"":""running"",
                ""area_km2"":1.88,""layers"":[""imagery"",""osm""],""percent"":40,""warnings"":[],""error"":null,
                ""progress"":{""imagery"":{""state"":""running"",""phase"":""Downloading imagery"",""done"":12,""total"":49},
                ""osm"":{""state"":""failed"",""error"":""Geofabrik down"",""phase"":null,""done"":0,""total"":null}},
                ""package"":null,""some_future_field"":{}}"));
            Assert.Equal("Downloading imagery 12/49", job.Phase);
            Assert.Equal("osm: Geofabrik down", job.LayerErrors.Single());
            Assert.Null(job.Error);
            Assert.True(job.IsActive);
            Assert.True(job.CanRetry);
        }

        [Fact]
        public void InfoChecksApiMajor()
        {
            Assert.True(ServerInfo.Parse(JObject.Parse(@"{""api"":1,""layers"":[""imagery""],""imagery"":{""max_zoom"":18}}")).Compatible);
            Assert.False(ServerInfo.Parse(JObject.Parse(@"{""api"":2}")).Compatible);
        }

        [Theory]
        [InlineData("http://aleph.example.org")]
        [InlineData("https://user:pw@aleph.example.org")]
        [InlineData("https://aleph.example.org/?x=1")]
        [InlineData("ftp://x")]
        public void ServerUrlMustBeAPlainHttpsOrigin(string bad) =>
            Assert.Throws<ArgumentException>(() => AlephClient.NormalizeUrl(bad));

        [Fact]
        public void ServerUrlIsNormalized()
        {
            Assert.Equal("https://aleph.prod.ilwg.us", AlephClient.NormalizeUrl(" https://aleph.prod.ilwg.us/ "));
            Assert.Equal("https://10.0.0.5:8443", AlephClient.NormalizeUrl("https://10.0.0.5:8443"));
        }

        [Fact]
        public void AreaMatchesServiceWithinOnePercent() =>
            // The service measures this as 1.883 km² (live Lake Springfield capture).
            Assert.InRange(AreaMath.AreaKm2(AreaMath.Bbox(-89.6200, 39.7000, -89.6035, 39.7120)), 1.863, 1.903);

        [Fact]
        public void GeoJsonRingIsClosedOnceWithDuplicatesDropped()
        {
            var ring = new[] { (0.0, 0.0), (1.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0) }.ToList();
            var polygon = AreaMath.ToGeoJson(ring);
            Assert.Single((JArray)polygon["coordinates"]);  // exactly one ring, properly nested
            var coordinates = (JArray)polygon["coordinates"][0];
            Assert.Equal(5, coordinates.Count);
            Assert.Equal(coordinates[0].ToString(), coordinates[4].ToString());
            Assert.Equal(JTokenType.Array, coordinates[0].Type);  // [lon, lat], not a bare number
        }
    }

    /// <summary>Resumable download against a fake server that honours Range like the service does.</summary>
    public class DownloadTests
    {
        private static readonly byte[] Payload = Enumerable.Range(0, 300_000).Select(i => (byte)(i * 7)).ToArray();
        private static readonly string Sha = BitConverter.ToString(SHA256.HashData(Payload)).Replace("-", "").ToLowerInvariant();

        private sealed class RangeServer : HttpMessageHandler
        {
            public int Requests;
            public long? LastRangeFrom;

            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
            {
                Requests++;
                Assert.Equal("Bearer", request.Headers.Authorization.Scheme);
                long from = request.Headers.Range?.Ranges.First().From ?? 0;
                LastRangeFrom = request.Headers.Range == null ? (long?)null : from;
                var response = new HttpResponseMessage(from > 0 ? HttpStatusCode.PartialContent : HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(Payload.Skip((int)from).ToArray()),
                };
                return Task.FromResult(response);
            }
        }

        private static Job CompleteJob() => Job.Parse(JObject.Parse(
            $@"{{""id"":""j1"",""state"":""complete"",""progress"":{{}},""package"":{{""filename"":""a.zip"",""bytes"":{Payload.Length},""sha256"":""{Sha}""}}}}"));

        [Fact]
        public async Task ResumesFromPartialFileAndVerifiesHash()
        {
            string dir = Path.Combine(Path.GetTempPath(), "aleph-dl-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(dir);
            try
            {
                File.WriteAllBytes(Path.Combine(dir, "a.zip.part"), Payload.Take(100_000).ToArray());  // interrupted earlier
                var server = new RangeServer();
                var client = new AlephClient(() => "https://aleph.example.org", () => "alt_x", server);
                string path = await client.DownloadPackageAsync(CompleteJob(), dir, null, CancellationToken.None);
                Assert.Equal(100_000, server.LastRangeFrom);
                Assert.Equal(Payload, File.ReadAllBytes(path));
                Assert.False(File.Exists(path + ".part"));

                await client.DownloadPackageAsync(CompleteJob(), dir, null, CancellationToken.None);
                Assert.Equal(1, server.Requests);  // already verified on disk → no second download
            }
            finally
            {
                Directory.Delete(dir, true);
            }
        }

        [Fact]
        public async Task CorruptDownloadIsRejectedAndNotResumed()
        {
            string dir = Path.Combine(Path.GetTempPath(), "aleph-dl-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(dir);
            try
            {
                var badJob = Job.Parse(JObject.Parse(
                    $@"{{""id"":""j1"",""state"":""complete"",""progress"":{{}},""package"":{{""filename"":""a.zip"",""bytes"":{Payload.Length},""sha256"":""{new string('0', 64)}""}}}}"));
                var client = new AlephClient(() => "https://aleph.example.org", () => "alt_x", new RangeServer());
                await Assert.ThrowsAsync<AlephException>(() => client.DownloadPackageAsync(badJob, dir, null, CancellationToken.None));
                Assert.False(File.Exists(Path.Combine(dir, "a.zip.part")));
            }
            finally
            {
                Directory.Delete(dir, true);
            }
        }
    }
}
