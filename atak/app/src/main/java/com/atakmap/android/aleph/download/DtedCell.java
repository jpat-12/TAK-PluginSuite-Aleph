package com.atakmap.android.aleph.download;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.charset.StandardCharsets;

/**
 * Reads, merges and rewrites DTED cells (MIL-PRF-89020B), the same layout the service writes
 * (service/aleph_tak/formats/dted.py).
 *
 * Why merge instead of copy: an Aleph cell only has posts inside the captured area and void
 * (-32767) everywhere else, while a device often already holds a complete cell for the whole
 * 1°×1° square. {@link #fillVoids} keeps every existing height and only fills the existing
 * cell's voids, so installing a capture can add elevation but never remove any.
 */
public final class DtedCell {

    public static final int VOID = -32767;
    static final int HEADER_BYTES = 80 + 648 + 2700;

    final byte[] header;
    final int profiles;   // longitude lines, west → east
    final int posts;      // per profile, south → north
    final int[][] heights;

    private DtedCell(byte[] header, int profiles, int posts, int[][] heights) {
        this.header = header;
        this.profiles = profiles;
        this.posts = posts;
        this.heights = heights;
    }

    public static DtedCell read(File file) throws IOException {
        try (RandomAccessFile in = new RandomAccessFile(file, "r")) {
            byte[] header = new byte[HEADER_BYTES];
            in.readFully(header);
            String uhl = new String(header, 0, 80, StandardCharsets.US_ASCII);
            if (!uhl.startsWith("UHL")) throw new IOException(file + ": not a DTED file");
            int profiles = Integer.parseInt(uhl.substring(47, 51).trim());
            int posts = Integer.parseInt(uhl.substring(51, 55).trim());
            int record = 12 + posts * 2;
            if (in.length() != HEADER_BYTES + (long) profiles * record) {
                throw new IOException(file + ": size doesn't match its header");
            }
            int[][] heights = new int[profiles][posts];
            byte[] raw = new byte[record];
            for (int i = 0; i < profiles; i++) {
                in.readFully(raw);
                if ((raw[0] & 0xFF) != 0xAA) throw new IOException(file + ": bad record sentinel at profile " + i);
                for (int j = 0; j < posts; j++) {
                    int word = ((raw[8 + j * 2] & 0xFF) << 8) | (raw[9 + j * 2] & 0xFF);
                    heights[i][j] = (word & 0x8000) != 0 ? -(word & 0x7FFF) : word;
                }
            }
            return new DtedCell(header, profiles, posts, heights);
        }
    }

    public boolean sameGrid(DtedCell other) {
        return profiles == other.profiles && posts == other.posts
                && new String(header, 4, 24, StandardCharsets.US_ASCII)
                        .equals(new String(other.header, 4, 24, StandardCharsets.US_ASCII));
    }

    /** Fill this cell's voids from {@code source}; returns how many posts were filled. */
    public int fillVoids(DtedCell source) {
        int filled = 0;
        for (int i = 0; i < profiles; i++) {
            for (int j = 0; j < posts; j++) {
                if (heights[i][j] == VOID && source.heights[i][j] != VOID) {
                    heights[i][j] = source.heights[i][j];
                    filled++;
                }
            }
        }
        return filled;
    }

    public void write(File file) throws IOException {
        File temporary = new File(file.getPath() + ".tmp");
        try (FileOutputStream out = new FileOutputStream(temporary)) {
            out.write(header);
            byte[] record = new byte[12 + posts * 2];
            for (int i = 0; i < profiles; i++) {
                record[0] = (byte) 0xAA;
                record[1] = (byte) (i >> 16);
                record[2] = (byte) (i >> 8);
                record[3] = (byte) i;
                record[4] = (byte) (i >> 8);
                record[5] = (byte) i;
                record[6] = 0;
                record[7] = 0;
                for (int j = 0; j < posts; j++) {
                    int value = Math.max(-32767, Math.min(32767, heights[i][j]));
                    int word = value < 0 ? (0x8000 | -value) : value;
                    record[8 + j * 2] = (byte) (word >> 8);
                    record[9 + j * 2] = (byte) word;
                }
                long sum = 0;
                for (int k = 0; k < record.length - 4; k++) sum += record[k] & 0xFF;
                int at = record.length - 4;
                record[at] = (byte) (sum >> 24);
                record[at + 1] = (byte) (sum >> 16);
                record[at + 2] = (byte) (sum >> 8);
                record[at + 3] = (byte) sum;
                out.write(record);
            }
        }
        if (!temporary.renameTo(file)) {
            // Windows-style rename refuses to replace; Android doesn't, but be explicit anyway.
            if (!file.delete() || !temporary.renameTo(file)) throw new IOException("Couldn't replace " + file);
        }
    }

    public int height(int profile, int post) {
        return heights[profile][post];
    }

    void set(int profile, int post, int value) {  // tests
        heights[profile][post] = value;
    }
}
