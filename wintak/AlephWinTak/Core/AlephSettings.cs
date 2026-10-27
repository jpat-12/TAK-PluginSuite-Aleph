using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using Newtonsoft.Json.Linq;

namespace AlephWinTak.Core
{
    /// <summary>
    /// Server URL + token, in %LOCALAPPDATA%\AlephWinTak\settings.json. The token is encrypted
    /// with Windows DPAPI for the current user, so the file is useless if copied off the machine
    /// and other Windows accounts can't read it. Never logged.
    /// </summary>
    public sealed class AlephSettings
    {
        private readonly string _path;
        private static readonly byte[] Entropy = Encoding.UTF8.GetBytes("AlephWinTak/1");

        public string ServerUrl { get; private set; } = "";
        public string Token { get; private set; } = "";
        public bool IsConfigured => ServerUrl.Length > 0 && Token.Length > 0;

        public AlephSettings(string path = null)
        {
            _path = path ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                                         "AlephWinTak", "settings.json");
            Load();
        }

        private void Load()
        {
            try
            {
                if (!File.Exists(_path)) return;
                var json = JObject.Parse(File.ReadAllText(_path));
                ServerUrl = (string)json["server_url"] ?? "";
                var protectedToken = (string)json["token"];
                if (!string.IsNullOrEmpty(protectedToken))
                {
                    var bytes = ProtectedData.Unprotect(Convert.FromBase64String(protectedToken), Entropy, DataProtectionScope.CurrentUser);
                    Token = Encoding.UTF8.GetString(bytes);
                }
            }
            catch (Exception)
            {
                // Unreadable or from another Windows account: start blank and let the user re-enter.
                ServerUrl = "";
                Token = "";
            }
        }

        public void Save(string serverUrl, string token)
        {
            ServerUrl = AlephClient.NormalizeUrl(serverUrl);
            Token = (token ?? "").Trim();
            var encrypted = ProtectedData.Protect(Encoding.UTF8.GetBytes(Token), Entropy, DataProtectionScope.CurrentUser);
            Directory.CreateDirectory(Path.GetDirectoryName(_path));
            File.WriteAllText(_path, new JObject { ["server_url"] = ServerUrl, ["token"] = Convert.ToBase64String(encrypted) }.ToString());
        }
    }
}
