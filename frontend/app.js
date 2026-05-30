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
      activeView: 'requests',
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
      // SSE 实时推送相关
      sseSource: null,          // EventSource 实例
      sseConnected: false,      // SSE 连接状态
      sseEnabled: false,        // 是否已成功建立 SSE 连接（用于禁用轮询回退）
      recentEvents: [],         // 最近 10 条调度事件（前端展示用）
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
      // 多场景管理
      scenarioList: [],
      scenarioNewName: '',
      scenarioSaving: false,
      scenarioLoadingName: '',
      // 场景对比
      compareNameA: '',
      compareNameB: '',
      compareReport: null,
      comparing: false,
      // 请求列表分页与过滤
      reqPage: 1,
      reqPageSize: 20,
      reqTotal: 0,
      reqHasNext: false,
      reqItems: [],        // 当前页数据（来自 /api/v1/requests）
      reqFilterStatus: '',
      reqFilterDataType: '',
      reqFilterSatelliteId: '',
      reqSort: '-id',
      reqLoading: false,
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
      // 优先使用分页接口数据；若尚未加载则回退到 systemData.requests（Cesium 场景渲染用）
      if (this.reqItems.length > 0 || this.reqTotal > 0) {
        return this.reqItems;
      }
      const rows = Array.isArray(this.systemData.requests) ? this.systemData.requests : [];
      return rows
        .filter((req) => req.source !== 'background')
        .slice()
        .sort((a, b) => String(b.id || '').localeCompare(String(a.id || '')));
    },

    // 用于 Cesium 场景渲染的实时活跃请求（不受分页影响）
    activeRequestsForScene() {
      const rows = Array.isArray(this.systemData.requests) ? this.systemData.requests : [];
      return rows.filter((req) => req.source !== 'background');
    },

    recentRequests() {
      return this.requests.slice(0, 8);
    },

    reqTotalPages() {
      return this.reqPageSize > 0 ? Math.max(1, Math.ceil(this.reqTotal / this.reqPageSize)) : 1;
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
    // 先执行一次初始全量拉取
    this.refreshAll();
    this.refreshScenarios();
    this.refreshRequestList();
    // 尝试建立 SSE 连接；若浏览器不支持或服务端不可达则回退轮询
    if (typeof EventSource !== 'undefined') {
      this.initSSE();
    } else {
      this._startPolling();
    }
    window.addEventListener('resize', this.resizeViewer);
  },

  updated() {
    this.renderIcons();
  },

  beforeUnmount() {
    // 关闭 SSE 连接
    if (this.sseSource) {
      this.sseSource.close();
      this.sseSource = null;
    }
    // 关闭回退轮询（如果存在）
    if (this.refreshTimer) {
      window.clearInterval(this.refreshTimer);
      this.refreshTimer = null;
    }
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
      // 登录后自动在请求头携带 JWT（来自 localStorage）
      const token = (typeof localStorage !== 'undefined') ? localStorage.getItem('smartnode_token') : null;
      if (token && !headers['Authorization']) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      const response = await fetch(this.apiUrl(path), {
        ...options,
        headers,
      });

      const contentType = response.headers.get('content-type') || '';
      const payload = contentType.includes('application/json') ? await response.json() : await response.text();
      if (!response.ok) {
        const message = typeof payload === 'string'
          ? payload
          : (payload.message || payload.reject_reason || payload.error || '请求失败');
        throw new Error(message);
      }
      // 透明解包统一成功包络 {code:0, data, meta, request_id}
      if (payload && typeof payload === 'object' && payload.code === 0 && 'data' in payload) {
        return payload.data;
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

    // ── SSE 实时推送 ─────────────────────────────────────────────

    /**
     * 启动 SSE 连接，订阅 /api/v1/stream。
     * 成功后停止回退轮询；断线后自动重连（浏览器原生行为）。
     * 若服务端返回非 2xx 或 5 秒内未收到任何事件，则降级为轮询模式。
     */
    initSSE() {
      const url = this.apiUrl('/api/v1/stream');
      const es = new EventSource(url);
      this.sseSource = es;

      // 超时保护：5 秒内未收到任何 message 则降级为轮询
      let fallbackTimer = window.setTimeout(() => {
        if (!this.sseEnabled) {
          es.close();
          this.sseSource = null;
          this._startPolling();
        }
      }, 5000);

      es.addEventListener('snapshot', (e) => {
        try {
          const snap = JSON.parse(e.data);
          this._applySnapshot(snap);
        } catch (_) {}

        // 首次收到快照：确认 SSE 可用，取消降级定时器，停止任何已启动的轮询
        if (!this.sseEnabled) {
          this.sseEnabled = true;
          this.sseConnected = true;
          this.backendOnline = true;
          window.clearTimeout(fallbackTimer);
          if (this.refreshTimer) {
            window.clearInterval(this.refreshTimer);
            this.refreshTimer = null;
          }
        }
      });

      es.addEventListener('event', (e) => {
        try {
          const evt = JSON.parse(e.data);
          this.recentEvents = [evt, ...this.recentEvents].slice(0, 10);
        } catch (_) {}
      });

      es.onerror = () => {
        this.sseConnected = false;
        // EventSource 在断线后会自动尝试重连；若首次连接从未成功，降级轮询
        if (!this.sseEnabled) {
          window.clearTimeout(fallbackTimer);
          es.close();
          this.sseSource = null;
          this._startPolling();
        }
      };
    },

    /**
     * 将 SSE snapshot 事件的内容应用到 Vue 响应式数据中。
     * snapshot 结构与 /api/data 返回的结构兼容。
     */
    _applySnapshot(snap) {
      if (!snap || typeof snap !== 'object') return;
      this.systemData = snap;
      this.updateScene();
    },

    /**
     * 启动 2 秒轮询回退（在 SSE 不可用时使用）。
     */
    _startPolling() {
      if (this.refreshTimer) return; // 已在运行
      this.refreshTimer = window.setInterval(() => {
        this.refreshAll();
        this.refreshRequestList();
      }, 2000);
    },

    // ── 分页请求列表 ─────────────────────────────────────────────
    async refreshRequestList() {
      this.reqLoading = true;
      try {
        const params = new URLSearchParams();
        params.set('page', String(this.reqPage));
        params.set('page_size', String(this.reqPageSize));
        params.set('sort', this.reqSort);
        if (this.reqFilterStatus) params.set('status', this.reqFilterStatus);
        if (this.reqFilterDataType) params.set('data_type', this.reqFilterDataType);
        if (this.reqFilterSatelliteId) params.set('satellite_id', this.reqFilterSatelliteId);

        // fetchJson 对统一包络自动解包，返回 data 字段（即 items 数组）
        // 但这里需要同时获取 meta，需要绕过自动解包
        const url = `/api/v1/requests?${params.toString()}`;
        const resp = await fetch(this.apiUrl(url), {
          headers: { 'Content-Type': 'application/json' },
        });
        const payload = await resp.json();
        if (payload && payload.code === 0) {
          this.reqItems = Array.isArray(payload.data) ? payload.data : [];
          const meta = payload.meta || {};
          this.reqTotal = Number(meta.total || 0);
          this.reqHasNext = Boolean(meta.has_next);
        }
      } catch (e) {
        this.setNotice('请求列表加载失败: ' + (e.message || e), 'error');
      } finally {
        this.reqLoading = false;
      }
    },

    async reqGoPage(page) {
      if (page < 1 || page > this.reqTotalPages) return;
      this.reqPage = page;
      await this.refreshRequestList();
    },

    async reqPrevPage() {
      if (this.reqPage > 1) await this.reqGoPage(this.reqPage - 1);
    },

    async reqNextPage() {
      if (this.reqHasNext) await this.reqGoPage(this.reqPage + 1);
    },

    async applyReqFilters() {
      this.reqPage = 1;
      await this.refreshRequestList();
    },

    resetReqFilters() {
      this.reqFilterStatus = '';
      this.reqFilterDataType = '';
      this.reqFilterSatelliteId = '';
      this.reqSort = '-id';
      this.reqPage = 1;
      this.refreshRequestList();
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

      this.activeRequestsForScene
        .filter((req) => req.status === 'transmitting')
        .slice(0, 24)
        .forEach((req) => {
          const satellite = satMap.get(req.satellite_id);
          if (!satellite) return;

          this.drawRequestLinks(req, satellite, geoMap, gsMap, linkColor);
        });

      this.viewer.scene.requestRender();
    },

    drawRequestLinks(req, satellite, geoMap, gsMap, color) {
      const groundStation = req.selected_ground_station
        ? gsMap.get(req.selected_ground_station)
        : null;
      const firstRelay = req.selected_relay
        ? geoMap.get(req.selected_relay)
        : null;
      const secondRelay = req.selected_relay2
        ? geoMap.get(req.selected_relay2)
        : null;

      if (firstRelay && secondRelay) {
        this.drawLink(satellite, firstRelay, color);
        this.drawLink(firstRelay, secondRelay, color);
        if (groundStation) {
          this.drawLink(secondRelay, groundStation, color);
        }
        return;
      }

      if (firstRelay) {
        this.drawLink(satellite, firstRelay, color);
        if (groundStation) {
          this.drawLink(firstRelay, groundStation, color);
        }
        return;
      }

      if (groundStation && req.transmission_method === 'direct') {
        this.drawLink(satellite, groundStation, color);
      }
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

    // ── 多场景管理 ──────────────────────────────────────────────────
    async refreshScenarios() {
      try {
        const items = await this.fetchJson('/api/scenarios');
        this.scenarioList = Array.isArray(items) ? items : [];
      } catch (e) {
        this.setNotice('场景列表加载失败: ' + (e.message || e), 'error');
      }
    },

    async saveNamedScenario() {
      const name = (this.scenarioNewName || '').trim();
      if (!name) {
        this.setNotice('请输入场景名称', 'error');
        return;
      }
      this.scenarioSaving = true;
      try {
        await this.fetchJson('/api/scenarios', {
          method: 'POST',
          body: JSON.stringify({ name }),
        });
        this.setNotice(`场景 "${name}" 已保存`);
        this.scenarioNewName = '';
        await this.refreshScenarios();
      } catch (e) {
        this.setNotice('场景保存失败: ' + (e.message || e), 'error');
      } finally {
        this.scenarioSaving = false;
      }
    },

    async activateScenario(name) {
      this.scenarioLoadingName = name;
      try {
        await this.fetchJson(`/api/scenarios/${encodeURIComponent(name)}/activate`, {
          method: 'POST',
        });
        this.setNotice(`已切换到场景 "${name}"`);
        this.resourceFormReady = false;
        await this.refreshAll();
      } catch (e) {
        this.setNotice('场景切换失败: ' + (e.message || e), 'error');
      } finally {
        this.scenarioLoadingName = '';
      }
    },

    async setBaseline(name) {
      try {
        await this.fetchJson(`/api/scenarios/${encodeURIComponent(name)}/baseline`, {
          method: 'POST',
        });
        this.setNotice(`场景 "${name}" 已设为基线`);
        await this.refreshScenarios();
      } catch (e) {
        this.setNotice('设置基线失败: ' + (e.message || e), 'error');
      }
    },

    async deleteScenario(name) {
      if (!window.confirm(`确认删除场景 "${name}"？`)) return;
      try {
        await this.fetchJson(`/api/scenarios/${encodeURIComponent(name)}`, {
          method: 'DELETE',
        });
        this.setNotice(`场景 "${name}" 已删除`);
        // 清理对比选择
        if (this.compareNameA === name) this.compareNameA = '';
        if (this.compareNameB === name) this.compareNameB = '';
        await this.refreshScenarios();
      } catch (e) {
        this.setNotice('删除失败: ' + (e.message || e), 'error');
      }
    },

    async runCompare() {
      const a = (this.compareNameA || '').trim();
      const b = (this.compareNameB || '').trim();
      if (!a || !b) {
        this.setNotice('请先选择两个场景再对比', 'error');
        return;
      }
      if (a === b) {
        this.setNotice('请选择不同的两个场景', 'error');
        return;
      }
      this.comparing = true;
      this.compareReport = null;
      try {
        const report = await this.fetchJson(
          `/api/scenario/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`
        );
        this.compareReport = report;
      } catch (e) {
        this.setNotice('对比失败: ' + (e.message || e), 'error');
      } finally {
        this.comparing = false;
      }
    },

    compareMetricClass(delta) {
      if (delta === null || delta === undefined) return '';
      if (delta > 0) return 'metric-up';
      if (delta < 0) return 'metric-down';
      return '';
    },

    formatMetricValue(value) {
      if (value === null || value === undefined) return '-';
      const n = Number(value);
      if (isNaN(n)) return '-';
      // 小值（0-1 区间）显示百分比，大值保留两位小数
      if (Math.abs(n) <= 1 && n !== 0) return (n * 100).toFixed(1) + '%';
      return n.toFixed(2);
    },

    labelDataType(type) {
      return DATA_TYPE_LABELS[type] || type || '未知';
    },

    labelStatus(status) {
      return STATUS_LABELS[status] || status || '未知';
    },

    labelLinkMode(req) {
      if (req.transmission_method === 'direct') return '直连';
      if (req.transmission_method === 'relay') return '中继';
      if (req.transmission_method === 'multi_relay') return '多跳';
      return '-';
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
