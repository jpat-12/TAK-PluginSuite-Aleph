using System.IO;
using System.IO.Compression;
using System.Text.RegularExpressions;

namespace AlephWinTak.Core
{
    /// <summary>
    /// Installs the DTED cells from a downloaded Aleph package into a DTED root (WinTAK:
    /// C:\ProgramData\WinTAK\DTED). New cells are copied; cells the workstation already has are
    /// merged with <see cref="DtedCell.FillVoids"/> so existing elevation is never lost.
    /// </summary>
    public static class DtedInstaller
    {
        /// <summary>Package path of the nested zip the service writes (layers/elevation.py).</summary>
        private static readonly Regex Nested = new Regex(@"^elevation/[^/]+-dted\.zip$");
        /// <summary>The only entry names we'll write — no "..", no absolute paths, nothing outside DTED/.</summary>
        private static readonly Regex Cell = new Regex(@"^DTED/([ew]\d{3})/([ns]\d{2}\.dt[12])$");

        public sealed class Result
        {
            public int Added;
            public int Merged;
            public int Skipped;
        }

        public static Result Install(string packageZip, string dtedRoot)
        {
            var result = new Result();
            using (var package = ZipFile.OpenRead(packageZip))
            {
                foreach (var entry in package.Entries)
                {
                    if (!Nested.IsMatch(entry.FullName)) continue;
                    using (var nestedStream = entry.Open())
                    using (var buffer = new MemoryStream())
                    {
                        nestedStream.CopyTo(buffer);
                        buffer.Position = 0;
                        using (var cells = new ZipArchive(buffer, ZipArchiveMode.Read))
                        {
                            foreach (var cell in cells.Entries)
                            {
                                var m = Cell.Match(cell.FullName);
                                if (!m.Success) continue;
                                InstallCell(cell, Path.Combine(dtedRoot, m.Groups[1].Value, m.Groups[2].Value), result);
                            }
                        }
                    }
                }
            }
            return result;
        }

        private static void InstallCell(ZipArchiveEntry cell, string target, Result result)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(target));
            string incoming = target + ".aleph";
            using (var input = cell.Open())
            using (var output = File.Create(incoming))
                input.CopyTo(output);
            try
            {
                var fresh = DtedCell.Read(incoming);  // reject a corrupt cell before touching the store
                if (!File.Exists(target))
                {
                    File.Move(incoming, target);
                    result.Added++;
                    return;
                }
                var existing = DtedCell.Read(target);
                if (!existing.SameGrid(fresh))
                {
                    result.Skipped++;  // different level/zone/origin: leave the workstation's cell alone
                    return;
                }
                if (existing.FillVoids(fresh) > 0)
                {
                    existing.Write(target);
                    result.Merged++;
                }
            }
            finally
            {
                if (File.Exists(incoming)) File.Delete(incoming);
            }
        }
    }
}
