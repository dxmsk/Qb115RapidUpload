import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';

const {createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,withCtx:_withCtx,createTextVNode:_createTextVNode,openBlock:_openBlock,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "config-page" };

const {onMounted,ref} = await importShared('vue');



const _sfc_main = {
  __name: 'Config',
  props: { initialConfig: { type: Object, default: () => ({}) } },
  emits: ['save', 'close'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;
const defaults = {
  enabled: true,
  cookie_115: '',
  target_cid: '0',
  rapid_upload_path: '',
  retry_interval_minutes: 30,
  stop_after_organized: true,
  cancel_organize_after_success: true,
  auto_organize_enabled: true,
  ignore_tags: '已整理,刷流',
  force_organize: false,
};
const config = ref({ ...defaults });

function save() {
  config.value.retry_interval_minutes = Math.min(1440, Math.max(1, Number(config.value.retry_interval_minutes || 30)));
  config.value.target_cid = String(config.value.target_cid || '0').trim() || '0';
  emit('save', { ...config.value });
}

onMounted(() => { config.value = { ...defaults, ...(props.initialConfig || {}) }; });

return (_ctx, _cache) => {
  const _component_VSpacer = _resolveComponent("VSpacer");
  const _component_VBtn = _resolveComponent("VBtn");
  const _component_VToolbar = _resolveComponent("VToolbar");
  const _component_VAlert = _resolveComponent("VAlert");
  const _component_VIcon = _resolveComponent("VIcon");
  const _component_VCardTitle = _resolveComponent("VCardTitle");
  const _component_VDivider = _resolveComponent("VDivider");
  const _component_VSwitch = _resolveComponent("VSwitch");
  const _component_VCol = _resolveComponent("VCol");
  const _component_VTextField = _resolveComponent("VTextField");
  const _component_VTextarea = _resolveComponent("VTextarea");
  const _component_VRow = _resolveComponent("VRow");
  const _component_VCardText = _resolveComponent("VCardText");
  const _component_VCard = _resolveComponent("VCard");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_VToolbar, {
      color: "transparent",
      density: "comfortable"
    }, {
      default: _withCtx(() => [
        _cache[11] || (_cache[11] = _createElementVNode("div", { class: "text-h6 font-weight-bold ms-3" }, "qB 115 秒传整理联动", -1)),
        _createVNode(_component_VSpacer),
        _createVNode(_component_VBtn, {
          icon: "mdi-content-save",
          color: "primary",
          variant: "text",
          title: "保存",
          onClick: save
        }),
        _createVNode(_component_VBtn, {
          icon: "mdi-close",
          variant: "text",
          title: "关闭",
          onClick: _cache[0] || (_cache[0] = $event => (emit('close')))
        })
      ]),
      _: 1
    }),
    _createVNode(_component_VAlert, {
      type: "info",
      variant: "tonal",
      class: "mb-4"
    }, {
      default: _withCtx(() => [...(_cache[12] || (_cache[12] = [
        _createTextVNode(" 秒传只读取文件计算 SHA1，不移动、不重命名、不删除、不修改本地数据。统一调度顺序为：qB 完成 → 首次秒传 → 失败后整理入队。 ", -1)
      ]))]),
      _: 1
    }),
    _createVNode(_component_VCard, {
      variant: "tonal",
      class: "config-card"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCardTitle, null, {
          default: _withCtx(() => [
            _createVNode(_component_VIcon, {
              icon: "mdi-cloud-upload-outline",
              color: "primary",
              class: "mr-2"
            }),
            _cache[13] || (_cache[13] = _createTextVNode("115 秒传", -1))
          ]),
          _: 1
        }),
        _createVNode(_component_VDivider),
        _createVNode(_component_VCardText, null, {
          default: _withCtx(() => [
            _createVNode(_component_VRow, null, {
              default: _withCtx(() => [
                _createVNode(_component_VCol, { cols: "12" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VSwitch, {
                      modelValue: config.value.enabled,
                      "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((config.value.enabled) = $event)),
                      label: "启用插件",
                      inset: ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, { cols: "12" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextField, {
                      modelValue: config.value.cookie_115,
                      "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((config.value.cookie_115) = $event)),
                      label: "115 Cookie（必填）",
                      type: "password",
                      autocomplete: "new-password"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextField, {
                      modelValue: config.value.target_cid,
                      "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((config.value.target_cid) = $event)),
                      label: "目标目录 ID",
                      hint: "0 表示 115 根目录",
                      "persistent-hint": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextField, {
                      modelValue: config.value.retry_interval_minutes,
                      "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.value.retry_interval_minutes) = $event)),
                      modelModifiers: { number: true },
                      label: "重试间隔（分钟）",
                      type: "number",
                      min: "1",
                      max: "1440"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, { cols: "12" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextarea, {
                      modelValue: config.value.rapid_upload_path,
                      "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.value.rapid_upload_path) = $event)),
                      label: "秒传目录（本地）",
                      rows: "2",
                      "auto-grow": "",
                      hint: "留空使用 MoviePilot 默认下载目录；逗号或换行分隔多个目录",
                      "persistent-hint": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VSwitch, {
                      modelValue: config.value.stop_after_organized,
                      "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.value.stop_after_organized) = $event)),
                      label: "整理后停止秒传",
                      hint: "MoviePilot整理完成后不再尝试秒传",
                      "persistent-hint": "",
                      inset: ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VSwitch, {
                      modelValue: config.value.cancel_organize_after_success,
                      "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((config.value.cancel_organize_after_success) = $event)),
                      label: "秒传成功后取消整理任务",
                      hint: "秒传成功后自动取消对应整理任务，避免重复转移",
                      "persistent-hint": "",
                      inset: ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode(_component_VCard, {
      variant: "tonal",
      class: "config-card"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCardTitle, null, {
          default: _withCtx(() => [
            _createVNode(_component_VIcon, {
              icon: "mdi-folder-sync-outline",
              color: "success",
              class: "mr-2"
            }),
            _cache[14] || (_cache[14] = _createTextVNode("自动整理", -1))
          ]),
          _: 1
        }),
        _createVNode(_component_VDivider),
        _createVNode(_component_VCardText, null, {
          default: _withCtx(() => [
            _createVNode(_component_VRow, null, {
              default: _withCtx(() => [
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VSwitch, {
                      modelValue: config.value.auto_organize_enabled,
                      "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((config.value.auto_organize_enabled) = $event)),
                      label: "启用自动整理联动",
                      hint: "仅首次秒传失败的任务才进入整理队列",
                      "persistent-hint": "",
                      inset: ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VSwitch, {
                      modelValue: config.value.force_organize,
                      "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((config.value.force_organize) = $event)),
                      label: "强制整理",
                      hint: "向 MoviePilot 传递 manual=true、force=true",
                      "persistent-hint": "",
                      inset: ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, { cols: "12" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextField, {
                      modelValue: config.value.ignore_tags,
                      "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((config.value.ignore_tags) = $event)),
                      label: "排除 qB 标签",
                      placeholder: "已整理,刷流",
                      hint: "命中任一标签的任务不会秒传，也不会自动整理；支持逗号、中文逗号或空格",
                      "persistent-hint": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    })
  ]))
}
}

};
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-8b89ad22"]]);

export { Config as default };
