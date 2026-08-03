import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';

const {createElementVNode:_createElementVNode,toDisplayString:_toDisplayString,resolveComponent:_resolveComponent,createVNode:_createVNode,withCtx:_withCtx,createTextVNode:_createTextVNode,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "status-page" };
const _hoisted_2 = { class: "toolbar-copy" };
const _hoisted_3 = { class: "text-caption text-medium-emphasis" };
const _hoisted_4 = ["title"];
const _hoisted_5 = ["title"];
const _hoisted_6 = ["title"];
const _hoisted_7 = ["title"];
const _hoisted_8 = ["title"];
const _hoisted_9 = ["title"];

const {computed,onMounted,ref} = await importShared('vue');



const _sfc_main = {
  __name: 'Page',
  props: { api: { type: Object, default: () => ({}) } },
  emits: ['close'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;
const tab = ref('rapid');
const loading = ref(false);
const error = ref('');
const tasks = ref([]);
const organizeRecords = ref([]);

const rapidSuccesses = computed(() => tasks.value.filter(item => item.status === 'SUCCESS'));
const activeRapidCount = computed(() => tasks.value.filter(item => ['WAITING', 'PROCESSING', 'RETRY_WAIT'].includes(item.status)).length);

const rapidHeaders = [
  { title: '资源', key: 'torrent_name' },
  { title: '成功时间', key: 'rapid_uploaded_at' },
  { title: '大小', key: 'display_size', sortable: false },
  { title: '本地来源', key: 'source_path', sortable: false },
  { title: '115 秒传路径', key: 'remote_path', sortable: false },
];
const organizeHeaders = [
  { title: '资源', key: 'torrent_name' },
  { title: '状态', key: 'display_status' },
  { title: '入队/完成时间', key: 'display_time' },
  { title: '来源路径', key: 'source_path', sortable: false },
  { title: '目标路径 / 错误', key: 'detail', sortable: false },
];

function unwrap(response) {
  const root = response?.data ?? response ?? {};
  if (root?.data !== undefined && root?.code !== undefined) return root.data
  if (root?.data?.data !== undefined && root?.data?.code !== undefined) return root.data.data
  return root
}

function formatSize(value) {
  let number = Number(value || 0);
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  let index = 0;
  while (number >= 1024 && index < units.length - 1) { number /= 1024; index += 1; }
  return index ? `${number.toFixed(1)} ${units[index]}` : `${Math.max(0, Math.round(number))} B`
}

function formatTime(value) {
  if (!value) return '-'
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12: false })
}

function remotePath(item) {
  const base = String(item.target_cid || '0') === '0' ? '115:/根目录' : `115:/目录ID/${item.target_cid}`;
  return item.remote_dirs ? `${base}/${item.remote_dirs}` : base
}

function organizeStatus(value) {
  return {
    QUEUED: '等待整理',
    SUCCESS: '整理成功',
    FAILED: '整理失败',
    CANCELLED_RAPID_SUCCESS: '秒传成功，已取消整理',
  }[value] || value || '未入队'
}

async function loadData() {
  loading.value = true;
  error.value = '';
  try {
    const [taskResponse, organizeResponse] = await Promise.all([
      props.api.get('plugin/Qb115RapidUpload/tasks', { params: { limit: 300 } }),
      props.api.get('plugin/Qb115RapidUpload/organize_records', { params: { limit: 300 } }),
    ]);
    const rawTasks = unwrap(taskResponse);
    const rawRecords = unwrap(organizeResponse);
    tasks.value = (Array.isArray(rawTasks) ? rawTasks : []).map(item => ({
      ...item,
      rapid_uploaded_at: formatTime(item.rapid_uploaded_at),
      display_size: formatSize(item.total_size),
      source_path: item.content_path || item.save_path || '-',
      remote_path: remotePath(item),
    }));
    organizeRecords.value = (Array.isArray(rawRecords) ? rawRecords : []).map(item => ({
      ...item,
      display_status: organizeStatus(item.organize_status),
      display_time: formatTime(item.organize_completed_at || item.organize_queued_at),
      source_path: item.organize_source_path || item.content_path || item.save_path || '-',
      detail: item.organize_target_path || item.organize_last_error || '-',
    }));
  } catch (err) {
    error.value = err?.message || '任务记录加载失败';
  } finally {
    loading.value = false;
  }
}

onMounted(loadData);

return (_ctx, _cache) => {
  const _component_VSpacer = _resolveComponent("VSpacer");
  const _component_VBtn = _resolveComponent("VBtn");
  const _component_VToolbar = _resolveComponent("VToolbar");
  const _component_VAlert = _resolveComponent("VAlert");
  const _component_VIcon = _resolveComponent("VIcon");
  const _component_VTab = _resolveComponent("VTab");
  const _component_VTabs = _resolveComponent("VTabs");
  const _component_VDataTable = _resolveComponent("VDataTable");
  const _component_VWindowItem = _resolveComponent("VWindowItem");
  const _component_VChip = _resolveComponent("VChip");
  const _component_VWindow = _resolveComponent("VWindow");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_VToolbar, {
      color: "transparent",
      density: "comfortable",
      class: "page-toolbar"
    }, {
      default: _withCtx(() => [
        _createElementVNode("div", _hoisted_2, [
          _cache[4] || (_cache[4] = _createElementVNode("div", { class: "text-h6 font-weight-bold" }, "qB 115 秒传整理联动", -1)),
          _createElementVNode("div", _hoisted_3, "秒传成功 " + _toDisplayString(rapidSuccesses.value.length) + " · 正在处理 " + _toDisplayString(activeRapidCount.value) + " · 整理记录 " + _toDisplayString(organizeRecords.value.length), 1)
        ]),
        _createVNode(_component_VSpacer),
        _createVNode(_component_VBtn, {
          icon: "mdi-refresh",
          variant: "text",
          loading: loading.value,
          title: "刷新",
          onClick: loadData
        }, null, 8, ["loading"]),
        _createVNode(_component_VBtn, {
          icon: "mdi-close",
          variant: "text",
          title: "关闭",
          onClick: _cache[0] || (_cache[0] = $event => (emit('close')))
        })
      ]),
      _: 1
    }),
    (error.value)
      ? (_openBlock(), _createBlock(_component_VAlert, {
          key: 0,
          type: "error",
          variant: "tonal",
          class: "mb-3",
          closable: "",
          "onClick:close": _cache[1] || (_cache[1] = $event => (error.value = ''))
        }, {
          default: _withCtx(() => [
            _createTextVNode(_toDisplayString(error.value), 1)
          ]),
          _: 1
        }))
      : _createCommentVNode("", true),
    _createVNode(_component_VTabs, {
      modelValue: tab.value,
      "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((tab).value = $event)),
      color: "primary",
      class: "mb-3"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VTab, { value: "rapid" }, {
          default: _withCtx(() => [
            _createVNode(_component_VIcon, {
              icon: "mdi-cloud-check-outline",
              class: "mr-2"
            }),
            _cache[5] || (_cache[5] = _createTextVNode("115 秒传", -1))
          ]),
          _: 1
        }),
        _createVNode(_component_VTab, { value: "organize" }, {
          default: _withCtx(() => [
            _createVNode(_component_VIcon, {
              icon: "mdi-folder-sync-outline",
              class: "mr-2"
            }),
            _cache[6] || (_cache[6] = _createTextVNode("自动整理", -1))
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_VWindow, {
      modelValue: tab.value,
      "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((tab).value = $event))
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VWindowItem, { value: "rapid" }, {
          default: _withCtx(() => [
            _createVNode(_component_VDataTable, {
              headers: rapidHeaders,
              items: rapidSuccesses.value,
              loading: loading.value,
              density: "compact",
              "fixed-header": "",
              height: "32rem",
              "item-value": "id",
              "no-data-text": "暂无秒传成功记录"
            }, {
              "item.torrent_name": _withCtx(({ item }) => [
                _createElementVNode("span", {
                  class: "name-cell",
                  title: item.torrent_name
                }, _toDisplayString(item.torrent_name || item.download_hash), 9, _hoisted_4)
              ]),
              "item.source_path": _withCtx(({ item }) => [
                _createElementVNode("span", {
                  class: "path-cell",
                  title: item.source_path
                }, _toDisplayString(item.source_path), 9, _hoisted_5)
              ]),
              "item.remote_path": _withCtx(({ item }) => [
                _createElementVNode("span", {
                  class: "path-cell",
                  title: item.remote_path
                }, _toDisplayString(item.remote_path), 9, _hoisted_6)
              ]),
              _: 1
            }, 8, ["items", "loading"])
          ]),
          _: 1
        }),
        _createVNode(_component_VWindowItem, { value: "organize" }, {
          default: _withCtx(() => [
            _createVNode(_component_VDataTable, {
              headers: organizeHeaders,
              items: organizeRecords.value,
              loading: loading.value,
              density: "compact",
              "fixed-header": "",
              height: "32rem",
              "item-value": "id",
              "no-data-text": "暂无自动整理记录"
            }, {
              "item.torrent_name": _withCtx(({ item }) => [
                _createElementVNode("span", {
                  class: "name-cell",
                  title: item.torrent_name
                }, _toDisplayString(item.torrent_name || item.download_hash), 9, _hoisted_7)
              ]),
              "item.display_status": _withCtx(({ item }) => [
                _createVNode(_component_VChip, {
                  size: "small",
                  variant: "tonal",
                  color: item.organize_status === 'SUCCESS' ? 'success' : item.organize_status === 'FAILED' ? 'error' : item.organize_status === 'CANCELLED_RAPID_SUCCESS' ? 'info' : 'warning'
                }, {
                  default: _withCtx(() => [
                    _createTextVNode(_toDisplayString(item.display_status), 1)
                  ]),
                  _: 2
                }, 1032, ["color"])
              ]),
              "item.source_path": _withCtx(({ item }) => [
                _createElementVNode("span", {
                  class: "path-cell",
                  title: item.source_path
                }, _toDisplayString(item.source_path), 9, _hoisted_8)
              ]),
              "item.detail": _withCtx(({ item }) => [
                _createElementVNode("span", {
                  class: "path-cell",
                  title: item.detail
                }, _toDisplayString(item.detail), 9, _hoisted_9)
              ]),
              _: 1
            }, 8, ["items", "loading"])
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"])
  ]))
}
}

};
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-150fa0d1"]]);

export { Page as default };
