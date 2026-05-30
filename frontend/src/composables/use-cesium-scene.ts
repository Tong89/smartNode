/**
 * useCesiumScene — composable that owns Cesium viewer lifecycle and scene rendering.
 *
 * Returns:
 *   cesiumReady         — ref<boolean>  whether Cesium Viewer was initialised successfully
 *   showCoverage        — ref<boolean>  whether coverage footprint layer is visible
 *   mapMode             — ref<'2D'|'3D'>  current map display mode
 *   initCesium          — call once (mounted) with a DOM element id
 *   updateScene         — call whenever satellite / gs / relay / request data changes
 *   resizeViewer        — call on window resize or layout change
 *   destroyViewer       — call in beforeUnmount
 *   toggleCoverageLayer — toggle coverage footprint visibility
 *   toggleMapMode       — switch between 2D and 3D display modes
 */

import { ref } from 'vue';

/** localStorage key for persisting map mode across sessions */
const MAP_MODE_STORAGE_KEY = 'smartnode_map_mode';
import type { Satellite, GroundStation, GeoRelay, TransmissionRequest } from '../types/api';

declare const window: Window & {
  Cesium?: typeof import('cesium');
};

type CesiumType = typeof import('cesium');

interface SceneData {
  satellites: Satellite[];
  groundStations: GroundStation[];
  geoRelays: GeoRelay[];
  activeRequests: TransmissionRequest[];
}

/**
 * Compute the ground coverage radius (in meters) for a satellite/relay
 * given its orbital altitude and minimum elevation angle.
 *
 * Geometry (spherical Earth):
 *   Earth radius R_E = 6_371_000 m
 *   Satellite altitude h (m above surface)
 *   Minimum elevation angle ε (degrees)
 *
 *   Nadir half-angle ρ satisfies:  cos(ρ) = R_E / (R_E + h)
 *   Earth central angle λ = 90° − ε − ρ
 *   Ground coverage radius = R_E × λ (in radians)
 */
function computeCoverageRadius(altitudeM: number, minElevationDeg: number): number {
  const R_E = 6_371_000; // Earth radius in metres
  const h = Math.max(altitudeM, 0);
  const cosNadir = R_E / (R_E + h);
  const nadirRad = Math.acos(Math.min(1, cosNadir));
  const minElRad = (minElevationDeg * Math.PI) / 180;
  const earthCentralAngleRad = Math.max(0, Math.PI / 2 - minElRad - nadirRad);
  return R_E * earthCentralAngleRad;
}

export function useCesiumScene() {
  const cesiumReady = ref(false);
  /** Whether the coverage footprint layer (LEO circles + GEO rings) is visible */
  const showCoverage = ref(true);

  /**
   * Current map display mode: '3D' (default) or '2D' (flat map).
   * Persisted to localStorage so the user's last choice is remembered.
   */
  const storedMode = typeof localStorage !== 'undefined'
    ? (localStorage.getItem(MAP_MODE_STORAGE_KEY) as '2D' | '3D' | null)
    : null;
  const mapMode = ref<'2D' | '3D'>(storedMode === '2D' ? '2D' : '3D');

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let viewer: any = null;

  /**
   * Coverage footprint entity index:
   *   `leo-cov-{satId}`  → LEO satellite coverage ellipse
   *   `geo-vis-{relayId}` → GEO relay visibility ring ellipse
   */
  const _coverageIndex: Record<string, unknown> = {};

  function getCesium(): CesiumType | null {
    return (window as unknown as { Cesium?: CesiumType }).Cesium ?? null;
  }

  function initCesium(containerId: string): void {
    const Cesium = getCesium();
    if (!Cesium) {
      cesiumReady.value = false;
      return;
    }

    try {
      const imageryProvider = new Cesium.TileMapServiceImageryProvider({
        url: Cesium.buildModuleUrl('Assets/Textures/NaturalEarthII'),
      });

      viewer = new Cesium.Viewer(containerId, {
        imageryProvider,
        animation: false,
        timeline: false,
        baseLayerPicker: false,
        geocoder: false,
        homeButton: false,
        sceneModePicker: false,
        navigationHelpButton: false,
        fullscreenButton: false,
        infoBox: false,
        selectionIndicator: false,
        requestRenderMode: true,
      });

      viewer.scene.globe.enableLighting = false;
      viewer.scene.backgroundColor = Cesium.Color.fromCssColorString('#1f2b2d');
      viewer.camera.setView({
        destination: Cesium.Cartesian3.fromDegrees(110, 28, 22000000),
      });

      cesiumReady.value = true;

      // Apply the persisted map mode immediately after init
      if (mapMode.value === '2D') {
        // Use morphToColumbusView for a flat map (morphTo2D renders a rectangle around
        // the globe which is less useful; Columbus is the true flat "2D" projection).
        viewer.scene.morphTo2D(0);
      }
    } catch (error) {
      console.warn('Cesium 初始化失败:', error);
      cesiumReady.value = false;
    }
  }

  /**
   * Toggle between 2D (flat / Columbus-view) and 3D (globe) modes.
   * The transition is animated with a 1-second morph.
   * The selected mode is persisted to localStorage.
   */
  function toggleMapMode(): void {
    const Cesium = getCesium();
    if (!Cesium || !viewer || !cesiumReady.value) return;

    if (mapMode.value === '3D') {
      // Switch to 2D flat map
      viewer.scene.morphTo2D(1.0);
      mapMode.value = '2D';
    } else {
      // Switch back to 3D globe
      viewer.scene.morphTo3D(1.0);
      mapMode.value = '3D';
    }

    // Persist choice so it survives page reloads
    try {
      localStorage.setItem(MAP_MODE_STORAGE_KEY, mapMode.value);
    } catch (_) {
      // localStorage may be unavailable in some environments; ignore silently
    }

    // Ensure the scene re-renders after morph
    viewer.scene.requestRender();
  }

  function toCartesian(lon: number, lat: number, alt = 0) {
    const Cesium = getCesium()!;
    const safeLon = Number.isFinite(Number(lon)) ? Number(lon) : 0;
    const safeLat = Number.isFinite(Number(lat)) ? Number(lat) : 0;
    const safeAlt = Math.max(0, Math.min(Number(alt) || 0, 42000000));
    return Cesium.Cartesian3.fromDegrees(safeLon, safeLat, safeAlt);
  }

  function makeLabel(text: string, color: string, pixelOffsetY: number) {
    const Cesium = getCesium()!;
    return {
      text: String(text || ''),
      font: '12px sans-serif',
      fillColor: Cesium.Color.fromCssColorString(color),
      outlineColor: Cesium.Color.BLACK,
      outlineWidth: 2,
      style: Cesium.LabelStyle.FILL_AND_OUTLINE,
      pixelOffset: new Cesium.Cartesian2(0, pixelOffsetY),
      distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 26000000),
    };
  }

  function drawLink(
    from: { lon: number; lat: number; alt?: number },
    to: { lon: number; lat: number; alt?: number },
    color: unknown,
  ): void {
    viewer.entities.add({
      polyline: {
        positions: [
          toCartesian(from.lon, from.lat, from.alt || 0),
          toCartesian(to.lon, to.lat, to.alt || 0),
        ],
        width: 2.5,
        material: color,
      },
    });
  }

  function drawRequestLinks(
    req: TransmissionRequest & {
      satellite_id?: string;
      selected_ground_station?: string;
      selected_relay?: string;
      selected_relay2?: string;
      transmission_method?: string;
    },
    satellite: Satellite,
    geoMap: Map<string, GeoRelay & { lat?: number; alt?: number }>,
    gsMap: Map<string, GroundStation>,
    linkColor: unknown,
  ): void {
    const groundStation = req.selected_ground_station
      ? gsMap.get(req.selected_ground_station)
      : null;
    const firstRelay = req.selected_relay ? geoMap.get(req.selected_relay) : null;
    const secondRelay = req.selected_relay2 ? geoMap.get(req.selected_relay2) : null;

    if (firstRelay && secondRelay) {
      drawLink(satellite, firstRelay as unknown as { lon: number; lat: number; alt?: number }, linkColor);
      drawLink(
        firstRelay as unknown as { lon: number; lat: number; alt?: number },
        secondRelay as unknown as { lon: number; lat: number; alt?: number },
        linkColor,
      );
      if (groundStation) {
        drawLink(
          secondRelay as unknown as { lon: number; lat: number; alt?: number },
          groundStation,
          linkColor,
        );
      }
      return;
    }

    if (firstRelay) {
      drawLink(satellite, firstRelay as unknown as { lon: number; lat: number; alt?: number }, linkColor);
      if (groundStation) {
        drawLink(
          firstRelay as unknown as { lon: number; lat: number; alt?: number },
          groundStation,
          linkColor,
        );
      }
      return;
    }

    if (groundStation && req.transmission_method === 'direct') {
      drawLink(satellite, groundStation, linkColor);
    }
  }

  /**
   * Upsert a coverage ellipse (circle) entity on the ground surface.
   * Uses Cesium's `ellipse` primitive so the circle drapes on the globe.
   *
   * @param entityId   — unique entity id in the viewer
   * @param lat        — centre latitude (degrees)
   * @param lon        — centre longitude (degrees)
   * @param radiusM    — coverage radius in metres
   * @param fillColor  — semi-transparent fill colour
   * @param strokeColor — outline colour
   */
  function upsertCoverageEllipse(
    entityId: string,
    lat: number,
    lon: number,
    radiusM: number,
    fillColor: unknown,
    strokeColor: unknown,
  ): void {
    const Cesium = getCesium();
    if (!Cesium || !viewer) return;

    const position = toCartesian(lon, lat, 0);
    const r = Math.max(10_000, radiusM); // at least 10 km to stay visible

    if (_coverageIndex[entityId]) {
      // Update position and semi-axes of existing entity
      const existing = _coverageIndex[entityId] as { position: unknown; ellipse: { semiMajorAxis: number; semiMinorAxis: number; show: boolean } };
      existing.position = position;
      existing.ellipse.semiMajorAxis = r;
      existing.ellipse.semiMinorAxis = r;
      existing.ellipse.show = showCoverage.value;
    } else {
      const entity = viewer.entities.add({
        id: entityId,
        position,
        ellipse: {
          semiMajorAxis: r,
          semiMinorAxis: r,
          material: fillColor,
          outline: true,
          outlineColor: strokeColor,
          outlineWidth: 1.5,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
          show: showCoverage.value,
        },
      });
      _coverageIndex[entityId] = entity;
    }
  }

  /**
   * Update coverage footprints for all LEO satellites and GEO relay visibility rings.
   * Called as part of updateScene to keep footprints in sync with node positions.
   */
  function updateCoverageFootprints(
    satellites: Satellite[],
    geoRelays: GeoRelay[],
  ): void {
    const Cesium = getCesium();
    if (!Cesium || !viewer) return;

    // Colours: LEO footprint — warm amber, semi-transparent; GEO ring — cool blue
    const leoCoverageColor = Cesium.Color.fromCssColorString('#f5a623').withAlpha(0.13);
    const leoStrokeColor = Cesium.Color.fromCssColorString('#f5a623').withAlpha(0.55);
    const geoCoverageColor = Cesium.Color.fromCssColorString('#7ec8e3').withAlpha(0.10);
    const geoStrokeColor = Cesium.Color.fromCssColorString('#7ec8e3').withAlpha(0.50);

    const liveCoverageIds = new Set<string>();

    // LEO satellite coverage footprints
    satellites
      .filter((sat) => sat.type === 'LEO')
      .forEach((sat) => {
        const entityId = `leo-cov-${sat.id}`;
        liveCoverageIds.add(entityId);
        const minEl = sat.min_elevation ?? 10;
        const radius = computeCoverageRadius(sat.alt, minEl);
        upsertCoverageEllipse(entityId, sat.lat, sat.lon, radius, leoCoverageColor, leoStrokeColor);
      });

    // GEO relay visibility rings
    geoRelays.forEach((relay) => {
      const r = relay as GeoRelay;
      const entityId = `geo-vis-${relay.id}`;
      liveCoverageIds.add(entityId);
      const relayLat = r.lat ?? 0;
      const relayAlt = r.alt ?? 35_786_000;
      const minEl = r.coverage_min_elevation ?? 10;
      const radius = computeCoverageRadius(relayAlt, minEl);
      upsertCoverageEllipse(entityId, relayLat, relay.lon, radius, geoCoverageColor, geoStrokeColor);
    });

    // Remove stale coverage entities (satellites or relays that disappeared)
    for (const eid of Object.keys(_coverageIndex)) {
      if (!liveCoverageIds.has(eid)) {
        viewer.entities.remove(_coverageIndex[eid]);
        delete _coverageIndex[eid];
      }
    }
  }

  /**
   * Toggle the coverage footprint layer on/off.
   * Updates the `show` property of every coverage entity and triggers a re-render.
   */
  function toggleCoverageLayer(): void {
    showCoverage.value = !showCoverage.value;
    for (const entity of Object.values(_coverageIndex)) {
      const e = entity as { ellipse?: { show: boolean } };
      if (e.ellipse) {
        e.ellipse.show = showCoverage.value;
      }
    }
    if (viewer && cesiumReady.value) {
      viewer.scene.requestRender();
    }
  }

  function updateScene(data: SceneData): void {
    const Cesium = getCesium();
    if (!viewer || !cesiumReady.value || !Cesium) return;

    const satColor = Cesium.Color.fromCssColorString('#c47b10');
    const gsColor = Cesium.Color.fromCssColorString('#007f78');
    const geoColor = Cesium.Color.fromCssColorString('#2e6fa3');
    const linkColor = Cesium.Color.fromCssColorString('#f0c76b');

    viewer.entities.removeAll();
    // Coverage index entities were removed by removeAll; clear the index
    for (const key of Object.keys(_coverageIndex)) {
      delete _coverageIndex[key];
    }

    const satMap = new Map<string, Satellite>();
    const gsMap = new Map<string, GroundStation>();
    const geoMap = new Map<string, GeoRelay & { lat?: number; alt?: number }>();

    data.groundStations.forEach((station) => {
      gsMap.set(station.id, station);
      viewer.entities.add({
        id: `gs-${station.id}`,
        position: toCartesian(station.lon, station.lat, 0),
        point: {
          pixelSize: 8,
          color: gsColor,
          outlineColor: Cesium.Color.WHITE,
          outlineWidth: 1,
        },
        label: makeLabel(station.name, '#e7fff7', 16),
      });
    });

    data.geoRelays.forEach((relay) => {
      const r = relay as GeoRelay & { lat?: number; alt?: number };
      geoMap.set(relay.id, r);
      viewer.entities.add({
        id: `geo-${relay.id}`,
        position: toCartesian(relay.lon, r.lat ?? 0, r.alt ?? 35786000),
        point: {
          pixelSize: 11,
          color: geoColor,
          outlineColor: Cesium.Color.WHITE,
          outlineWidth: 1,
        },
        label: makeLabel(relay.name, '#e7f3ff', 18),
      });
    });

    data.satellites.forEach((satellite) => {
      satMap.set(satellite.id, satellite);
      viewer.entities.add({
        id: `sat-${satellite.id}`,
        position: toCartesian(satellite.lon, satellite.lat, satellite.alt),
        point: {
          pixelSize: satellite.type === 'LEO' ? 7 : 9,
          color: satColor,
          outlineColor: Cesium.Color.WHITE,
          outlineWidth: 1,
        },
        label: makeLabel(satellite.id, '#fff3db', 14),
      });
    });

    data.activeRequests
      .filter((req) => req.status === 'transmitting')
      .slice(0, 24)
      .forEach((req) => {
        const extReq = req as typeof req & { satellite_id?: string };
        const satellite = extReq.satellite_id ? satMap.get(extReq.satellite_id) : null;
        if (!satellite) return;
        drawRequestLinks(extReq as Parameters<typeof drawRequestLinks>[0], satellite, geoMap, gsMap, linkColor);
      });

    // Draw coverage footprints (LEO) and visibility rings (GEO) on top
    updateCoverageFootprints(data.satellites, data.geoRelays);

    viewer.scene.requestRender();
  }

  function resizeViewer(): void {
    if (viewer && cesiumReady.value) {
      viewer.resize();
      viewer.scene.requestRender();
    }
  }

  function destroyViewer(): void {
    if (viewer && !viewer.isDestroyed()) {
      viewer.destroy();
    }
    viewer = null;
  }

  return {
    cesiumReady,
    showCoverage,
    mapMode,
    initCesium,
    updateScene,
    resizeViewer,
    destroyViewer,
    toggleCoverageLayer,
    toggleMapMode,
  };
}
