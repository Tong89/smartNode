const DATA_TYPE_LABELS = {
  TASK_CMD: '任务指令',
  INTEL: '情报信息',
  DATA_SLICE: '数据切片',
  RAW_IMAGE: '原始影像',
};

const STATUS_LABELS = {
  pending: '排队',
  accepted: '等待',
  transmitting: '传输',
  completed: '完成',
  rejected: '拒绝',
};

function resolveApiBase() {
  const params = new URLSearchParams(window.location.search);
  const configured = params.get('api') || localStorage.getItem('space_api_base');
  if (configured) {
    return configured.replace(/\/$/, '');
  }

  if (window.location.protocol === 'file:' || (window.location.port && window.location.port !== '5000')) {
    return 'http://127.0.0.1:5000';
  }

  return '';
}

const app = Vue.createApp({
  data() {
    const apiBase = resolveApiBase();
    return {
      apiBase,
      apiBaseDraft: apiBase || window.location.origin,
      activeView: 'overview',
      backendOnline: false,
      cesiumReady: false,
      viewer: null,
      systemData: {},
      systemInfo: {},
      resourceStatus: {},
      resourceUtilization: {},
      notice: '',
      noticeType: 'success',
      submitting: false,
      refreshing: false,
      resourceFormReady: false,
      refreshTimer: null,
      requestForm: {
        data_type: 'DATA_SLICE',
        data_size: 120,
        priority: 5,
        max_delay: 600,
        satellite_id: '',
        ground_station_id: '',
      },
      resourceForm: {
        ground_station_count: 0,
        leo_satellite_count: 0,
      },
    };
  },

  computed: {
    systemTime() {
      return Number(this.systemData.time || 0);
    },

    stats() {
      return this.systemData.stats || {};
    },

    satellites() {
      return Array.isArray(this.systemData.satellites) ? this.systemData.satellites : [];
    },

    leoSatellites() {
      return this.satellites.filter((sat) => sat.type === 'LEO');
    },

    groundStations() {
      return Array.isArray(this.systemData.ground_stations) ? this.systemData.ground_stations : [];
    },

    geoRelays() {
      return Array.isArray(this.systemData.geo_relays) ? this.systemData.geo_relays : [];
    },

    requests() {
      const rows = Array.isArray(this.systemData.requests) ? this.systemData.requests : [];
      return rows
        .filter((req) => req.source !== 'background')
        .slice()
        .sort((a, b) => String(b.id || '').localeCompare(String(a.id || '')));
    },

    recentRequests() {
      return this.requests.slice(0, 8);
    },

    satelliteCount() {
      return this.satellites.length;
    },

    groundStationCount() {
      return this.groundStations.length;
    },

    geoRelayCount() {
      return this.geoRelays.length;
    },

    dataTypeOptions() {
      const apiTypes = this.systemInfo.data_types || {};
      const keys = Object.keys(apiTypes);
      const sourceKeys = keys.length ? keys : Object.keys(DATA_TYPE_LABELS);
      return sourceKeys.map((key) => ({
        value: key,
        label: DATA_TYPE_LABELS[key] || apiTypes[key]?.name || key,
      }));
    },

    utilizationRows() {
      const summary = this.resourceStatus.summary || {};
      return [
        { key: 'satellites', label: '卫星资源', value: Number(summary.satellites_utilization || 0) },
        { key: 'ground', label: '地面站资源', value: Number(summary.ground_stations_utilization || 0) },
        { key: 'geo', label: '中继资源', value: Number(summary.geo_relays_utilization || 0) },
        { key: 'overall', label: '综合占用', value: Number(summary.overall_utilization || 0) },
      ];
    },
  },

  mounted() {
    this.renderIcons();
    this.initCesium();
    this.refreshAll();
    this.refreshTimer = window.setInterval(this.refreshAll, 2000);
    window.addEventListener('resize', this.resizeViewer);
  },

  updated() {
    this.renderIcons();
  },

  beforeUnmount() {
    window.clearInterval(this.refreshTimer);
    window.removeEventListener('resize', this.resizeViewer);
    if (this.viewer && !this.viewer.isDestroyed()) {
      this.viewer.destroy();
    }
  },

  methods: {
    renderIcons() {
      if (window.lucide) {
        window.lucide.createIcons();
      }
    },

    setView(view) {
      this.activeView = view;
      this.$nextTick(() => {
        this.renderIcons();
        this.resizeViewer();
      });
    },

    saveApiBase() {
      const value = (this.apiBaseDraft || '').trim().replace(/\/$/, '');
      this.apiBase = value === window.location.origin ? '' : value;
      if (this.apiBase) {
        localStorage.setItem('space_api_base', this.apiBase);
      } else {
        localStorage.removeItem('space_api_base');
      }
      this.setNotice('API 地址已更新');
      this.refreshAll();
    },

    apiUrl(path) {
      return `${this.apiBase}${path}`;
    },

    async fetchJson(path, options = {}) {
      const headers = {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      };
      const response = await fetch(this.apiUrl(path), {
        ...options,
        headers,
      });

      const contentType = response.headers.get('content-type') || '';
      const payload = contentType.includes('application/json') ? await response.json() : await response.text();
      if (!response.ok) {
        const message = typeof payload === 'string' ? payload : payload.error || payload.message || '请求失败';
        throw new Error(message);
      }
      return payload;
    },

    async refreshAll() {
      if (this.refreshing) return;
      this.refreshing = true;
      try {
        const [health, data, info, status, utilization] = await Promise.allSettled([
          this.fetchJson('/api/health'),
          this.fetchJson('/api/data'),
          this.fetchJson('/api/system_info'),
          this.fetchJson('/api/resource_status'),
          this.fetchJson('/api/resource_utilization'),
        ]);

        this.backendOnline = health.status === 'fulfilled';

        if (data.status === 'fulfilled') {
          this.systemData = data.value || {};
          this.updateScene();
        }

        if (info.status === 'fulfilled') {
          this.systemInfo = info.value || {};
          this.syncResourceForm();
        }

        if (status.status === 'fulfilled') {
          this.resourceStatus = status.value || {};
        }

        if (utilization.status === 'fulfilled') {
          this.resourceUtilization = utilization.value || {};
        }
      } catch (error) {
        this.backendOnline = false;
        this.setNotice(error.message || '刷新失败', 'error');
      } finally {
        this.refreshing = false;
      }
    },

    syncResourceForm() {
      if (this.resourceFormReady) return;
      this.resourceForm.ground_station_count = Number(this.systemInfo.ground_station_count || this.groundStationCount || 0);
      this.resourceForm.leo_satellite_count = Number(this.systemInfo.leo_satellite_count || this.leoSatellites.length || 0);
      this.resourceFormReady = true;
    },

    initCesium() {
      if (!window.Cesium) {
        this.cesiumReady = false;
        return;
      }

      try {
        const imageryProvider = new Cesium.TileMapServiceImageryProvider({
          url: Cesium.buildModuleUrl('Assets/Textures/NaturalEarthII'),
        });

        this.viewer = new Cesium.Viewer('cesiumContainer', {
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

        this.viewer.scene.globe.enableLighting = false;
        this.viewer.scene.backgroundColor = Cesium.Color.fromCssColorString('#1f2b2d');
        this.viewer.camera.setView({
          destination: Cesium.Cartesian3.fromDegrees(110, 28, 22000000),
        });

        this.cesiumReady = true;
      } catch (error) {
        console.warn('Cesium 初始化失败:', error);
        this.cesiumReady = false;
      }
    },

    updateScene() {
      if (!this.viewer || !this.cesiumReady || !window.Cesium) return;

      const satColor = Cesium.Color.fromCssColorString('#c47b10');
      const gsColor = Cesium.Color.fromCssColorString('#007f78');
      const geoColor = Cesium.Color.fromCssColorString('#2e6fa3');
      const linkColor = Cesium.Color.fromCssColorString('#f0c76b');

      this.viewer.entities.removeAll();

      const satMap = new Map();
      const gsMap = new Map();
      const geoMap = new Map();

      this.groundStations.forEach((station) => {
        gsMap.set(station.id, station);
        this.viewer.entities.add({
          id: `gs-${station.id}`,
          position: this.toCartesian(station.lon, station.lat, 0),
          point: {
            pixelSize: 8,
            color: gsColor,
            outlineColor: Cesium.Color.WHITE,
            outlineWidth: 1,
          },
          label: this.makeLabel(station.name, '#e7fff7', 16),
        });
      });

      this.geoRelays.forEach((relay) => {
        geoMap.set(relay.id, relay);
        this.viewer.entities.add({
          id: `geo-${relay.id}`,
          position: this.toCartesian(relay.lon, relay.lat, relay.alt),
          point: {
            pixelSize: 11,
            color: geoColor,
            outlineColor: Cesium.Color.WHITE,
            outlineWidth: 1,
          },
          label: this.makeLabel(relay.name, '#e7f3ff', 18),
        });
      });

      this.satellites.forEach((satellite) => {
        satMap.set(satellite.id, satellite);
        this.viewer.entities.add({
          id: `sat-${satellite.id}`,
          position: this.toCartesian(satellite.lon, satellite.lat, satellite.alt),
          point: {
            pixelSize: satellite.type === 'LEO' ? 7 : 9,
            color: satColor,
            outlineColor: Cesium.Color.WHITE,
            outlineWidth: 1,
          },
          label: this.makeLabel(satellite.id, '#fff3db', 14),
        });
      });

      this.requests
        .filter((req) => req.status === 'transmitting')
        .slice(0, 24)
        .forEach((req) => {
          const satellite = satMap.get(req.satellite_id);
          if (!satellite) return;

          if (req.selected_relay && geoMap.has(req.selected_relay)) {
            this.drawLink(satellite, geoMap.get(req.selected_relay), linkColor);
          }

          if (req.selected_relay2 && geoMap.has(req.selected_relay2)) {
            this.drawLink(satellite, geoMap.get(req.selected_relay2), linkColor);
          }

          if (req.selected_ground_station && gsMap.has(req.selected_ground_station)) {
            this.drawLink(satellite, gsMap.get(req.selected_ground_station), linkColor);
          }
        });

      this.viewer.scene.requestRender();
    },

    makeLabel(text, color, pixelOffsetY) {
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
    },

    drawLink(from, to, color) {
      this.viewer.entities.add({
        polyline: {
          positions: [
            this.toCartesian(from.lon, from.lat, from.alt || 0),
            this.toCartesian(to.lon, to.lat, to.alt || 0),
          ],
          width: 2.5,
          material: color,
        },
      });
    },

    toCartesian(lon, lat, alt = 0) {
      const safeLon = Number.isFinite(Number(lon)) ? Number(lon) : 0;
      const safeLat = Number.isFinite(Number(lat)) ? Number(lat) : 0;
      const safeAlt = Math.max(0, Math.min(Number(alt) || 0, 42000000));
      return Cesium.Cartesian3.fromDegrees(safeLon, safeLat, safeAlt);
    },

    resizeViewer() {
      if (this.viewer && this.cesiumReady) {
        this.viewer.resize();
        this.viewer.scene.requestRender();
      }
    },

    async submitRequest() {
      this.submitting = true;
      try {
        const selectedGroundStations = this.requestForm.ground_station_id
          ? [this.requestForm.ground_station_id]
          : [];

        const payload = {
          data_type: this.requestForm.data_type,
          data_size: Number(this.requestForm.data_size),
          priority: Number(this.requestForm.priority),
          max_delay: Number(this.requestForm.max_delay),
          selected_ground_stations: selectedGroundStations,
        };

        if (this.requestForm.satellite_id) {
          payload.satellite_id = this.requestForm.satellite_id;
        }

        const result = await this.fetchJson('/api/request', {
          method: 'POST',
          body: JSON.stringify(payload),
        });

        if (result && result.status === 'rejected') {
          this.setNotice(`请求被拒绝：${result.reject_reason || '资源暂不可用'}`, 'error');
        } else {
          this.setNotice(`请求已提交：${result.id || '已进入队列'}`);
        }

        await this.refreshAll();
      } catch (error) {
        this.setNotice(error.message || '提交失败', 'error');
      } finally {
        this.submitting = false;
      }
    },

    async updateGroundStations() {
      await this.updateResource('/api/update_ground_stations', {
        count: Number(this.resourceForm.ground_station_count),
      }, '地面站数量已更新');
    },

    async updateLeoSatellites() {
      await this.updateResource('/api/update_leo_satellites', {
        count: Number(this.resourceForm.leo_satellite_count),
      }, '卫星数量已更新');
    },

    async updateResource(path, payload, message) {
      try {
        await this.fetchJson(path, {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        this.setNotice(message);
        this.resourceFormReady = false;
        await this.refreshAll();
      } catch (error) {
        this.setNotice(error.message || '资源更新失败', 'error');
      }
    },

    setNotice(message, type = 'success') {
      this.notice = message;
      this.noticeType = type;
      window.clearTimeout(this.noticeTimer);
      this.noticeTimer = window.setTimeout(() => {
        this.notice = '';
      }, 4200);
    },

    labelDataType(type) {
      return DATA_TYPE_LABELS[type] || type || '未知';
    },

    labelStatus(status) {
      return STATUS_LABELS[status] || status || '未知';
    },

    formatProgress(progress) {
      const value = Number(progress || 0);
      return `${Math.max(0, Math.min(100, value)).toFixed(0)}%`;
    },

    formatTime(seconds) {
      const total = Math.max(0, Math.floor(Number(seconds || 0)));
      const hours = Math.floor(total / 3600);
      const minutes = Math.floor((total % 3600) / 60);
      const secs = total % 60;
      return [hours, minutes, secs].map((part) => String(part).padStart(2, '0')).join(':');
    },
  },
});

app.mount('#app');
