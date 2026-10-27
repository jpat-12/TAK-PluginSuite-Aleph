using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace AlephWinTak.Core
{
    /// <summary>An HTTP error from the service, carrying its {"error": "..."} message for the operator.</summary>
    public sealed class AlephException : Exception
    {
        public int Status { get; }
        public AlephException(int status, string message) : base(message) { Status = status; }
    }

    /// <summary>
    /// Calls to the Aleph capture service's /api/v1 (docs/API.md), plus the resumable,
    /// SHA-256-verified package download. No WinTAK dependencies.
    /// </summary>
    public sealed class AlephClient
    {
        private readonly HttpClient _http;
        private readonly Func<string> _serverUrl;
        private readonly Func<string> _token;

        public AlephClient(Func<string> serverUrl, Func<string> token, HttpMessageHandler handler = null)
        {
            _serverUrl = serverUrl;
            _token = token;
            // AllowAutoRedirect off: never forward the bearer token to another host.
            _http = new HttpClient(handler ?? new HttpClientHandler { AllowAutoRedirect = false })
            {
                Timeout = Timeout.InfiniteTimeSpan,  // per-call timeouts below; downloads can run long
            };
        }

        /// <summary>
        /// HTTPS only, no credentials, query or fragment — the token goes to whatever host this
        /// names, so it must be a plain origin (workspace CLAUDE.md §12).
        /// </summary>
        public static string NormalizeUrl(string raw)
        {
            string url = (raw ?? "").Trim().TrimEnd('/');
            if (url.Length == 0) return "";
            if (!Uri.TryCreate(url, UriKind.Absolute, out var uri)) throw new ArgumentException("Not a valid URL: " + raw);
            if (uri.Scheme != Uri.UriSchemeHttps) throw new ArgumentException("Server URL must start with https://");
            if (!string.IsNullOrEmpty(uri.UserInfo) || !string.IsNullOrEmpty(uri.Query) || !string.IsNullOrEmpty(uri.Fragment))
                throw new ArgumentException("Use just the server address, e.g. https://aleph.example.org");
            return "https://" + uri.Authority + uri.AbsolutePath.TrimEnd('/');
        }

        public async Task<ServerInfo> InfoAsync() => ServerInfo.Parse(await SendAsync(HttpMethod.Get, "/info", null, false));
        public async Task<Estimate> EstimateAsync(JObject capture) => Estimate.Parse(await SendAsync(HttpMethod.Post, "/estimate", capture, true));
        public async Task<Job> CreateAsync(JObject capture) => Job.Parse(await SendAsync(HttpMethod.Post, "/jobs", capture, true));
        public async Task<List<Job>> JobsAsync() => Job.ParseList(await SendAsync(HttpMethod.Get, "/jobs", null, true));
        public Task DeleteAsync(string id) => SendAsync(HttpMethod.Delete, "/jobs/" + id, null, true);
        public async Task<Job> RetryAsync(string id) => Job.Parse(await SendAsync(HttpMethod.Post, "/jobs/" + id + "/retry", null, true));

        public Task<JObject> PointAsync(double lat, double lon) =>
            SendAsync(HttpMethod.Get, string.Format(CultureInfo.InvariantCulture, "/point?lat={0:F6}&lon={1:F6}", lat, lon), null, true);

        private HttpRequestMessage Request(HttpMethod method, string path, bool auth)
        {
            string server = _serverUrl();
            if (string.IsNullOrEmpty(server)) throw new AlephException(0, "Set the Aleph server URL first.");
            var request = new HttpRequestMessage(method, server + "/api/v1" + path);
            request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
            if (auth) request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _token());
            return request;
        }

        private async Task<JObject> SendAsync(HttpMethod method, string path, JObject body, bool auth)
        {
            using (var request = Request(method, path, auth))
            using (var cts = new CancellationTokenSource(TimeSpan.FromSeconds(30)))
            {
                if (body != null) request.Content = new StringContent(body.ToString(), Encoding.UTF8, "application/json");
                using (var response = await _http.SendAsync(request, cts.Token).ConfigureAwait(false))
                {
                    string text = await response.Content.ReadAsStringAsync().ConfigureAwait(false);
                    JObject json;
                    try { json = string.IsNullOrWhiteSpace(text) ? new JObject() : JObject.Parse(text); }
                    catch (Exception) { throw new AlephException((int)response.StatusCode, $"Unexpected response from {_serverUrl()} (HTTP {(int)response.StatusCode})"); }
                    if ((int)response.StatusCode >= 300)
                    {
                        string message = (string)json["error"] ?? "HTTP " + (int)response.StatusCode;
                        if (response.StatusCode == HttpStatusCode.Unauthorized) message = "The server rejected the token — check it in Settings. " + message;
                        throw new AlephException((int)response.StatusCode, message);
                    }
                    return json;
                }
            }
        }

        /// <summary>
        /// Download a job's package to <paramref name="directory"/>, resuming from a .part file with
        /// Range/If-Range (the ETag is the package's SHA-256), and verify the hash before returning.
        /// </summary>
        public async Task<string> DownloadPackageAsync(Job job, string directory, IProgress<(long Done, long Total)> progress,
                                                       CancellationToken cancel)
        {
            Directory.CreateDirectory(directory);
            string target = Path.Combine(directory, job.PackageFile);
            if (File.Exists(target) && Sha256(target).Equals(job.PackageSha256, StringComparison.OrdinalIgnoreCase)) return target;
            string part = target + ".part";
            long have = File.Exists(part) ? new FileInfo(part).Length : 0;

            using (var request = Request(HttpMethod.Get, "/jobs/" + job.Id + "/package", true))
            {
                if (have > 0)
                {
                    request.Headers.Range = new RangeHeaderValue(have, null);
                    request.Headers.IfRange = new RangeConditionHeaderValue(new EntityTagHeaderValue("\"" + job.PackageSha256 + "\""));
                }
                using (var response = await _http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancel).ConfigureAwait(false))
                {
                    bool append = response.StatusCode == HttpStatusCode.PartialContent;
                    if ((int)response.StatusCode == 416 && have == job.PackageBytes)
                    {
                        // the .part is already complete; fall through to verification
                    }
                    else if (response.StatusCode != HttpStatusCode.OK && !append)
                    {
                        if ((int)response.StatusCode == 416) File.Delete(part);  // stale .part from another package
                        throw new AlephException((int)response.StatusCode, "Download failed: HTTP " + (int)response.StatusCode);
                    }
                    else
                    {
                        if (!append) have = 0;
                        using (var input = await response.Content.ReadAsStreamAsync().ConfigureAwait(false))
                        using (var output = new FileStream(part, append ? FileMode.Append : FileMode.Create, FileAccess.Write))
                        {
                            var buffer = new byte[256 * 1024];
                            long done = have, lastReport = 0;
                            int n;
                            while ((n = await input.ReadAsync(buffer, 0, buffer.Length, cancel).ConfigureAwait(false)) > 0)
                            {
                                await output.WriteAsync(buffer, 0, n, cancel).ConfigureAwait(false);
                                done += n;
                                if (done - lastReport > 512 * 1024)
                                {
                                    progress?.Report((done, job.PackageBytes));
                                    lastReport = done;
                                }
                            }
                            progress?.Report((done, job.PackageBytes));
                        }
                    }
                }
            }
            if (!Sha256(part).Equals(job.PackageSha256, StringComparison.OrdinalIgnoreCase))
            {
                File.Delete(part);  // a corrupt resume must not be resumed again
                throw new AlephException(0, "Downloaded package failed its checksum; it will restart from scratch.");
            }
            if (File.Exists(target)) File.Delete(target);
            File.Move(part, target);
            return target;
        }

        internal static string Sha256(string path)
        {
            using (var sha = SHA256.Create())
            using (var stream = File.OpenRead(path))
                return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
        }
    }
}
