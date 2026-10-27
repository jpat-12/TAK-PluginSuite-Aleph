using System;
using System.IO;
using System.Text;

namespace AlephWinTak.Core
{
    /// <summary>
    /// Reads, merges and rewrites DTED cells (MIL-PRF-89020B) — the layout the service writes
    /// (service/aleph_tak/formats/dted.py). C# twin of the ATAK plugin's DtedCell.java.
    ///
    /// Why merge instead of copy: an Aleph cell has posts only inside the captured area and void
    /// (-32767) elsewhere, while a workstation often already holds a complete cell for the whole
    /// 1°×1° square. <see cref="FillVoids"/> keeps every existing height and only fills the
    /// existing cell's voids, so installing a capture can add elevation but never remove any.
    /// </summary>
    public sealed class DtedCell
    {
        public const int Void = -32767;
        internal const int HeaderBytes = 80 + 648 + 2700;

        private readonly byte[] _header;
        private readonly int[,] _heights;   // [profile (west→east), post (south→north)]
        public int Profiles { get; }
        public int Posts { get; }

        private DtedCell(byte[] header, int profiles, int posts, int[,] heights)
        {
            _header = header;
            Profiles = profiles;
            Posts = posts;
            _heights = heights;
        }

        public static DtedCell Read(string path)
        {
            byte[] data = File.ReadAllBytes(path);
            if (data.Length < HeaderBytes || Encoding.ASCII.GetString(data, 0, 3) != "UHL")
                throw new InvalidDataException($"{path}: not a DTED file");
            string uhl = Encoding.ASCII.GetString(data, 0, 80);
            int profiles = int.Parse(uhl.Substring(47, 4).Trim());
            int posts = int.Parse(uhl.Substring(51, 4).Trim());
            int record = 12 + posts * 2;
            if (data.Length != HeaderBytes + (long)profiles * record)
                throw new InvalidDataException($"{path}: size doesn't match its header");
            var heights = new int[profiles, posts];
            for (int i = 0; i < profiles; i++)
            {
                int start = HeaderBytes + i * record;
                if (data[start] != 0xAA) throw new InvalidDataException($"{path}: bad record sentinel at profile {i}");
                long sum = 0;
                for (int k = 0; k < record - 4; k++) sum += data[start + k];
                long stored = ((long)data[start + record - 4] << 24) | ((long)data[start + record - 3] << 16)
                              | ((long)data[start + record - 2] << 8) | data[start + record - 1];
                if ((sum & 0xFFFFFFFF) != stored) throw new InvalidDataException($"{path}: bad checksum at profile {i}");
                for (int j = 0; j < posts; j++)
                {
                    int word = (data[start + 8 + j * 2] << 8) | data[start + 9 + j * 2];
                    heights[i, j] = (word & 0x8000) != 0 ? -(word & 0x7FFF) : word;
                }
            }
            var header = new byte[HeaderBytes];
            Array.Copy(data, header, HeaderBytes);
            return new DtedCell(header, profiles, posts, heights);
        }

        public bool SameGrid(DtedCell other) =>
            Profiles == other.Profiles && Posts == other.Posts
            && Encoding.ASCII.GetString(_header, 4, 24) == Encoding.ASCII.GetString(other._header, 4, 24);

        /// <summary>Fill this cell's voids from <paramref name="source"/>; returns how many posts were filled.</summary>
        public int FillVoids(DtedCell source)
        {
            int filled = 0;
            for (int i = 0; i < Profiles; i++)
                for (int j = 0; j < Posts; j++)
                    if (_heights[i, j] == Void && source._heights[i, j] != Void)
                    {
                        _heights[i, j] = source._heights[i, j];
                        filled++;
                    }
            return filled;
        }

        public int Height(int profile, int post) => _heights[profile, post];

        internal void Set(int profile, int post, int value) => _heights[profile, post] = value;  // tests

        public void Write(string path)
        {
            string temporary = path + ".tmp";
            using (var output = new FileStream(temporary, FileMode.Create, FileAccess.Write))
            {
                output.Write(_header, 0, _header.Length);
                var record = new byte[12 + Posts * 2];
                for (int i = 0; i < Profiles; i++)
                {
                    record[0] = 0xAA;
                    record[1] = (byte)(i >> 16);
                    record[2] = (byte)(i >> 8);
                    record[3] = (byte)i;
                    record[4] = (byte)(i >> 8);
                    record[5] = (byte)i;
                    record[6] = 0;
                    record[7] = 0;
                    for (int j = 0; j < Posts; j++)
                    {
                        int value = Math.Max(-32767, Math.Min(32767, _heights[i, j]));
                        int word = value < 0 ? (0x8000 | -value) : value;
                        record[8 + j * 2] = (byte)(word >> 8);
                        record[9 + j * 2] = (byte)word;
                    }
                    long sum = 0;
                    for (int k = 0; k < record.Length - 4; k++) sum += record[k];
                    int at = record.Length - 4;
                    record[at] = (byte)(sum >> 24);
                    record[at + 1] = (byte)(sum >> 16);
                    record[at + 2] = (byte)(sum >> 8);
                    record[at + 3] = (byte)sum;
                    output.Write(record, 0, record.Length);
                }
            }
            if (File.Exists(path)) File.Delete(path);
            File.Move(temporary, path);
        }
    }
}
