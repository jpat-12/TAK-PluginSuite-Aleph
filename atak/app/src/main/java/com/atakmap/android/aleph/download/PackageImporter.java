package com.atakmap.android.aleph.download;

import android.content.Intent;

import com.atakmap.android.importexport.ImportExportMapComponent;
import com.atakmap.android.ipc.AtakBroadcast;
import com.atakmap.coremap.filesystem.FileSystemUtils;

import java.io.File;
import java.io.IOException;

/**
 * Hands a verified package to ATAK. Two steps, because ATAK's generic import can't be trusted
 * with Aleph's mostly-void DTED cells (it might replace a device's complete cell):
 *
 *   1. DTED → merged into atak/DTED by {@link DtedInstaller} (fills voids, never overwrites).
 *   2. Everything else (MBTiles imagery, OSM KMZ, photo markers) → ATAK's own data-package
 *      import, via the same broadcast its Import Manager uses. The manifest marks the DTED zip
 *      and the GIS-only GeoTIFF ignore="true", so step 2 skips them.
 *
 * USER_HANDLE_IMPORT_FILE_ACTION and its extras were read from the 5.6 SDK's
 * ImportExportMapComponent; re-check them when moving to a new ATAK SDK.
 */
public final class PackageImporter {

    private PackageImporter() {
    }

    public static DtedInstaller.Result installElevation(File packageZip) throws IOException {
        return DtedInstaller.install(packageZip, FileSystemUtils.getItem("DTED"));
    }

    public static void importPackage(File packageZip) {
        Intent intent = new Intent(ImportExportMapComponent.USER_HANDLE_IMPORT_FILE_ACTION);
        intent.putExtra("filepath", packageZip.getAbsolutePath());
        intent.putExtra("importInPlace", false);
        intent.putExtra("promptOnMultipleMatch", false);
        intent.putExtra("showNotificationsDuringImport", true);
        intent.putExtra("zoomToFile", true);
        AtakBroadcast.getInstance().sendBroadcast(intent);
    }

    public static File downloadDir() {
        return FileSystemUtils.getItem("tools/aleph");
    }
}
