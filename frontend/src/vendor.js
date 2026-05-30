// 本地化第三方运行时：由 Vite 从 node_modules 打包 Cesium / Vue / lucide，
// 挂载为全局供经典脚本 app.js 沿用（去除 unpkg CDN 运行时依赖，离线可用）。
import * as Vue from 'vue';
import * as Cesium from 'cesium';
import 'cesium/Build/Cesium/Widgets/widgets.css';
import * as lucide from 'lucide';

if (typeof window !== 'undefined') {
  window.Vue = Vue;
  window.Cesium = Cesium;
  window.lucide = lucide;
}

export { Vue, Cesium, lucide };
