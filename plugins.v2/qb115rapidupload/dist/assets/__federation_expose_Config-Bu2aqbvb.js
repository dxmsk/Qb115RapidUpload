import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';

const {createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,withCtx:_withCtx,createTextVNode:_createTextVNode,toDisplayString:_toDisplayString,normalizeClass:_normalizeClass,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode} = await importShared('vue');


const _hoisted_1 = { class: "config-page" };
const _hoisted_2 = { class: "d-flex align-center ga-3 mt-2" };

const {onMounted,ref} = await importShared('vue');



const _sfc_main = {
  __name: 'Config',
  props: {
  initialConfig: { type: Object, default: () => ({}) },
  api: { type: Object, default: () => ({}) },
},
  emits: ['save', 'close'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;
const defaults = {
  enabled: true,
  qb_url: 'http://127.0.0.1:8080',
  username: 'admin',
  password: '',
  monitor_interval_seconds: 1,
  cookie_115: '',
  target_cid: '0',
  rapid_upload_path: '',
  retry_interval_minutes: 30,
  stop_after_organized: true,
  cancel_organize_after_success: true,
  auto_organize_enabled: true,
  ignore_tags: '',
  force_organize: false,
};
const config = ref({ ...defaults });
const testingQb = ref(false);
const testMessage = ref('');
const testSuccess = ref(false);

function save() {
  config.value.retry_interval_minutes = Math.min(1440, Math.max(1, Number(config.value.retry_interval_minutes || 30)));
  config.value.monitor_interval_seconds = Math.min(3600, Math.max(1, Number(config.value.monitor_interval_seconds || 1)));
  config.value.target_cid = String(config.value.target_cid || '0').trim() || '0';
  emit('save', { ...config.value });
}

async function testQb() {
  testingQb.value = true;
  testMessage.value = '';
  try {
    const response = await props.api.get('plugin/Qb115RapidUpload/test_qb');
    const payload = response?.data?.data || response?.data || response || {};
    testSuccess.value = Boolean(payload.ok);
    testMessage.value = payload.message || (testSuccess.value ? '连接成功' : '连接失败');
  } catch (err) {
    testSuccess.value = false;
    testMessage.value = err?.message || '连接测试失败';
  } finally {
    testingQb.value = false;
  }
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
  const _component_VTextField = _resolveComponent("VTextField");
  const _component_VCol = _resolveComponent("VCol");
  const _component_VRow = _resolveComponent("VRow");
  const _component_VCardText = _resolveComponent("VCardText");
  const _component_VCard = _resolveComponent("VCard");
  const _component_VSwitch = _resolveComponent("VSwitch");
  const _component_VTextarea = _resolveComponent("VTextarea");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_VToolbar, {
      color: "transparent",
      density: "comfortable"
    }, {
      default: _withCtx(() => [
        _cache[15] || (_cache[15] = _createElementVNode("div", { class: "text-h6 font-weight-bold ms-3" }, "qB 115 秒传整理联动", -1)),
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
      default: _withCtx(() => [...(_cache[16] || (_cache[16] = [
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
              icon: "mdi-server-network",
              color: "primary",
              class: "mr-2"
            }),
            _cache[17] || (_cache[17] = _createTextVNode("qBittorrent 监控", -1))
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
                    _createVNode(_component_VTextField, {
                      modelValue: config.value.qb_url,
                      "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((config.value.qb_url) = $event)),
                      label: "服务器地址",
                      placeholder: "http://127.0.0.1:8080",
                      "prepend-inner-icon": "mdi-web"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "3"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextField, {
                      modelValue: config.value.username,
                      "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((config.value.username) = $event)),
                      label: "用户名",
                      "prepend-inner-icon": "mdi-account"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "3"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextField, {
                      modelValue: config.value.password,
                      "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((config.value.password) = $event)),
                      label: "密码",
                      type: "password",
                      autocomplete: "current-password",
                      "prepend-inner-icon": "mdi-lock"
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
                      modelValue: config.value.monitor_interval_seconds,
                      "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.value.monitor_interval_seconds) = $event)),
                      modelModifiers: { number: true },
                      label: "监控轮询间隔（秒）",
                      type: "number",
                      min: "1",
                      max: "3600",
                      hint: "秒传与自动整理共同使用",
                      "persistent-hint": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }),
            _createElementVNode("div", _hoisted_2, [
              _createVNode(_component_VBtn, {
                color: "primary",
                variant: "tonal",
                "prepend-icon": "mdi-lan-connect",
                loading: testingQb.value,
                onClick: testQb
              }, {
                default: _withCtx(() => [...(_cache[18] || (_cache[18] = [
                  _createTextVNode("测试连接", -1)
                ]))]),
                _: 1
              }, 8, ["loading"]),
              (testMessage.value)
                ? (_openBlock(), _createElementBlock("span", {
                    key: 0,
                    class: _normalizeClass(["text-caption", testSuccess.value ? 'text-success' : 'text-error'])
                  }, _toDisplayString(testMessage.value), 3))
                : _createCommentVNode("", true)
            ])
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
              icon: "mdi-cloud-upload-outline",
              color: "primary",
              class: "mr-2"
            }),
            _cache[19] || (_cache[19] = _createTextVNode("115 秒传", -1))
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
                      "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.value.enabled) = $event)),
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
                      "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.value.cookie_115) = $event)),
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
                      "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((config.value.target_cid) = $event)),
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
                      "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((config.value.retry_interval_minutes) = $event)),
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
                      "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((config.value.rapid_upload_path) = $event)),
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
                      "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((config.value.stop_after_organized) = $event)),
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
                      "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((config.value.cancel_organize_after_success) = $event)),
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
            _cache[20] || (_cache[20] = _createTextVNode("自动整理", -1))
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
                      "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((config.value.auto_organize_enabled) = $event)),
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
                      "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((config.value.force_organize) = $event)),
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
                      "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((config.value.ignore_tags) = $event)),
                      label: "排除 qB 标签",
                      placeholder: "例如：刷流,已整理",
                      hint: "留空时处理所有标签；命中任一排除标签的任务既不秒传也不自动整理",
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
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-022923cb"]]);

export { Config as default };
