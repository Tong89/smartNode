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
      // 2D/3D 地图模式：'3D'（默认）| '2D'（平面地图），持久化到 localStorage
      mapMode: localStorage.getItem('smartnode_map_mode') === '2D' ? '2D' : '3D',
      // Cesium 增量更新：实体索引表，避免每次 removeAll 重建场景
      _entityIndex: {},      // id -> Cesium.Entity，管理节点（卫星、地面站、中继）
      _linkIndex: {},        // linkKey -> Cesium.Entity，管理链路 polyline
      // 链路动画状态：流动动画偏移量与 rAF 句柄
      _linkAnimOffset: 0,    // 当前动画时间偏移（0–1 循环，用于 dashPattern 驱动流动效果）
      _linkAnimFrame: null,  // requestAnimationFrame 句柄，非 null 时表示动画循环运行
      _linkAnimRateMap: {},  // linkKey -> { rate, method }，缓存链路传输速率与方式
      // 轨道轨迹索引：satId -> { orbitEntity, groundEntity }
      _trackIndex: {},
      _tracksLoading: false,
      _tracksLastRefresh: 0,  // 上次刷新轨迹的仿真时刻（用于节流）
      // 覆盖足迹索引：entityId -> Cesium.Entity（LEO 覆盖足迹圆 & GEO 中继可见性圈）
      _coverageIndex: {},
      showCoverage: true,     // 覆盖图层开关（true = 显示）
      systemData: {},
      systemInfo: {},
      resourceStatus: {},
      resourceUtilization: {},
      resourceTimeline: null,   // 资源时间轴数据（来自 /api/resource_timeline）
      ganttHoveredEvent: null,  // 甘特图当前悬浮事件
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

    // ── 甘特图计算属性 ────────────────────────────────────────────────
    ganttTimeRange() {
      if (!this.resourceTimeline) return [0, 1];
      const [s, e] = this.resourceTimeline.time_range;
      return e > s ? [s, e] : [s, s + 1];
    },

    ganttRangeSpan() {
      return this.ganttTimeRange[1] - this.ganttTimeRange[0];
    },

    ganttTimeTicks() {
      const [start] = this.ganttTimeRange;
      const span = this.ganttRangeSpan;
      const count = 5;
      return Array.from({ length: count + 1 }, (_, i) => {
        const t = start + (span * i) / count;
        const pct = (i / count) * 100;
        return { t, pct, label: this.formatTime(t) };
      });
    },

    ganttGroups() {
      if (!this.resourceTimeline) return [];
      const result = [];
      const satRows = Object.entries(this.resourceTimeline.satellites || {})
        .filter(([, res]) => res.events.length > 0)
        .map(([id, res]) => ({ id, name: res.name, events: res.events }));
      if (satRows.length) result.push({ id: 'sat', label: '卫星 LEO', rows: satRows });

      const gsRows = Object.entries(this.resourceTimeline.ground_stations || {})
        .filter(([, res]) => res.events.length > 0)
        .map(([id, res]) => ({ id, name: res.name, events: res.events }));
      if (gsRows.length) result.push({ id: 'gs', label: '地面站', rows: gsRows });

      const geoRows = Object.entries(this.resourceTimeline.geo_relays || {})
        .filter(([, res]) => res.events.length > 0)
        .map(([id, res]) => ({ id, name: res.name, events: res.events }));
      if (geoRows.length) result.push({ id: 'geo', label: '中继 GEO', rows: geoRows });

      return result;
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
    // 取消链路动画循环
    if (this._linkAnimFrame !== null) {
      cancelAnimationFrame(this._linkAnimFrame);
      this._linkAnimFrame = null;
    }
    window.removeEventListener('resize', this.resizeViewer);
    if (this.viewer && !this.viewer.isDestroyed()) {
      this.viewer.destroy();
    }
    // 清空增量更新索引，防止后续残留引用
    this._entityIndex = {};
    this._linkIndex = {};
    this._trackIndex = {};
    this._coverageIndex = {};
    this._linkAnimRateMap = {};
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
        const [health, data, info, status, utilization, timeline] = await Promise.allSettled([
          this.fetchJson('/api/health'),
          this.fetchJson('/api/data'),
          this.fetchJson('/api/system_info'),
          this.fetchJson('/api/resource_status'),
          this.fetchJson('/api/resource_utilization'),
          this.fetchJson('/api/resource_timeline'),
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

        if (timeline.status === 'fulfilled') {
          this.resourceTimeline = timeline.value || null;
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

        // 若上次选择了 2D 模式，初始化后立即切换
        if (this.mapMode === '2D') {
          this.viewer.scene.morphTo2D(0);
        }
      } catch (error) {
        console.warn('Cesium 初始化失败:', error);
        this.cesiumReady = false;
      }
    },

    /**
     * 在 2D 平面地图与 3D 地球模式之间切换。
     * 使用 Cesium 内置的 morphTo2D / morphTo3D 完成平滑过渡动画（1 秒）。
     * 用户选择持久化到 localStorage，下次打开页面时自动恢复。
     */
    toggleMapMode() {
      if (!this.viewer || !this.cesiumReady || !window.Cesium) return;

      if (this.mapMode === '3D') {
        this.viewer.scene.morphTo2D(1.0);
        this.mapMode = '2D';
      } else {
        this.viewer.scene.morphTo3D(1.0);
        this.mapMode = '3D';
      }

      try {
        localStorage.setItem('smartnode_map_mode', this.mapMode);
      } catch (_) {
        // localStorage 在某些环境下不可用，忽略异常
      }

      this.viewer.scene.requestRender();
    },

    /**
     * 增量更新 Cesium 场景：对新增节点执行 add、对已有节点仅更新 position，
     * 对消失节点执行 remove，避免每次刷新调用 removeAll 导致的闪烁与卡顿。
     *
     * 索引表：
     *   _entityIndex  { id -> Entity }  管理卫星、地面站、GEO 中继节点
     *   _linkIndex    { linkKey -> Entity }  管理链路 polyline，按请求 id + 端点复用
     */
    updateScene() {
      if (!this.viewer || !this.cesiumReady || !window.Cesium) return;

      const satColor = Cesium.Color.fromCssColorString('#c47b10');
      const gsColor = Cesium.Color.fromCssColorString('#007f78');
      const geoColor = Cesium.Color.fromCssColorString('#2e6fa3');
      const linkColor = Cesium.Color.fromCssColorString('#f0c76b');

      // 收集本轮所有节点 id，用于事后清理已消失实体
      const liveNodeIds = new Set();
      const satMap = new Map();
      const gsMap = new Map();
      const geoMap = new Map();

      // ── 地面站 ──────────────────────────────────────────────────
      this.groundStations.forEach((station) => {
        const eid = `gs-${station.id}`;
        liveNodeIds.add(eid);
        gsMap.set(station.id, station);
        const pos = this.toCartesian(station.lon, station.lat, 0);

        if (this._entityIndex[eid]) {
          // 仅更新位置，保留其他属性引用
          this._entityIndex[eid].position = pos;
        } else {
          const entity = this.viewer.entities.add({
            id: eid,
            position: pos,
            point: {
              pixelSize: 8,
              color: gsColor,
              outlineColor: Cesium.Color.WHITE,
              outlineWidth: 1,
            },
            label: this.makeLabel(station.name, '#e7fff7', 16),
          });
          this._entityIndex[eid] = entity;
        }
      });

      // ── GEO 中继 ────────────────────────────────────────────────
      this.geoRelays.forEach((relay) => {
        const eid = `geo-${relay.id}`;
        liveNodeIds.add(eid);
        geoMap.set(relay.id, relay);
        const pos = this.toCartesian(relay.lon, relay.lat, relay.alt);

        if (this._entityIndex[eid]) {
          this._entityIndex[eid].position = pos;
        } else {
          const entity = this.viewer.entities.add({
            id: eid,
            position: pos,
            point: {
              pixelSize: 11,
              color: geoColor,
              outlineColor: Cesium.Color.WHITE,
              outlineWidth: 1,
            },
            label: this.makeLabel(relay.name, '#e7f3ff', 18),
          });
          this._entityIndex[eid] = entity;
        }
      });

      // ── 卫星 ────────────────────────────────────────────────────
      this.satellites.forEach((satellite) => {
        const eid = `sat-${satellite.id}`;
        liveNodeIds.add(eid);
        satMap.set(satellite.id, satellite);
        const pos = this.toCartesian(satellite.lon, satellite.lat, satellite.alt);

        if (this._entityIndex[eid]) {
          this._entityIndex[eid].position = pos;
        } else {
          const entity = this.viewer.entities.add({
            id: eid,
            position: pos,
            point: {
              pixelSize: satellite.type === 'LEO' ? 7 : 9,
              color: satColor,
              outlineColor: Cesium.Color.WHITE,
              outlineWidth: 1,
            },
            label: this.makeLabel(satellite.id, '#fff3db', 14),
          });
          this._entityIndex[eid] = entity;
        }
      });

      // ── 移除已消失的节点实体 ─────────────────────────────────────
      for (const eid of Object.keys(this._entityIndex)) {
        if (!liveNodeIds.has(eid)) {
          this.viewer.entities.remove(this._entityIndex[eid]);
          delete this._entityIndex[eid];
        }
      }

      // ── 链路增量更新 ─────────────────────────────────────────────
      const liveLinkKeys = new Set();
      this.activeRequestsForScene
        .filter((req) => req.status === 'transmitting')
        .slice(0, 24)
        .forEach((req) => {
          const satellite = satMap.get(req.satellite_id);
          if (!satellite) return;
          this.updateRequestLinks(req, satellite, geoMap, gsMap, liveLinkKeys);
        });

      // 移除已消失的链路实体
      for (const lkey of Object.keys(this._linkIndex)) {
        if (!liveLinkKeys.has(lkey)) {
          this.viewer.entities.remove(this._linkIndex[lkey]);
          delete this._linkIndex[lkey];
          delete this._linkAnimRateMap[lkey];
        }
      }

      // 启动链路流动动画循环（若尚未运行）
      if (liveLinkKeys.size > 0) {
        this._startLinkAnimation();
      } else {
        this._stopLinkAnimation();
      }

      // ── 覆盖足迹与可见性圈 ────────────────────────────────────────
      this.updateCoverageFootprints();

      this.viewer.scene.requestRender();

      // 轨道轨迹节流刷新：每隔约半个轨道周期（或首次）才重新采样
      this._refreshOrbitTracksIfNeeded();
    },

    /**
     * 为单条请求按需增量更新/创建链路 polyline 实体。
     * liveLinkKeys 用于记录本轮活跃的链路 key，以便事后清理。
     * 链路颜色由 transmission_method 决定，线宽由 transmission_rate 归一化映射。
     */
    updateRequestLinks(req, satellite, geoMap, gsMap, liveLinkKeys) {
      const groundStation = req.selected_ground_station
        ? gsMap.get(req.selected_ground_station)
        : null;
      const firstRelay = req.selected_relay
        ? geoMap.get(req.selected_relay)
        : null;
      const secondRelay = req.selected_relay2
        ? geoMap.get(req.selected_relay2)
        : null;

      const rate = Number(req.transmission_rate || 0);
      const method = req.transmission_method || 'direct';

      if (firstRelay && secondRelay) {
        this.upsertLink(`${req.id}:sat-relay1`, satellite, firstRelay, rate, method, liveLinkKeys);
        this.upsertLink(`${req.id}:relay1-relay2`, firstRelay, secondRelay, rate, method, liveLinkKeys);
        if (groundStation) {
          this.upsertLink(`${req.id}:relay2-gs`, secondRelay, groundStation, rate, method, liveLinkKeys);
        }
        return;
      }

      if (firstRelay) {
        this.upsertLink(`${req.id}:sat-relay1`, satellite, firstRelay, rate, method, liveLinkKeys);
        if (groundStation) {
          this.upsertLink(`${req.id}:relay1-gs`, firstRelay, groundStation, rate, method, liveLinkKeys);
        }
        return;
      }

      if (groundStation && method === 'direct') {
        this.upsertLink(`${req.id}:sat-gs`, satellite, groundStation, rate, method, liveLinkKeys);
      }
    },

    /**
     * 将传输速率（Mbps）归一化为链路线宽（1.5–6px）。
     * 使用对数映射，使低速率链路也有明显变化。
     * @param {number} rateMbps - 传输速率（Mbps）
     * @returns {number} 线宽（px）
     */
    _rateToLineWidth(rateMbps) {
      const MIN_W = 1.5;
      const MAX_W = 6.0;
      const MAX_RATE = 1000; // 参考最大速率 1000 Mbps
      if (!rateMbps || rateMbps <= 0) return MIN_W;
      // 对数归一化：log(1 + rate) / log(1 + MAX_RATE)
      const norm = Math.log1p(Math.min(rateMbps, MAX_RATE)) / Math.log1p(MAX_RATE);
      return MIN_W + norm * (MAX_W - MIN_W);
    },

    /**
     * 根据传输方式返回对应的链路颜色（Cesium.Color）。
     * - direct（直连）：金黄色
     * - relay（单中继）：青绿色
     * - multi_relay（多跳）：紫色
     * @param {string} method - 传输方式
     * @returns {Cesium.Color}
     */
    _methodToLinkColor(method) {
      if (!window.Cesium) return null;
      switch (method) {
        case 'relay':       return Cesium.Color.fromCssColorString('#3dcfc4'); // 青绿
        case 'multi_relay': return Cesium.Color.fromCssColorString('#b67cf6'); // 紫色
        default:            return Cesium.Color.fromCssColorString('#f0c76b'); // 金黄（直连）
      }
    },

    /**
     * 按 linkKey 复用已有的 polyline 实体；不存在时新建并注册到 _linkIndex。
     * 复用时更新两端点坐标与动画速率缓存，保持实体引用稳定。
     * 使用 PolylineGlowMaterialProperty 表现数据流向，线宽随传输速率变化。
     * @param {string} linkKey - 链路唯一键
     * @param {object} from - 起始节点 { lon, lat, alt }
     * @param {object} to - 终止节点 { lon, lat, alt }
     * @param {number} rateMbps - 传输速率（Mbps），用于映射线宽
     * @param {string} method - 传输方式（direct/relay/multi_relay），用于确定颜色
     * @param {Set<string>} liveLinkKeys - 本轮活跃链路集合
     */
    upsertLink(linkKey, from, to, rateMbps, method, liveLinkKeys) {
      liveLinkKeys.add(linkKey);
      const positions = [
        this.toCartesian(from.lon, from.lat, from.alt || 0),
        this.toCartesian(to.lon, to.lat, to.alt || 0),
      ];
      const width = this._rateToLineWidth(rateMbps);
      const baseColor = this._methodToLinkColor(method || 'direct');

      // 缓存当前链路速率与方式，供动画循环使用
      this._linkAnimRateMap[linkKey] = { rate: rateMbps, method: method || 'direct' };

      if (this._linkIndex[linkKey]) {
        // 更新两端点位置与线宽
        const poly = this._linkIndex[linkKey].polyline;
        poly.positions = positions;
        poly.width = width;
        // 更新发光材质颜色（速率/方式可能在刷新中变化）
        if (poly.material && poly.material instanceof Cesium.PolylineGlowMaterialProperty) {
          poly.material = new Cesium.PolylineGlowMaterialProperty({
            glowPower: 0.25,
            taperPower: 0.9,
            color: baseColor.withAlpha(0.85),
          });
        }
      } else {
        const entity = this.viewer.entities.add({
          polyline: {
            positions,
            width,
            material: new Cesium.PolylineGlowMaterialProperty({
              glowPower: 0.25,
              taperPower: 0.9,
              color: baseColor.withAlpha(0.85),
            }),
            arcType: Cesium.ArcType.NONE,
          },
        });
        this._linkIndex[linkKey] = entity;
      }
    },

    /**
     * 启动链路流动动画循环。
     * 通过持续调用 requestRender 驱动 Cesium 在 requestRenderMode 下不断重绘，
     * 同时利用 PolylineGlowMaterialProperty 的自发光效果模拟数据流动感。
     * 每帧递增 _linkAnimOffset 并对有速率信息的链路微调发光强度，产生脉冲效果。
     */
    _startLinkAnimation() {
      if (this._linkAnimFrame !== null) return; // 已在运行
      if (!this.viewer || !this.cesiumReady) return;

      let lastTime = performance.now();
      const tick = (now) => {
        const dt = Math.min((now - lastTime) / 1000, 0.1); // 单帧增量（秒），上限 100ms
        lastTime = now;

        // 更新全局动画偏移（0–1 循环）
        this._linkAnimOffset = (this._linkAnimOffset + dt * 0.5) % 1;

        // 对每条活跃链路：按速率调整发光强度，营造脉冲流动感
        if (window.Cesium) {
          const t = this._linkAnimOffset;
          for (const [lkey, info] of Object.entries(this._linkAnimRateMap)) {
            const entity = this._linkIndex[lkey];
            if (!entity || !entity.polyline) continue;
            // 速率越高脉冲越快；基础脉冲频率 1Hz，速率比例最高 3x
            const freq = 1 + Math.min(2, (info.rate || 0) / 200);
            const phase = (t * freq) % 1;
            // 发光强度在 0.15–0.55 间脉冲
            const glow = 0.15 + 0.40 * Math.abs(Math.sin(phase * Math.PI));
            const baseColor = this._methodToLinkColor(info.method);
            entity.polyline.material = new Cesium.PolylineGlowMaterialProperty({
              glowPower: glow,
              taperPower: 0.9,
              color: baseColor.withAlpha(0.85),
            });
          }
        }

        // 在 requestRenderMode 下触发重绘
        if (this.viewer && !this.viewer.isDestroyed()) {
          this.viewer.scene.requestRender();
        }

        // 若仍有活跃链路则继续循环
        if (Object.keys(this._linkAnimRateMap).length > 0) {
          this._linkAnimFrame = requestAnimationFrame(tick);
        } else {
          this._linkAnimFrame = null;
        }
      };

      this._linkAnimFrame = requestAnimationFrame(tick);
    },

    /**
     * 停止链路流动动画循环（当无活跃传输链路时调用）。
     */
    _stopLinkAnimation() {
      if (this._linkAnimFrame !== null) {
        cancelAnimationFrame(this._linkAnimFrame);
        this._linkAnimFrame = null;
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

    /**
     * @deprecated 由 upsertLink 取代，保留仅供外部可能调用的场景兼容。
     * 直接新建一个 polyline 实体（不索引，不复用）。
     */
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

    /**
     * @deprecated 由 updateRequestLinks 取代。
     */
    drawRequestLinks(req, satellite, geoMap, gsMap) {
      const liveLinkKeys = new Set();
      this.updateRequestLinks(req, satellite, geoMap, gsMap, liveLinkKeys);
    },

    /**
     * 节流控制器：仅当卫星数量变化或距上次刷新超过 60 秒（模拟时间）时才拉取新轨迹。
     * 轨迹数据变化慢（轨道根数基本固定），无需每帧刷新。
     */
    _refreshOrbitTracksIfNeeded() {
      const now = this.systemTime;
      const elapsed = now - this._tracksLastRefresh;
      const satCount = this.satellites.length;
      const trackedCount = Object.keys(this._trackIndex).length;
      // 首次、卫星数量变化、或距上次刷新超过 60 秒时刷新
      if (trackedCount === 0 || Math.abs(satCount - trackedCount) > 0 || elapsed > 60) {
        this.refreshOrbitTracks();
      }
    },

    /**
     * 从 /api/orbit_tracks 拉取各卫星的轨道采样点，并在 Cesium 中绘制：
     * - 空间轨道折线（带高度，颜色区分 LEO/MEO）
     * - 贴地星下点轨迹（alt=0）
     * 复用已有实体，仅在卫星集合变化时重建。
     */
    async refreshOrbitTracks() {
      if (!this.viewer || !this.cesiumReady || !window.Cesium) return;
      if (this._tracksLoading) return;
      this._tracksLoading = true;
      try {
        const data = await this.fetchJson('/api/orbit_tracks?steps=90');
        if (!data || !Array.isArray(data.tracks)) return;
        this._tracksLastRefresh = this.systemTime;

        // LEO 轨道颜色（橙黄）；MEO 轨道颜色（浅蓝）；星下点轨迹半透明
        const leoOrbitColor = Cesium.Color.fromCssColorString('#f5a623').withAlpha(0.75);
        const meoOrbitColor = Cesium.Color.fromCssColorString('#7ec8e3').withAlpha(0.75);
        const leoGroundColor = Cesium.Color.fromCssColorString('#f5a623').withAlpha(0.35);
        const meoGroundColor = Cesium.Color.fromCssColorString('#7ec8e3').withAlpha(0.35);

        const liveSatIds = new Set(data.tracks.map((t) => t.id));

        // 移除已消失卫星的轨迹实体
        for (const satId of Object.keys(this._trackIndex)) {
          if (!liveSatIds.has(satId)) {
            const pair = this._trackIndex[satId];
            if (pair.orbitEntity) this.viewer.entities.remove(pair.orbitEntity);
            if (pair.groundEntity) this.viewer.entities.remove(pair.groundEntity);
            delete this._trackIndex[satId];
          }
        }

        // 新增或更新各卫星轨迹
        for (const track of data.tracks) {
          const orbitColor = track.type === 'MEO' ? meoOrbitColor : leoOrbitColor;
          const groundColor = track.type === 'MEO' ? meoGroundColor : leoGroundColor;

          const orbitPositions = track.orbit_points.map((p) =>
            this.toCartesian(p.lon, p.lat, p.alt)
          );
          const groundPositions = track.ground_points.map((p) =>
            this.toCartesian(p.lon, p.lat, 1000)  // 略高于地面以防 z-fighting
          );

          if (this._trackIndex[track.id]) {
            // 更新已有实体的折线坐标
            const pair = this._trackIndex[track.id];
            pair.orbitEntity.polyline.positions = orbitPositions;
            pair.groundEntity.polyline.positions = groundPositions;
          } else {
            // 新建轨道折线实体
            const orbitEntity = this.viewer.entities.add({
              polyline: {
                positions: orbitPositions,
                width: 1.5,
                material: new Cesium.PolylineGlowMaterialProperty({
                  glowPower: 0.15,
                  color: orbitColor,
                }),
                arcType: Cesium.ArcType.NONE,
              },
            });
            // 新建贴地星下点轨迹折线实体
            const groundEntity = this.viewer.entities.add({
              polyline: {
                positions: groundPositions,
                width: 1.0,
                material: groundColor,
                arcType: Cesium.ArcType.GEODESIC,
              },
            });
            this._trackIndex[track.id] = { orbitEntity, groundEntity };
          }
        }

        this.viewer.scene.requestRender();
      } catch (e) {
        // 轨迹加载失败不影响主场景更新
        console.warn('轨道轨迹加载失败:', e.message || e);
      } finally {
        this._tracksLoading = false;
      }
    },

    /**
     * 根据卫星/中继高度和最小仰角计算地面覆盖半径（米）。
     *
     * 几何关系（球形地球）：
     *   R_E  — 地球半径 6371 km
     *   h    — 卫星高度（米）
     *   ε    — 最小仰角（度）
     *
     *   天底角 ρ：cos(ρ) = R_E / (R_E + h)
     *   地心角 λ = 90° − ε − ρ
     *   地面覆盖半径 = R_E × λ（弧度制）
     */
    computeCoverageRadius(altitudeM, minElevationDeg) {
      const R_E = 6371000;
      const h = Math.max(altitudeM || 0, 0);
      const cosNadir = R_E / (R_E + h);
      const nadirRad = Math.acos(Math.min(1, cosNadir));
      const minElRad = (minElevationDeg * Math.PI) / 180;
      const earthCentralAngleRad = Math.max(0, Math.PI / 2 - minElRad - nadirRad);
      return R_E * earthCentralAngleRad;
    },

    /**
     * 新增或更新一个贴地覆盖圆（椭圆）实体。
     * 复用已有实体（按 entityId 索引），仅在首次添加时创建；后续仅更新位置与半径。
     */
    upsertCoverageEllipse(entityId, lat, lon, radiusM, fillColor, strokeColor) {
      if (!this.viewer || !window.Cesium) return;
      const r = Math.max(10000, radiusM);
      const position = this.toCartesian(lon, lat, 0);

      if (this._coverageIndex[entityId]) {
        const entity = this._coverageIndex[entityId];
        entity.position = position;
        entity.ellipse.semiMajorAxis = r;
        entity.ellipse.semiMinorAxis = r;
        entity.ellipse.show = this.showCoverage;
      } else {
        const entity = this.viewer.entities.add({
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
            show: this.showCoverage,
          },
        });
        this._coverageIndex[entityId] = entity;
      }
    },

    /**
     * 更新所有 LEO 卫星覆盖足迹圆与 GEO 中继可见性圈。
     * 复用已有实体；仅在节点消失时移除对应实体。
     */
    updateCoverageFootprints() {
      if (!this.viewer || !window.Cesium) return;

      const leoCoverageColor = Cesium.Color.fromCssColorString('#f5a623').withAlpha(0.13);
      const leoStrokeColor = Cesium.Color.fromCssColorString('#f5a623').withAlpha(0.55);
      const geoCoverageColor = Cesium.Color.fromCssColorString('#7ec8e3').withAlpha(0.10);
      const geoStrokeColor = Cesium.Color.fromCssColorString('#7ec8e3').withAlpha(0.50);

      const liveCoverageIds = new Set();

      // LEO 卫星覆盖足迹
      this.satellites
        .filter((sat) => sat.type === 'LEO')
        .forEach((sat) => {
          const eid = `leo-cov-${sat.id}`;
          liveCoverageIds.add(eid);
          const minEl = sat.min_elevation != null ? sat.min_elevation : 10;
          const radius = this.computeCoverageRadius(sat.alt, minEl);
          this.upsertCoverageEllipse(eid, sat.lat, sat.lon, radius, leoCoverageColor, leoStrokeColor);
        });

      // GEO 中继可见性圈
      this.geoRelays.forEach((relay) => {
        const eid = `geo-vis-${relay.id}`;
        liveCoverageIds.add(eid);
        const relayLat = relay.lat != null ? relay.lat : 0;
        const relayAlt = relay.alt != null ? relay.alt : 35786000;
        const minEl = relay.coverage_min_elevation != null ? relay.coverage_min_elevation : 10;
        const radius = this.computeCoverageRadius(relayAlt, minEl);
        this.upsertCoverageEllipse(eid, relayLat, relay.lon, radius, geoCoverageColor, geoStrokeColor);
      });

      // 移除已消失节点的覆盖实体
      for (const eid of Object.keys(this._coverageIndex)) {
        if (!liveCoverageIds.has(eid)) {
          this.viewer.entities.remove(this._coverageIndex[eid]);
          delete this._coverageIndex[eid];
        }
      }
    },

    /**
     * 切换覆盖足迹图层的显示/隐藏状态。
     * 更新所有已注册覆盖实体的 show 属性，并触发重绘。
     */
    toggleCoverageLayer() {
      this.showCoverage = !this.showCoverage;
      for (const entity of Object.values(this._coverageIndex)) {
        if (entity.ellipse) {
          entity.ellipse.show = this.showCoverage;
        }
      }
      if (this.viewer && this.cesiumReady) {
        this.viewer.scene.requestRender();
      }
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

    // ── 甘特图辅助方法 ────────────────────────────────────────────────
    /**
     * 将仿真时刻转换为时间轴上的百分比位置。
     */
    ganttToPct(t) {
      const [start] = this.ganttTimeRange;
      const span = this.ganttRangeSpan;
      return Math.max(0, Math.min(100, ((t - start) / span) * 100));
    },

    ganttBarStyle(evt) {
      const leftPct = this.ganttToPct(evt.start);
      const rightPct = this.ganttToPct(evt.end);
      const widthPct = Math.max(0.4, rightPct - leftPct);
      return { left: leftPct + '%', width: widthPct + '%' };
    },

    ganttBarClass(evt) {
      return `bar-${evt.status} bar-dt-${(evt.data_type || 'unknown').toLowerCase()}`;
    },

    ganttBarTooltip(evt) {
      const dtLabel = DATA_TYPE_LABELS[evt.data_type] || evt.data_type;
      const stLabels = { transmitting: '传输中', completed: '已完成' };
      const stLabel = stLabels[evt.status] || evt.status;
      return `${evt.request_id} · ${dtLabel} · ${stLabel} · ${evt.data_size}MB`;
    },

    ganttHover(evt) {
      this.ganttHoveredEvent = evt;
    },

    ganttLeave() {
      this.ganttHoveredEvent = null;
    },

    formatDuration(seconds) {
      const total = Math.max(0, Math.floor(Number(seconds || 0)));
      if (total < 60) return `${total}s`;
      if (total < 3600) return `${Math.floor(total / 60)}m ${total % 60}s`;
      return `${Math.floor(total / 3600)}h ${Math.floor((total % 3600) / 60)}m`;
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
