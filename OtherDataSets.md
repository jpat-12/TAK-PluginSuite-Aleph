# Other open datasets — candidates for Aleph for TAK

**A menu, not a plan of record. Nothing here is implemented.** Jon picks; each pick becomes a
layer (or a new source for an existing one) in `service/aleph_tak/layers/` + `sources.py`, an
option in `docs/API.md`, and a toggle in each client. Part 2 is the plan for elevation in every
TAK client.

How every entry was judged:
- **Licence** must allow offline redistribution inside a data package (public domain, CC0,
  CC BY, ODbL with attribution in `ATTRIBUTION.txt`). Non-commercial (NC), "view only" and
  Google/Bing/Esri-imagery terms are out, as the plan requires.
- **No GDAL on the server.** *Access* says how we'd read it without GDAL: a bbox query to an
  ArcGIS REST / OGC API / WFS endpoint returning GeoJSON, XYZ/WMTS tiles, Cloud-Optimized
  GeoTIFFs (COG; needs a small COG reader), CSV, or GeoParquet (needs pyarrow). FileGDB,
  shapefile-only and S-57 sources are flagged.
- **Fit** for a CAP aircrew or ground team: ★★★ use on most sorties · ★★ often useful ·
  ★ niche.
- Licences and endpoints change, and federal portals moved a lot in 2025 (HIFLD Open shut down
  in Aug 2025). **Verify each one before building it.** "Check" in the licence column means
  check it before use.

---

## Part 1 — the list

### A. Elevation, terrain and bathymetry
| Dataset | Coverage | What it adds | Licence | Access | Fit |
|---|---|---|---|---|---|
| AWS Terrain Tiles (Tilezen) — **in use** | Global | Current DTED/GeoTIFF source; US parts already include 3DEP | Mixed open sources, attribution | Terrarium PNG tiles | ★★★ |
| USGS 3DEP 1 m DEM (lidar) | Most of US, growing | 1 m bare earth: ditches, berms, trails under canopy | Public domain | COGs on AWS / TNM API | ★★★ |
| USGS 3DEP 1/3″ (~10 m) seamless | CONUS | Clean national DEM; DTED2 source with no tiling artefacts | Public domain | TNM ImageServer / COGs | ★★ |
| USGS 3DEP lidar point clouds (COPC) | Much of US | Canopy height, building heights, obstacle height | Public domain | COPC on AWS (heavy) | ★ |
| Copernicus DEM GLO-30 / GLO-90 | Global (a few countries withheld) | Second source outside the US; cross-check | Free & open, attribution | COGs on AWS `copernicus-dem-30m` | ★★ |
| NASA SRTM 1″ | 60°N–56°S | Classic fallback DEM | Public domain | Earthdata login (tiles) | ★ |
| NASADEM | 60°N–56°S | Re-processed SRTM with voids filled | Public domain | Earthdata / COG mirrors | ★ |
| ALOS AW3D30 (JAXA) | Global | Alternative 30 m DSM | Free with attribution (check) | Registration download | ★ |
| GEBCO grid | Global oceans + lakes | Bathymetry for water searches | Public domain-like (attribution) | NetCDF/GeoTIFF bulk | ★ |
| NOAA CUDEM / Coastal DEMs | US coasts, Great Lakes | Seamless topo-bathy at the shoreline | Public domain | COGs / THREDDS | ★★ |
| NOAA Great Lakes bathymetry | Great Lakes | Depth for Lake Michigan SAR | Public domain | Bulk grids | ★ |
| USACE / state lake bathymetry | Spotty | Reservoir depths | Usually public domain | Varies | ★ |
| **Derived:** contours, hillshade, slope, aspect | Wherever we have a DEM | Topo-map look, steep-ground warning, visibility | Ours | Computed from the DEM we already fetch | ★★★ |

### B. Imagery and base maps
| Dataset | Coverage | What it adds | Licence | Access | Fit |
|---|---|---|---|---|---|
| USDA NAIP via USGS — **in use** | CONUS | 0.6–1 m aerial imagery | Public domain | ArcGIS ImageServer | ★★★ |
| USGS National Map topo base map (USGSTopo) | US | Topo-style base map with contours and names | Public domain | Tile service | ★★★ |
| USGS Imagery Only / ImageryTopo | US | Alternative imagery mosaic and imagery + labels | Public domain | Tile service | ★★ |
| USGS historical topo maps (HTMC) | US | Old mine shafts, trails and structures missing from new maps | Public domain | GeoTIFF per quad | ★ |
| Sentinel-2 L2A (10 m) | Global, ~5-day revisit | Recent imagery (weeks old, not NAIP's 2–3 years): flood/fire/storm change; pairs with the Compare slider | Copernicus free & open | STAC + COGs on AWS (Earth Search) | ★★ |
| Landsat 8/9 C2 L2 (30 m) | Global, 8-day | Change detection, burn scars | Public domain | STAC + COGs on AWS | ★ |
| Harmonized Landsat-Sentinel (HLS) | Global | Combined 30 m with frequent revisit | Public domain | Earthdata COGs | ★ |
| EOX Sentinel-2 cloudless 2016 | Global | Cloud-free global base map | CC BY 4.0 (2016 only; later years are NC — avoid) | WMTS | ★ |
| State orthoimagery (e.g. Illinois ISGS, Indiana IndianaMap) | Per state | Often 15–30 cm leaf-off imagery | Mostly public domain (check per state) | State WMTS / ImageServer | ★★ |
| Maxar / Planet open-data events programmes | Disaster areas only | Very-high-resolution post-disaster imagery | Mostly CC BY-NC (check; NC is out) | STAC / S3 | ★ |
| NOAA NGS emergency response imagery | Post-hurricane US | Post-storm aerials of damaged coast | Public domain | Tile service | ★★ |
| OpenTopoMap tiles | Global | Topo-style rendering of OSM + SRTM | CC BY-SA (tile usage policy forbids bulk) | Rendering it ourselves would be OK; bulk download is not | ★ |

### C. Aviation (CAP-specific)
| Dataset | Coverage | What it adds | Licence | Access | Fit |
|---|---|---|---|---|---|
| FAA VFR Sectional + Terminal Area charts | US | The chart aircrews fly with, offline | Public domain | GeoTIFF, 56-day cycle | ★★★ |
| FAA IFR Enroute Low charts | US | Airways and MEAs for IFR legs | Public domain | GeoTIFF | ★ |
| FAA Helicopter route charts | Major metros | Low-level helicopter routes | Public domain | GeoTIFF | ★ |
| FAA Digital Obstacle File (DOF) | US | Towers, stacks, turbines with AGL/MSL heights | Public domain | CSV, 56-day | ★★★ |
| FAA NASR: airports, heliports, runways, navaids | US | Landing zones, helipads, frequencies | Public domain | 28-day CSV subscription | ★★★ |
| FAA airspace (Class B/C/D/E, SUA) | US | Airspace boundaries as vectors | Public domain | AIS open data (ArcGIS) / NASR | ★★ |
| FAA TFRs | US | Temporary flight restrictions (live; snapshot at capture time) | Public domain | XML / GeoJSON feed | ★★ |
| FCC Antenna Structure Registration (ASR) | US | Registered towers with heights; cross-checks DOF | Public domain | Bulk download | ★★ |
| USGS Wind Turbine Database | US | Every utility-scale turbine with height | Public domain | API / CSV | ★★ |
| OurAirports | Global | Airports and runways outside the US | Public domain | CSV | ★ |
| OpenAIP | Global | Airspace and navaids worldwide | CC BY-NC (check; NC is out) | API | ★ |
| **Derived:** CAP grid / USNG / MGRS lines | Anywhere | Search grids with labels (CAP grids are sectional-based 15′×15′, quartered) | Ours | Generated | ★★★ |

### D. Hydrography and water
| Dataset | Coverage | What it adds | Licence | Access | Fit |
|---|---|---|---|---|---|
| USGS NHD → 3D Hydrography Program (3DHP) | US | Named streams, intermittent drainages, springs; far denser than OSM in rural areas | Public domain | TNM ArcGIS REST by bbox | ★★★ |
| USGS WBD (watershed boundaries) | US | Drainage basins: lost people follow drainages | Public domain | ArcGIS REST | ★★ |
| USGS NWIS stream gauges (live) | US | River stage and flow at capture time | Public domain | Water Services API | ★★ |
| NOAA NWM / AHPS flood forecasts | US | Forecast flood stage | Public domain | API (live) | ★ |
| FEMA National Flood Hazard Layer | US | Flood zones | Public domain | ArcGIS REST | ★★ |
| USFWS National Wetlands Inventory | US | Wetlands and marsh: slow going, hard to search | Public domain | WMS / ArcGIS REST | ★★ |
| National Inventory of Dams (USACE) | US | Dams with height and hazard class | Public domain | API / CSV | ★★ |
| NOAA ENC nautical charts | US waters | Depths, hazards, aids to navigation | Public domain | S-57 (needs GDAL) or NOAA chart-tile service | ★ |
| USCG Light List / aids to navigation | US | Buoys and lights | Public domain | CSV / feature service | ★ |

### E. Transportation and access
| Dataset | Coverage | What it adds | Licence | Access | Fit |
|---|---|---|---|---|---|
| OpenStreetMap via Geofabrik — **in use** | Global | Roads, trails, buildings, water, power | ODbL | PBF | ★★★ |
| USFS trails + roads, incl. Motor Vehicle Use Maps | National Forests | Official trail/road numbers, allowed vehicles, seasons | Public domain | USFS EDW ArcGIS REST | ★★★ |
| NPS trails, roads, facilities | National Parks | Official park trails, trailheads, shelters | Public domain | NPS ArcGIS / open data | ★★ |
| BLM roads and trails (GTLF) | BLM land | Routes on western public land | Public domain | BLM ArcGIS REST | ★★ |
| Census TIGER/Line roads + rails | US | Every named road, gap-filler for OSM | Public domain | Shapefile (needs a reader) / TIGERweb REST | ★★ |
| State DOT road centrelines + mileposts | Per state | Mile markers: callers often report "near mile 42" | Usually public domain | State ArcGIS REST | ★★ |
| Overture Maps transportation | Global | OSM-derived plus extras, normalised schema | ODbL | GeoParquet on S3 | ★ |
| National Address Database (US DOT) | Growing US coverage | Offline address points for point lookup | Public domain | Bulk CSV (large) | ★★ |
| OpenAddresses | Global (per source) | Address points | Per-source; mostly open (check) | Per-county files | ★★ |
| Railroad mileposts / grade crossings (FRA) | US | Crossing IDs used in emergency calls | Public domain | ArcGIS REST | ★ |

### F. Buildings, places and names
| Dataset | Coverage | What it adds | Licence | Access | Fit |
|---|---|---|---|---|---|
| Microsoft Global ML Building Footprints | Global | Fills rural gaps in OSM buildings | ODbL | GeoJSONL by quadkey | ★★ |
| Overture buildings | Global | OSM + ML + other sources, merged | ODbL | GeoParquet | ★★ |
| USA Structures (FEMA/ORNL) | US | Every structure >450 ft² with use type | Public domain | Bulk / ArcGIS | ★★ |
| Overture places (POIs) | Global | Businesses and landmarks | CDLA-Permissive 2.0 | GeoParquet | ★ |
| USGS GNIS geographic names | US | Official names: peaks, gaps, hollows, creeks | Public domain | Bulk text / TNM API | ★★★ |
| GeoNames | Global | Place names worldwide | CC BY 4.0 | Bulk / API | ★ |
| Wikidata places | Global | Landmarks with links | CC0 | SPARQL | ★ |

### G. Land cover, vegetation and ground conditions
| Dataset | Coverage | What it adds | Licence | Access | Fit |
|---|---|---|---|---|---|
| Annual NLCD (USGS, 30 m) | US | Forest / scrub / open / water / developed: drives probability of detection and lost-person behaviour | Public domain | MRLC WMS/WCS or COGs | ★★★ |
| ESA WorldCover (10 m) | Global | Same idea, finer, worldwide | CC BY 4.0 | COGs on AWS | ★★ |
| Dynamic World (10 m, near-real-time) | Global | Recent land cover | CC BY 4.0 | Earth Engine only (needs an account) | ★ |
| LANDFIRE fuels + canopy cover/height | US | Canopy density (spotting from the air), fire fuels | Public domain | Bulk / WCS | ★★ |
| NLCD tree canopy cover | US | % canopy: how much the aircrew can see | Public domain | COGs | ★★ |
| Meta / WRI global canopy height (1 m) | Global | Tree height | CC BY 4.0 | COGs on AWS | ★ |
| USDA SSURGO / gSSURGO soils | US | Mud, swamp and trafficability for ground teams | Public domain | WFS / bulk | ★ |
| USGS mineral resources + mine sites (MRDS, USMIN) | US | Mine shafts and adits: hazards and hiding places | Public domain | WFS / CSV | ★★ |
| USDA cropland data layer | US | Crop type: corn in August is a search problem | Public domain | WMS / COGs | ★ |

### H. Land ownership, boundaries and jurisdiction
| Dataset | Coverage | What it adds | Licence | Access | Fit |
|---|---|---|---|---|---|
| PAD-US (protected areas) | US | Who owns the land (NPS, USFS, BLM, state, private conserved) | Public domain | ArcGIS REST | ★★★ |
| Census county / place / tribal boundaries | US | Jurisdiction lines: which sheriff and which EMS | Public domain | TIGERweb REST | ★★ |
| USFS ranger districts + admin units | National Forests | Who to call on Forest Service land | Public domain | EDW ArcGIS | ★★ |
| BLM Surface Management Agency | West | Land manager per parcel | Public domain | ArcGIS REST | ★ |
| State parcel data | Many states | Landowner contact for access | Varies (check) | State portals | ★ |
| PSAP (911 centre) boundaries | US | Which dispatch centre covers the area | Check (moved after HIFLD) | HIFLD Next / FCC | ★★ |

### I. Infrastructure and emergency services
| Dataset | Coverage | What it adds | Licence | Access | Fit |
|---|---|---|---|---|---|
| HIFLD Next (community successor to HIFLD Open) | US | Hospitals, fire, EMS, law enforcement, shelters, cell towers… | Mixed per layer (check) | HIFLD Next / DataLumos archive / original agencies | ★★ |
| CMS hospitals + trauma centres | US | Where to take a found subject | Public domain | CSV / API | ★★★ |
| FAA heliports at hospitals (from NASR) | US | Medevac landing points | Public domain | NASR | ★★★ |
| FCC cell tower data (ASR + ULS) | US | Coverage reasoning for phone pings | Public domain | Bulk | ★★ |
| FCC broadband / mobile coverage maps | US | Where a subject's phone could have had signal | Public domain | Bulk / API | ★★ |
| EIA power plants + transmission lines | US | Power lines (wire strikes) and plants | Public domain | ArcGIS REST | ★★ |
| Pipelines (NPMS public viewer) | US | Pipeline corridors | Restricted (public view only) — likely out | — | ★ |
| American Red Cross shelters (open feed) | US | Shelters in disasters | Check | Feature service | ★ |

### J. Weather, hazards and events (live — snapshot at capture or a live CloudTAK overlay)
| Dataset | Coverage | What it adds | Licence | Access | Fit |
|---|---|---|---|---|---|
| NWS forecast + alerts | US | Forecast and warnings at capture time | Public domain | api.weather.gov | ★★ |
| NEXRAD radar mosaic | US | Precipitation | Public domain | Tile services (live) | ★ (live overlay) |
| NOAA HRRR model | US | Ceilings/visibility/wind forecast for sortie planning | Public domain | GRIB on AWS (needs a decoder) | ★ |
| NASA FIRMS active fire | Global | Fire detections | Public domain-like (attribution) | CSV / API | ★★ |
| NIFC fire perimeters | US | Current wildfire perimeters | Public domain | ArcGIS REST | ★★ |
| USGS earthquakes | Global | Recent quakes | Public domain | GeoJSON feed | ★ |
| NOAA storm reports / tornado tracks | US | Damage paths for post-storm searches | Public domain | CSV | ★ |
| Avalanche forecast zones (avalanche.org) | Mountain West | Danger zones for winter SAR | Check | API | ★ |
| Sun / moon / twilight tables | Anywhere | Light for night searches and NVG ops | Ours (computed) | Generated | ★★ |

### K. People and behaviour (planning context)
| Dataset | Coverage | What it adds | Licence | Access | Fit |
|---|---|---|---|---|---|
| Census population density (block level) | US | Where people are; where help might come from | Public domain | TIGERweb / API | ★ |
| WorldPop / GHSL population | Global | Same, worldwide | CC BY 4.0 | COGs | ★ |
| ISRID lost-person behaviour statistics | — | Distance rings by subject type | Proprietary (dbS Productions) — numbers only by permission | — | ★★ (if licensed) |
| **Derived:** IPP distance rings + probability-of-area grid | Anywhere | Search segments from the land-cover and terrain layers above | Ours | Generated | ★★ |

### Considered and ruled out
- **Google / Bing / Esri World Imagery, Mapbox satellite.** Their terms forbid offline caching (the plan's main blocker).
- **Non-commercial (NC) data:** EOX cloudless after 2016, OpenAIP, most Maxar/Planet event
  imagery. A package can be redistributed, so NC terms don't fit.
- **NOAA ENC as S-57.** Needs GDAL; revisit only through a tile service.
- **Tile-usage-policy sources** (openstreetmap.org tiles, OpenTopoMap tiles). We can render OSM
  ourselves, but bulk-downloading their tiles is against their policies.

### Suggested starting set
1. **FAA sectionals** · 2. **CAP grid overlay** · 3. **FAA obstacles (DOF)** · 4. **contours + hillshade from our DEM**
   — highest value for aircrews, all public domain or derived, three of the four are small.
2. Then **NHD/3DHP hydrography**, **Annual NLCD land cover**, **USFS trails/MVUM**, **GNIS names**, **PAD-US**.
3. Then the elevation work in Part 2 (3DEP 1 m, full-cell DTED, terrain in CloudTAK).

---

## Part 2 — plan: elevation in every TAK client

### Where it stands today
- **Service** (`layers/elevation.py`): AWS Terrain Tiles (Terrarium PNG) → a Mercator height
  mosaic → **DTED1/2 cells** + a **Float32 GeoTIFF**. Cells are void outside the drawn area. Failed
  tiles now get one automatic retry pass; any tile still failing fails the layer (a voided DTED
  cell is worse than a clear error).
- **Package**: `elevation/<name>-dted.zip` is `ignore="true"` on purpose. A generic import would
  replace a device's complete cell with a mostly-void one. The GeoTIFF is plain data for GIS.
- **ATAK plugin**: `DtedInstaller` merges the cells into `atak/DTED/…`, **filling voids only**.
- **WinTAK plugin**: the same merge into `C:\ProgramData\WinTAK\DTED`, then refreshes WinTAK's
  `IDtedSourcesManager`.
- **CloudTAK**: no elevation on the map; point lookup returns one height from the service.
- **iTAK, TAK Server, TAK Aware and plain data-package imports**: get no usable elevation.

### What's common to all clients (service work)
1. **Better source ladder.** The source is chosen per area, recorded in `stats.source` and in
   `ATTRIBUTION.txt`:
   USGS 3DEP 1 m (where lidar exists) → 3DEP 1/3″ → AWS Terrain Tiles (today) → Copernicus GLO-30
   outside the US. Optional bathymetry (NOAA CUDEM / GEBCO) for water areas.
   Needs a small pure-Python COG reader (tiled GeoTIFF + deflate/LZW). Pillow plus our own
   `formats/geotiff.py` covers most of it.
2. **"Full-cell" DTED mode** (new option `dted_cells: "area" | "full"`). Fetch the whole 1° cell,
   not just the area. At z12 that's roughly 150 Terrarium tiles per cell (DTED1); at z13 about 600
   (DTED2). The cell then has no voids, so it is **safe to import anywhere**. Full-cell DTED goes
   in the package as `ignore="false"`, which is what makes elevation work on clients without our
   plugin (iTAK, TAK Server Data Sync, plain ATAK/WinTAK import).
   The estimate shows the extra size. The area-only mode stays the default for ATAK/WinTAK with
   the plugin, since they merge.
3. **Derived products from the same mosaic**, each a separate choice:
   - **Hillshade** as MBTiles (multidirectional, 50 % alpha). It works as an imagery overlay
     everywhere and reads well under the Compare slider.
   - **Contours** as KMZ: 10/20/40 ft or m intervals picked from the zoom; index lines labelled.
   - **Slope shading** as MBTiles: >30° in amber, >40° in red, for ground-team routing and
     avalanche/landslide awareness.
   - **Web terrain tiles** (Terrarium PNG, signed like imagery tiles) at
     `/jobs/{id}/terrain/{z}/{x}/{y}`, for CloudTAK 3D terrain and hillshade.
4. **API**: `options.elevation_products: ["dted", "geotiff", "hillshade", "contours", "slope"]`
   and `options.dted_cells`. `links.terrain` + `links.terrain_info` sit next to `links.tiles`.
   This is additive, so `API_VERSION` doesn't change. `test_api.py` + `API.md` change first,
   then the clients, as CLAUDE.md requires.
5. **Tests**: COG reader against a fixture, full-cell DTED has no voids and is byte-exact to the
   writer, hillshade/contour golden tests, Java/C# fixtures regenerated
   (`python -m tests.make_atak_fixture`).

### ATAK (CIV/GOV/MIL 5.x, our plugin)
| Step | What | How |
|---|---|---|
| 1 | Keep the void-fill DTED merge | Already done; add a per-device setting for DTED1 vs DTED2 to save phone storage |
| 2 | Hillshade / slope overlays | Imported as MBTiles through the existing `PackageImporter` (ATAK reads MBTiles natively); they show up in Overlay Manager with an opacity slider |
| 3 | Contours | KMZ import, as with OSM today |
| 4 | Use the elevation | No code: ATAK's own tools (elevation readout, viewshed, height-above-terrain, terrain slope, 3D view) read the merged DTED. **Verify each one in airplane mode** (VERIFY.md step 11) |
| 5 | Full-cell option | Plugin setting "Install complete DTED cells" → request `dted_cells: "full"` when the device has no cell for that degree |
| 6 | Optional: 1 m local DEM | ATAK can't use 1 m DTED; keep the 1 m GeoTIFF for viewshed-by-plugin later. Out of scope for v1 |

### WinTAK (5.6, our plugin)
| Step | What | How |
|---|---|---|
| 1 | Keep the merge + `IDtedSourcesManager` refresh | Already done |
| 2 | Hillshade / slope / contours | Through WinTAK's import manager (same package entries as ATAK) |
| 3 | Use the elevation | WinTAK's elevation readout, line of sight and 3D read the DTED. Verify on WinTAK 5.6, and re-check AlephDockPane's imports when WinTAK updates |
| 4 | Full-cell option | The same setting as ATAK |

### iTAK (no plugin of ours)
| Step | What | How |
|---|---|---|
| 1 | Deliver complete cells | The package built with `dted_cells: "full"` and DTED `ignore="false"`, so a plain data-package import brings elevation without voids |
| 2 | Overlays | Hillshade and slope as MBTiles; contours as KMZ. Both are formats iTAK imports |
| 3 | Getting it to the phone | Download link (QR) from CloudTAK or the admin page, or TAK Server Data Sync (below) |
| 4 | **Verify first** | Which iTAK versions read DTED from a data package, where they store it, and whether a new cell replaces an existing one. Test on a device before promising it; if iTAK won't take DTED, it still gets hillshade + contours |

### CloudTAK (browser, our plugin)
| Step | What | How |
|---|---|---|
| 1 | "Elevation" dataset toggle | A fourth toggle next to Imagery / OSM / Photos: adds a MapLibre `raster-dem` source from `links.terrain` and a **hillshade** layer under the imagery |
| 2 | 3D terrain | A "3D" switch calls `map.setTerrain` with our source; the Compare overlay already copies terrain, so the slider keeps working in 3D. Must not fight CloudTAK's own terrain overlay: only offered when that's off |
| 3 | Contours | `links.contours` GeoJSON, drawn as lines with labels; added to the legend |
| 4 | Elevation profile | Draw a line → profile computed from the loaded DEM tiles (no server round-trip). Shows climb/descent for ground teams |
| 5 | Slope shading | Optional raster layer from the service, in the legend with its colour key |
| 6 | Point lookup | Answers from the capture's own DEM when the point is inside a shown capture (works if the service is slow); falls back to the API |

### TAK Server (Data Sync / missions)
| Step | What | How |
|---|---|---|
| 1 | Push the package to a mission | Plan Phase 5 ("Data Sync push"): service uploads the package to a mission chosen in the admin page |
| 2 | Only safe elevation | Full-cell DTED (`ignore="false"`) plus overlays; area-only DTED stays `ignore="true"` so no client gets void-holed cells |
| 3 | Federation | Nothing extra; a mission package federates like any other |

### infra-TAK host / field node
| Step | What | How |
|---|---|---|
| 1 | Elevation cache | Keep fetched Terrarium/3DEP tiles in the service cache (already per-tile) and pre-seed whole states for a field node with no internet |
| 2 | Admin page | Disk used by the cache, purge button, "pre-cache this state" action |

### Suggested order
1. Service: hillshade + contours + web terrain tiles (no new source needed). CloudTAK
   Elevation toggle and hillshade. ATAK/WinTAK get the overlays through the existing import.
2. Full-cell DTED option, then test it on iTAK and through TAK Server Data Sync.
3. 3DEP 1 m / 1/3″ and the COG reader; Copernicus outside the US.
4. CloudTAK 3D terrain + elevation profile; slope shading everywhere.

### Open questions for Jon
- Default DTED level on phones (DTED2 is ~25 MB per cell, DTED1 ~3 MB)?
- Is full-cell DTED (bigger downloads, slower captures) acceptable as the default for iTAK users?
- Which iTAK versions does CAP field? This decides step 4 of the iTAK plan.
- Contour units: feet (aviation and US topo) or metres (MGRS/military maps)?

Sources consulted (Nov 2026): FAA Digital Products (VFR raster charts); AWS Open Data Registry
(Copernicus DEM); Overture Maps FAQ; NAPSG Foundation and the Data Rescue Project on the HIFLD
Open shutdown and HIFLD Next. Other entries are from the agencies' published terms as of the
last check. Re-verify each one before building it.
