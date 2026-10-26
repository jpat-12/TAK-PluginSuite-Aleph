package com.atakmap.android.aleph.download;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.NetworkInfo;
import android.os.Build;
import android.os.StatFs;

import com.atakmap.android.aleph.api.AlephClient;
import com.atakmap.android.aleph.api.Models;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Downloads a capture's package over spotty field LTE: resumes from a .part file with an HTTP
 * Range request (the service supports Range/If-Range on /package), checks storage first, and
 * verifies the SHA-256 the job record advertises before anything is imported.
 */
public final class PackageDownloader {

    /** Package + its unpacked copy + DTED cells, with headroom. */
    private static final double STORAGE_FACTOR = 2.5;

    public interface Listener {
        void onProgress(long done, long total);
    }

    private PackageDownloader() {
    }

    @SuppressWarnings("deprecation")
    public static boolean onUnmeteredNetwork(Context context) {
        ConnectivityManager cm = (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
        if (cm == null) return false;
        if (Build.VERSION.SDK_INT >= 23) {
            Network network = cm.getActiveNetwork();
            NetworkCapabilities caps = network == null ? null : cm.getNetworkCapabilities(network);
            return caps != null && (caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)
                    || caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET));
        }
        NetworkInfo info = cm.getActiveNetworkInfo();
        return info != null && info.isConnected()
                && (info.getType() == ConnectivityManager.TYPE_WIFI || info.getType() == ConnectivityManager.TYPE_ETHERNET);
    }

    public static void checkStorage(File dir, long packageBytes) throws IOException {
        if (!dir.isDirectory() && !dir.mkdirs()) throw new IOException("Can't create " + dir);
        long available = new StatFs(dir.getPath()).getAvailableBytes();
        long needed = (long) (packageBytes * STORAGE_FACTOR);
        if (available < needed) {
            throw new IOException(String.format(Locale.US, "Not enough storage: need %.0f MB free, have %.0f MB.",
                    needed / 1e6, available / 1e6));
        }
    }

    public static File download(AlephClient client, Models.Job job, File dir, Listener listener, AtomicBoolean cancel)
            throws IOException {
        File target = new File(dir, job.packageFile);
        if (target.isFile() && job.packageSha256.equalsIgnoreCase(sha256(target))) return target;
        File part = new File(dir, job.packageFile + ".part");
        long have = part.isFile() ? part.length() : 0;

        HttpURLConnection connection = client.openPackage(job.id);
        try {
            if (have > 0) {
                connection.setRequestProperty("Range", "bytes=" + have + "-");
                // Only resume if it's still the same package (the ETag is its SHA-256).
                connection.setRequestProperty("If-Range", "\"" + job.packageSha256 + "\"");
            }
            int status = connection.getResponseCode();
            boolean append = status == HttpURLConnection.HTTP_PARTIAL;
            if (status == 416 && have == job.packageBytes) {
                append = true;  // the .part is already complete; fall through to verification
            } else if (status != HttpURLConnection.HTTP_OK && !append) {
                if (status == 416) {
                    //noinspection ResultOfMethodCallIgnored
                    part.delete();  // stale .part from a different package: start over next time
                }
                throw new IOException("Download failed: HTTP " + status);
            } else {
                if (!append) have = 0;
                try (InputStream in = connection.getInputStream();
                     OutputStream out = new FileOutputStream(part, append)) {
                    byte[] buffer = new byte[256 * 1024];
                    long done = have;
                    long lastReport = 0;
                    int n;
                    while ((n = in.read(buffer)) > 0) {
                        if (cancel.get()) throw new IOException("Download cancelled; it will resume from here next time.");
                        out.write(buffer, 0, n);
                        done += n;
                        if (done - lastReport > 512 * 1024) {
                            listener.onProgress(done, job.packageBytes);
                            lastReport = done;
                        }
                    }
                    listener.onProgress(done, job.packageBytes);
                }
            }
        } finally {
            connection.disconnect();
        }
        if (!job.packageSha256.equalsIgnoreCase(sha256(part))) {
            //noinspection ResultOfMethodCallIgnored
            part.delete();  // a corrupt resume must not be resumed again
            throw new IOException("Downloaded package failed its checksum; it will restart from scratch.");
        }
        if (target.exists() && !target.delete()) throw new IOException("Can't replace " + target);
        if (!part.renameTo(target)) throw new IOException("Can't move " + part + " into place");
        return target;
    }

    static String sha256(File file) throws IOException {
        try (InputStream in = new FileInputStream(file)) {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[256 * 1024];
            int n;
            while ((n = in.read(buffer)) > 0) digest.update(buffer, 0, n);
            StringBuilder hex = new StringBuilder();
            for (byte b : digest.digest()) hex.append(String.format(Locale.US, "%02x", b));
            return hex.toString();
        } catch (NoSuchAlgorithmException e) {
            throw new IOException(e);
        }
    }
}
