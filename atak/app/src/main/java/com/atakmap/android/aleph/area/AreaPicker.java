package com.atakmap.android.aleph.area;

import android.graphics.PointF;

import com.atakmap.android.maps.MapEvent;
import com.atakmap.android.maps.MapEventDispatcher;
import com.atakmap.android.maps.MapItem;
import com.atakmap.android.maps.MapView;
import com.atakmap.android.maps.Shape;
import com.atakmap.coremap.maps.coords.GeoBounds;
import com.atakmap.coremap.maps.coords.GeoPoint;
import com.atakmap.coremap.maps.coords.MutableGeoBounds;

/**
 * Map interactions for choosing a capture area or a lookup point. Each one temporarily takes
 * over map taps with ATAK's push/popListeners pattern, so the user's tap selects for us instead
 * of opening the radial menu, and everything is restored afterwards.
 */
public final class AreaPicker {

    public interface AreaCallback {
        void onArea(double[][] ring, String label);

        void onRejected(String reason);
    }

    public interface PointCallback {
        void onPoint(double lat, double lon);
    }

    private final MapView mapView;
    private boolean active;

    public AreaPicker(MapView mapView) {
        this.mapView = mapView;
    }

    /** The visible map, from its four screen corners (works at any rotation). */
    public double[][] mapViewRing() {
        float w = mapView.getWidth();
        float h = mapView.getHeight();
        GeoPoint[] corners = {
                mapView.inverseWithElevation(0, h).get(), mapView.inverseWithElevation(w, h).get(),
                mapView.inverseWithElevation(w, 0).get(), mapView.inverseWithElevation(0, 0).get(),
        };
        return ring(corners);
    }

    /** Next tap on a rectangle, polygon, circle or other drawn shape becomes the area. */
    public void pickShape(AreaCallback callback) {
        begin(event -> {
            MapItem item = event.getItem();
            if (!(item instanceof Shape)) {
                callback.onRejected("That isn't a shape — tap a drawn rectangle, polygon or circle.");
                return true;
            }
            Shape shape = (Shape) item;
            double[][] ring = AreaMath.normalize(ring(shape.getPoints()));
            if (ring.length < 3) {
                GeoBounds b = shape.getBounds(new MutableGeoBounds());
                ring = AreaMath.bbox(b.getWest(), b.getSouth(), b.getEast(), b.getNorth());
            }
            callback.onArea(ring, shape.getTitle() == null ? "Shape" : shape.getTitle());
            return true;
        }, null);
    }

    /** Next tap anywhere on the map. */
    public void pickPoint(PointCallback callback) {
        begin(null, event -> {
            PointF p = event.getPointF();
            GeoPoint point = mapView.inverseWithElevation(p.x, p.y).get();
            callback.onPoint(point.getLatitude(), point.getLongitude());
            return true;
        });
    }

    public void cancel() {
        if (!active) return;
        active = false;
        mapView.getMapEventDispatcher().popListeners();
    }

    private interface Handler {
        boolean handle(MapEvent event);  // true = done picking
    }

    private void begin(Handler onItem, Handler onMap) {
        cancel();
        MapEventDispatcher dispatcher = mapView.getMapEventDispatcher();
        dispatcher.pushListeners();
        dispatcher.clearListeners(MapEvent.ITEM_CLICK);
        dispatcher.clearListeners(MapEvent.MAP_CLICK);
        active = true;
        MapEventDispatcher.MapEventDispatchListener listener = event -> {
            Handler handler = MapEvent.ITEM_CLICK.equals(event.getType()) ? onItem : onMap;
            if (handler != null && handler.handle(event)) cancel();
        };
        dispatcher.addMapEventListener(MapEvent.ITEM_CLICK, listener);
        dispatcher.addMapEventListener(MapEvent.MAP_CLICK, listener);
    }

    private static double[][] ring(GeoPoint[] points) {
        double[][] ring = new double[points.length][];
        for (int i = 0; i < points.length; i++) ring[i] = new double[] {points[i].getLongitude(), points[i].getLatitude()};
        return ring;
    }
}
