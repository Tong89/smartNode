/**
 * zh.ts — Simplified Chinese locale strings.
 *
 * Keys are organised by feature area so it is straightforward to find
 * the string that belongs to a particular component.
 */
export default {
  // ── General ──────────────────────────────────────────────────────────
  app: {
    title:    '天基智枢 SmartNode 仿真平台',
    subtitle: 'Space-Based Intelligent Relay Simulation Platform',
    loading:  '加载中…',
    empty:    '暂无数据',
    retry:    '重试',
    close:    '关闭',
    save:     '保存',
    cancel:   '取消',
    confirm:  '确认',
  },

  // ── TopBar ────────────────────────────────────────────────────────────
  topbar: {
    backendOnline:  '后端在线',
    backendOffline: '等待后端',
    simClock:       '仿真时钟',
    saveApiBase:    '保存 API 地址',
    apiBasePlaceholder: 'API Base URL',
    themeToggle:    '切换主题',
    langToggle:     '切换语言',
  },

  // ── SideRail ──────────────────────────────────────────────────────────
  siderail: {
    requests:  '请求',
    resources: '资源',
    scenario:  '场景',
    timeline:  '时间线',
    stats:     '统计',
    playback:  '回放',
  },

  // ── RequestForm ───────────────────────────────────────────────────────
  requestForm: {
    title:           '发送数据请求',
    dataType:        '数据类型',
    dataSize:        '数据大小 (MB)',
    priority:        '优先级',
    maxDelay:        '最大延迟 (s)',
    satellite:       '卫星',
    groundStation:   '地面站',
    anyGroundStation:'任意地面站',
    anySatellite:    '任意卫星',
    submit:          '提交请求',
    submitting:      '提交中…',
    rejected:        '请求被拒绝',
    submitted:       '请求已提交',
    unavailable:     '资源暂不可用',
    submitFailed:    '提交失败',
  },

  // ── ResourcePanel ─────────────────────────────────────────────────────
  resourcePanel: {
    title:              '资源管理',
    groundStations:     '地面站数量',
    leoSatellites:      'LEO 卫星数量',
    updateGroundStations: '更新地面站',
    updateLeoSatellites:  '更新卫星',
    updated:            '已更新',
    updateFailed:       '资源更新失败',
    refresh:            '刷新',
  },

  // ── ScenarioPanel ──────────────────────────────────────────────────────
  scenarioPanel: {
    title: '场景配置',
  },

  // ── GanttTimeline ──────────────────────────────────────────────────────
  gantt: {
    title:   '资源时间线',
    refresh: '刷新',
    empty:   '暂无时间线数据',
  },

  // ── StatsChartsPanel ──────────────────────────────────────────────────
  stats: {
    title:             '统计图表',
    accepted:          '已接受',
    rejected:          '已拒绝',
    total:             '总计',
    throughput:        '吞吐量',
    decisionMetrics:   '决策指标',
    rejectionDist:     '拒绝分布',
    refresh:           '刷新',
  },

  // ── TimePlayback ──────────────────────────────────────────────────────
  playback: {
    title:        '仿真回放',
    play:         '播放',
    pause:        '暂停',
    returnToLive: '返回实时',
    speed:        '倍速',
    noData:       '暂无回放数据',
  },

  // ── Errors & async states ─────────────────────────────────────────────
  error: {
    boundary:       '组件发生错误',
    boundaryDetail: '以下错误已被拦截，不影响其他面板正常使用。',
    retry:          '重新加载',
    loading:        '加载中…',
    empty:          '暂无数据',
    emptyHint:      '当后端返回数据后，此处将自动更新。',
  },

  // ── API ───────────────────────────────────────────────────────────────
  api: {
    baseUpdated: 'API 地址已更新',
  },
} as const;
