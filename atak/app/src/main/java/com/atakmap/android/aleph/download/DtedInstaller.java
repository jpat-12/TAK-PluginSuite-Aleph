package com.atakmap.android.aleph.download;

import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.Enumeration;
import java.util.regex.Pattern;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipInputStream;

/**
 * Installs the DTED cells from a downloaded Aleph package into ATAK's elevation store
 * (atak/DTED/w090/n39.dt2). New cells are copied; cells the device already has are merged with
 * {@link DtedCell#fillVoids} so existing elevation is never lost. No ATAK dependencies — the
 * caller passes the DTED root — so it's unit-tested on the JVM.
 */
public final class DtedInstaller {

    /** Package path of the nested zip the service writes (service/aleph_tak/layers/elevation.py). */
    private static final Pattern NESTED = Pattern.compile("^elevation/[^/]+-dted\\.zip$");
    /** The only entry names we'll write — no "..", no absolute paths, nothing outside DTED/. */
    private static final Pattern CELL = Pattern.compile("^DTED/([ew]\\d{3})/([ns]\\d{2}\\.dt[12])$");

    public static final class Result {
        public int added;
        public int merged;
        public int skipped;
    }

    private DtedInstaller() {
    }

    public static Result install(File packageZip, File dtedRoot) throws IOException {
        Result result = new Result();
        try (ZipFile zip = new ZipFile(packageZip)) {
            Enumeration<? extends ZipEntry> entries = zip.entries();
            while (entries.hasMoreElements()) {
                ZipEntry entry = entries.nextElement();
                if (!NESTED.matcher(entry.getName()).matches()) continue;
                try (ZipInputStream cells = new ZipInputStream(new BufferedInputStream(zip.getInputStream(entry)))) {
                    ZipEntry cell;
                    while ((cell = cells.getNextEntry()) != null) {
                        java.util.regex.Matcher m = CELL.matcher(cell.getName());
                        if (cell.isDirectory() || !m.matches()) continue;
                        installCell(cells, new File(new File(dtedRoot, m.group(1)), m.group(2)), result);
                    }
                }
            }
        }
        return result;
    }

    private static void installCell(InputStream in, File target, Result result) throws IOException {
        File parent = target.getParentFile();
        if (parent != null && !parent.isDirectory() && !parent.mkdirs()) throw new IOException("Can't create " + parent);
        File incoming = new File(target.getPath() + ".aleph");
        try (OutputStream out = new FileOutputStream(incoming)) {
            byte[] buffer = new byte[64 * 1024];
            int n;
            while ((n = in.read(buffer)) > 0) out.write(buffer, 0, n);
        }
        try {
            DtedCell fresh = DtedCell.read(incoming);  // reject a corrupt cell before touching the store
            if (!target.exists()) {
                if (!incoming.renameTo(target)) throw new IOException("Couldn't move " + incoming + " into place");
                result.added++;
                return;
            }
            DtedCell existing = DtedCell.read(target);
            if (!existing.sameGrid(fresh)) {
                result.skipped++;  // different level/zone/origin: leave the device's cell alone
                return;
            }
            if (existing.fillVoids(fresh) > 0) {
                existing.write(target);
                result.merged++;
            }
        } finally {
            //noinspection ResultOfMethodCallIgnored
            incoming.delete();
        }
    }
}
