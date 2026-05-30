/**
 * useCesiumScene — composable that owns Cesium viewer lifecycle and scene rendering.
 *
 * Returns:
 *   cesiumReady  — ref<boolean>  whether Cesium Viewer was initialised successfully
 *   initCesium   — call once (mounted) with a DOM element id
 *   updateScene  — call whenever satellite / gs / relay / request data changes
 *   resizeViewer — call on window resize or layout change
 *   destroyViewer — call in beforeUnmount
 */

import { ref } from 'vue';
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

export function useCesiumScene() {
  const cesiumReady = ref(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let viewer: any = null;

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
    } catch (error) {
      console.warn('Cesium 初始化失败:', error);
      cesiumReady.value = false;
    }
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

  function updateScene(data: SceneData): void {
    const Cesium = getCesium();
    if (!viewer || !cesiumReady.value || !Cesium) return;

    const satColor = Cesium.Color.fromCssColorString('#c47b10');
    const gsColor = Cesium.Color.fromCssColorString('#007f78');
    const geoColor = Cesium.Color.fromCssColorString('#2e6fa3');
    const linkColor = Cesium.Color.fromCssColorString('#f0c76b');

    viewer.entities.removeAll();

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
    initCesium,
    updateScene,
    resizeViewer,
    destroyViewer,
  };
}
