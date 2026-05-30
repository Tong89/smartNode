/**
 * en.ts — English locale strings.
 *
 * Mirrors the shape of zh.ts exactly.  Any key missing here will fall
 * back to the Chinese string in the i18n index.
 */
export default {
  // ── General ──────────────────────────────────────────────────────────
  app: {
    title:    'SmartNode Satellite Simulation Platform',
    subtitle: 'Space-Based Intelligent Relay Simulation Platform',
    loading:  'Loading…',
    empty:    'No data',
    retry:    'Retry',
    close:    'Close',
    save:     'Save',
    cancel:   'Cancel',
    confirm:  'Confirm',
  },

  // ── TopBar ────────────────────────────────────────────────────────────
  topbar: {
    backendOnline:  'Backend Online',
    backendOffline: 'Waiting for Backend',
    simClock:       'Sim Clock',
    saveApiBase:    'Save API Base',
    apiBasePlaceholder: 'API Base URL',
    themeToggle:    'Toggle Theme',
    langToggle:     'Toggle Language',
  },

  // ── SideRail ──────────────────────────────────────────────────────────
  siderail: {
    requests:  'Requests',
    resources: 'Resources',
    scenario:  'Scenario',
    timeline:  'Timeline',
    stats:     'Stats',
    playback:  'Playback',
  },

  // ── RequestForm ───────────────────��───────────────────────────────────
  requestForm: {
    title:           'Submit Data Request',
    dataType:        'Data Type',
    dataSize:        'Data Size (MB)',
    priority:        'Priority',
    maxDelay:        'Max Delay (s)',
    satellite:       'Satellite',
    groundStation:   'Ground Station',
    anyGroundStation:'Any Ground Station',
    anySatellite:    'Any Satellite',
    submit:          'Submit',
    submitting:      'Submitting…',
    rejected:        'Request rejected',
    submitted:       'Request submitted',
    unavailable:     'Resources temporarily unavailable',
    submitFailed:    'Submit failed',
  },

  // ── ResourcePanel ─────────────────────────────────────────────────────
  resourcePanel: {
    title:                'Resource Management',
    groundStations:       'Ground Stations',
    leoSatellites:        'LEO Satellites',
    updateGroundStations: 'Update Ground Stations',
    updateLeoSatellites:  'Update Satellites',
    updated:              'Updated',
    updateFailed:         'Resource update failed',
    refresh:              'Refresh',
  },

  // ── ScenarioPanel ──────────────────────────────────────────────────────
  scenarioPanel: {
    title: 'Scenario Config',
  },

  // ── GanttTimeline ──────────────────────────────────────────────────────
  gantt: {
    title:   'Resource Timeline',
    refresh: 'Refresh',
    empty:   'No timeline data',
  },

  // ── StatsChartsPanel ──────────────────────────────────────────────────
  stats: {
    title:           'Statistics',
    accepted:        'Accepted',
    rejected:        'Rejected',
    total:           'Total',
    throughput:      'Throughput',
    decisionMetrics: 'Decision Metrics',
    rejectionDist:   'Rejection Distribution',
    refresh:         'Refresh',
  },

  // ── TimePlayback ──────────────────────────────────────────────────────
  playback: {
    title:        'Simulation Playback',
    play:         'Play',
    pause:        'Pause',
    returnToLive: 'Return to Live',
    speed:        '× Speed',
    noData:       'No playback data',
  },

  // ── Errors & async states ─────────────────────────────────────────────
  error: {
    boundary:       'Component Error',
    boundaryDetail: 'The following error was caught and contained. Other panels continue to work normally.',
    retry:          'Reload',
    loading:        'Loading…',
    empty:          'No data',
    emptyHint:      'This section will update automatically once the backend returns data.',
  },

  // ── API ───────────────────────────────────────────────────────────────
  api: {
    baseUpdated: 'API base URL updated',
  },
} as const;
