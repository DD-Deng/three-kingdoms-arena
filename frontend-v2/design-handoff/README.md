# 三国 Arena · HomePage v2 · 水墨版

水墨主题的首页设计 + 实时演武图 + 山水背景 + 龙腾交互。

打开 `homepage.html` 即可在浏览器里独立预览(无需构建,内置 Babel 即时编译)。

---

## 一、文件总览

```
homepage-handoff/
├── README.md                  ← 你正在看的这个
├── homepage.html              ← 入口 (浏览器 Babel,直接打开即看)
├── homepage.jsx               ← 顶层 React 组件 (Nav / Hero / 战场态势 / 大厅)
├── homepage.css               ← 页面布局 + 水墨主题样式
│
├── hero-battle.jsx            ← 演武图 (auto/live/replay/demo 四种数据源)
│
├── ink-landscape.jsx          ← 山水背景 (马远《踏歌图》)
├── ink-landscape.css          ← 背景动画样式
│
├── dragon.jsx                 ← 水墨龙交互 (右崖 hover 触发)
├── dragon.css                 ← 龙动画 (emerging + fading)
│
├── tweaks-panel.jsx           ← Tweaks 调试面板组件 (仅 dev 使用)
│
├── assets/
│   ├── landscape-strokes.png  ← 抠掉绢底的水墨笔触,染成 #1f1a16 (729×1280)
│   ├── landscape-wide.png     ← 4 联横幅 (镜像拼接,某些布局用,可选)
│   └── dragon.png             ← 抠透明 + 染色的水墨龙 (786×999)
│
└── sources/                   ← 原始素材 (重新加工时用)
    ├── landscape.jpg          ← Wikimedia 公有领域版《踏歌图》(729×1280)
    └── dragon-src.png         ← 用户提供的水墨龙原图 (1293×1330)
```

---

## 二、组件依赖关系

```
homepage.html
 ├─ tweaks-panel.jsx   (TweaksPanel / useTweaks / Tweak* controls)
 ├─ hero-battle.jsx    (HeroBattle)
 ├─ ink-landscape.jsx  (InkLandscape)
 ├─ dragon.jsx         (InkDragon)
 └─ homepage.jsx       (HomePagePreview - 主组件,内部组合一切)
```

加载顺序很重要 — `homepage.jsx` 依赖前面所有的 `window.*` 全局。在 Vite/React 项目里用 ES modules 重写时,直接 `import` 即可。

---

## 三、整合到 frontend-v2 的步骤

### 1. 把全局变量改成 ES module export

每个 `.jsx` 文件最后都有 `window.XXX = XXX;`。改成:

```js
// in tweaks-panel.jsx
export { useTweaks, TweaksPanel, TweakSection, TweakSlider, TweakToggle,
         TweakRadio, TweakSelect, TweakText, TweakNumber, TweakColor, TweakButton };

// in hero-battle.jsx
export function HeroBattle({ mode, liveEndpoint, replayEndpoint }) { ... }

// in ink-landscape.jsx
export function InkLandscape({ opacity, motion, layout }) { ... }

// in dragon.jsx
export function InkDragon({ enabled }) { ... }

// in homepage.jsx
export default function HomePagePreview({ lobbyState, savedSession, heroMode }) { ... }
```

`homepage.jsx` 内部的 `Hero`/`Nav`/`Slots`/`Footer`/`BattlePreviewCard` 全是内部组件,不用导出。

### 2. 替换 mock 数据为真实接口

下面这些是当前的 mock,**整合时必须替换**:

| 文件 | mock 数据 | 真实数据来源 |
|---|---|---|
| `homepage.jsx` | `LOBBY_PRESETS` | `GET /v1/lobby/status` (已在 `frontend-v2/src/api.js`) |
| `homepage.jsx` | `savedSession` (从 props 传入) | `localStorage` 中的 `arena_sessions` |
| `hero-battle.jsx` | `HB_MOCK_REPLAY` | 后端实现 `GET /api/battles/latest` |
| `hero-battle.jsx` | `liveEndpoint`(默认 `/v1/lobby/status`) | ✅ 已经对应真实接口,只需后端在响应里附 `cities` + `events` 字段 |

### 3. 资源路径

`assets/` 里的图片在打包系统里需要用 `import` 或放进 `public/`:

```js
import landscapePNG from './assets/landscape-strokes.png';
import dragonPNG from './assets/dragon.png';
```

或者直接放到 `public/images/` 下,引用为 `/images/landscape-strokes.png`。代码里的字符串路径要相应调整。

### 4. CSS 全局变量冲突

`homepage.css` 里定义了 `:root` 上的水墨主题色板:
- `--bg`, `--panel`, `--ink`, `--vermillion` 等

frontend-v2 现有 `tokens.css` 里也定义了一套 `--bg`/`--panel`/`--accent`。整合时**择一保留**:
- 推荐:把这一版的 `homepage.css` 颜色合并进 `tokens.css`(本版的米色 + 朱红更精致)
- 旧版的 `--gold` 变量在本版用得很少,可以删

### 5. 移除/调整 Tweaks

`Tweaks` 是开发用的可视化调试面板。整合时:
- **生产环境**:删掉 `<TweaksPanel>` 整段 + 不再 import `tweaks-panel.jsx`,直接把当前的 tweak 默认值硬编码进组件 props
- **保留开发模式**:用 `import.meta.env.DEV` 包一层条件渲染

### 6. 把 homepage.jsx 接到路由

在 `frontend-v2/src/App.jsx` 里:

```jsx
import HomePagePreview from './pages/HomePageInk' // 改路径
// ...
<Route path="/" element={<HomePagePreview />} />
```

注意:旧版 `HomePage.jsx` 已经包含了 lobby 功能(`actJoin`/`actAssignAI` 等)。新版 `homepage.jsx` 是**纯展示原型**,没接 API。建议:
- 把旧版 `HomePage.jsx` 里的 lobby 状态管理 / API 调用逻辑搬过来
- 用新版的 UI + 旧版的逻辑

---

## 四、龙腾交互注意

`dragon.jsx` 监听 `document.mousemove`,并且:
- 只在 `window.scrollY <= 120` 时触发 (滚动到下方就静默)
- 触发区域:viewport 的 58%–96% × 6%–52% (右上角山崖)
- 一次触发后 800ms 冷却,鼠标离开 + 再次进入才能再触发
- 总动画时长 ~5.4s (emerge 2.2s + fade 3.2s)
- `prefers-reduced-motion` 或屏幕宽度 < 720px 自动关闭

`feTurbulence` + `feDisplacementMap` 滤镜给龙身做持续蜿蜒。这个滤镜在低端 GPU 上可能稍重 — 如果遇到性能问题,可以降 `numOctaves` 到 1 或去掉。

---

## 五、资源再加工(如果需要重新生成)

### landscape-strokes.png(抠绢底 + 染色)

```python
# 伪代码 / 思路 — 实际用 canvas 或 Python PIL 都行
from PIL import Image
img = Image.open('sources/landscape.jpg').convert('RGB')
for each pixel (r, g, b):
    lum = 0.30*r + 0.59*g + 0.11*b
    if lum >= 150:        alpha = 0           # 绢底 → 透明
    elif lum <= 50:       alpha = 220         # 浓墨 → 接近不透明
    else:
        t = (150 - lum) / (150 - 50)
        alpha = round((t ** 1.6) * 220)       # 中间用 gamma 曲线
    set pixel to (31, 26, 22, alpha)          # ink color #1f1a16
img.save('assets/landscape-strokes.png')
```

阈值 `150 / 50` 和 gamma `1.6` 是经过反复调试的甜区。

### landscape-wide.png(4 联横幅,可选)

把 `landscape-strokes.png` 横向拼接为 [镜像 | 原 | 镜像 | 原],总尺寸 2916×1280,长宽比 2.28(略宽于典型 viewport)。

### dragon.png(裁切 + 染色)

```python
img = Image.open('sources/dragon-src.png').convert('RGBA')
# 1. 找出 alpha > 8 的像素的最小外接矩形,加 20px padding
# 2. 裁出该矩形 (输出约 786×999)
# 3. 把 RGB 全部改为 (31, 26, 22),alpha 乘以 0.95
img_cropped.save('assets/dragon.png')
```

---

## 六、已知限制

- **HeroBattle live 模式**:依赖 `/v1/lobby/status` 响应包含 `cities` 数组和 `events` 数组;当前后端如果不返回这两个字段,会自动降级到 replay 或 demo。要让它真正工作,需要后端在 lobby status 响应里加上 `cities: [{name, owner, troops}]` 和 `events: [{tick, kind, faction, text, id}]`。
- **HeroBattle replay 模式**:需要后端实现 `GET /api/battles/latest` 返回 `{battle_id, model, winner, total_ticks, ticks: [...]}` —— `ticks` 的 shape 见 `hero-battle.jsx` 顶部 `HB_MOCK_REPLAY`。
- **国际化**:目前是中文 hardcoded,英文切换按钮没接逻辑。要加 i18n 时,把 `homepage.jsx` 里的文案抽到字典里。

---

## 七、改动思路概要(给 Claude Code 的提示)

整合优先级:
1. **先搬 UI 不动数据** — 把 `homepage-handoff/` 整个复制成 `frontend-v2/src/pages/HomePageInk/`,通通改成 ES module 导入,资源放 public,跑通独立预览
2. **再接 lobby** — 把现有 `HomePage.jsx` 里的 `actJoin`/`actAssignAI`/`getSession`/`JoinModal` 等逻辑搬到新组件里,替换 `LOBBY_PRESETS`
3. **再接战报** — 实现 `/api/battles/latest` 后端,移除 `HB_MOCK_REPLAY` 兜底
4. **最后清理 Tweaks** — 生产环境删掉,开发环境用 env 包一层

注意保留 `data-comment-anchor`(如果有)和 `data-screen-label`(如果有)属性 —— 这些是设计审阅系统用的钩子。

—— end of README ——
