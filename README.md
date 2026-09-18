# Vision Driver Box

Vision Driver Box is an industrial-grade bridge driver tool designed for vision systems, enabling efficient collaboration and data forwarding between camera acquisition and printing control systems.

## Key Features

- **Industrial Camera Integration**: Deeply integrated based on IKapC SDK, supporting high-performance image acquisition, parameter configuration, and stream control.
- **TCP/IP Forwarding Service**: Built-in efficient print data forwarding engine with support for custom delay control and data buffering.
- **Real-time Status Monitoring**: Real-time system status display (Standby, Running, Capture Mode, etc.) via system tray icons, with support for native Windows notifications.
- **Gantt Chart Performance Analysis**: Automatically parses execution logs to generate intuitive PDF Gantt charts for precise timing analysis of camera acquisition and print forwarding.
- **Flexible Configuration Management**: Provides a graphical user interface for dynamic adjustment of communication addresses, image parameters, stitching settings, and more.

## Project Structure

- `drivers/`: Hardware driver layer, containing camera (IKapC) and printer control logic.
- `ui/`: Interface layer, parameter settings and interaction UI based on Tkinter.
- `utils/`: Utility layer, including log management, path resolution, and Gantt chart generation engine.
- `src/`: Resource layer, storing system icons and core configuration files.

## Getting Started

### Development Environment
1. Ensure Python 3.9+ is installed.
2. Install dependencies (install `pyinstaller` if packaging is required).
3. Run the main program:
   ```bash
   python main.py
   ```

### Production Deployment (Packaging)
The project provides a one-key build script `build.bat`:
1. Run `build.bat`.
2. Enter the version number.
3. The script automatically executes PyInstaller packaging and Inno Setup compilation.
4. The final installer will be output to the `setup_exe/` directory.

## Logging & Analysis
- **Logging**: The system generates a timestamped log file for every start (Format: `YYYYMMDD_HHMMSS.log`).
- **Performance Analysis**: Select "Generate Gantt Chart" from the tray menu to generate a performance analysis report based on the current log.

## Tech Stack
- **Language**: Python
- **GUI**: Tkinter / PyStray
- **Imaging**: OpenCV / PIL
- **Installer**: Inno Setup 6

## Version Info

v1.02 : 修改配置文件默认目录到%APPDATA%，增加stitch监控日志
v1.03 : 解决高频转发导致打印机驱动崩溃问题，改为8M发一次解决
v1.04 : 修复图像采集问题、修复离线图像拼接问题
v1.05 : 更新倪工标定函数、修复拼接10秒超时bug、修复拼接生成图DPI问题、拼接图像前配置参数后,无需一键启动,可直接拼接、输入打印宽度和DPI,将实时修改画布结束位置,画布结束位置禁止人工修改
v1.05 : 增加新旧标定程序切换功能、新增热文件夹监测功能、增加camera帧&行超时设置、增加debug存图模式
v1.06 : 更新标定程序[2026-06-24] 
v1.07 : 增加拼接超时参数设置[2026-06-29]
v1.08 : 修复灯光配置[2026-07-03] 
v1.09 : 运行前自动清空监控热文件夹；增加多语言支持[2026-07-07]
v1.10 : 标定图像导出[2026-07-10]，修改采集模式下图像输出编号命名方式以适配热文件夹下识别功能
v1.11 : 标定图像导出[2026-07-28]，增加采集时显示拼接图像功能
v1.12 : 接缝闭环校正 + 双 YAML 标定；实时显示内存修复[2026-08-24]，详见下方「v1.12 现场部署说明」
v1.13 : 合入流式拼接器（stitch_stream_final/v2 + fastcore，项目根目录）；托盘离线拼接改走流式拼接+边缘视差补偿（fastcore 默认开，数值逐位等价已验证），产物在采集目录 stitch_stream/ 下；**实时打印转发路径也换成流式引擎**（StreamRealtime，带口径与旧路径一致，可经 .syscfg 的 stream_realtime 回退旧引擎），逐机常数见 .syscfg 的 stream_* 键与参数设置界面[2026-09-10]

---

# v1.12 现场部署说明

本版新增两项拼接改动，**默认已开启，但都需要确认配置才真正生效**。看不懂细节没关系，照「三步接上」做完即可。

## 零、先确认一件事：你运行的是 exe 还是源码

这决定了替换文件有没有用。

- 如果现场是双击 `C:\Program Files (x86)\VisionDriverBox\vsDriverBox.exe` 启动的 —— **直接替换本文件夹里的 .py 不起作用**，exe 是打包好的。必须选一条：
  - **A. 重新打包**：在本文件夹执行 `build.bat`（版本号自动从 `main.py` 的 `APP_VERSION` 读取，要改就改那一行），装 `setup_exe\` 下新生成的安装包
  - **B. 先跑源码验证**：`pip install -r requirements.txt` 后 `python main.py`，确认没问题再按 A 打包
- 如果现场本来就是跑 `python main.py`，替换文件夹即可。

## 一、压缩包里已经齐了，不需要再从别处拷任何东西

| 需要的东西 | 位置 | 状态 |
|---|---|---|
| 正向标定（T 向） | `calib\4_registered_calib.yaml` | 已包含 |
| 反向标定（F 向） | `calib\3_hflip_registered_calib.yaml` | 已包含 |
| 闭环校正模块 | `drivers\camera\SeamRefine.py` | 已包含 |
| 相机 SDK DLL | `drivers\camera\DLL\`（15 个） | 已包含 |
| 多语言文案 | `translations.yaml` | 已包含 |

这两份 YAML 是**配对**的，必须成对使用，不能只换一个，也不能和别处的 `4_calib.yaml` 混用（见第四节）。

`.spec` 已把 `calib\*.yaml` 和 `translations.yaml` 加进打包清单，所以重新打包后它们会跟着进安装目录。顺带修了一个老问题：`translations.yaml` 此前从未被打包，安装版一直在用代码内置文案。

## 二、三步接上

### 第 1 步：找到真正生效的配置文件

配置按这个顺序找，**第一个存在的就赢**，后面的不看：

1. `%APPDATA%\VisionDriverBox\.syscfg` ← 现场就是这个（`C:\Users\<用户名>\AppData\Roaming\VisionDriverBox\.syscfg`）
2. `D:\vsDriverbox\.syscfg`
3. `<安装目录>\src\.syscfg`

该文件带隐藏属性，资源管理器里要先勾「显示隐藏的项目」。

用这条命令确认是哪一个：

```powershell
@("$env:APPDATA\VisionDriverBox\.syscfg", "D:\vsDriverbox\.syscfg", "C:\Program Files\VisionDriverBox\src\.syscfg", "C:\Program Files (x86)\VisionDriverBox\src\.syscfg") | ForEach-Object { "$_ => $(Test-Path $_)" }
```

### 第 2 步：改四个键

在第 1 步找到的那份文件里，改成下面这样（也可以在托盘「参数设置」里点，效果相同）：

```json
"cal_sel": "new",
"calib_file": "calib\\4_registered_calib.yaml",
"calib_file_false": "calib\\3_hflip_registered_calib.yaml",
"seam_refine": true
```

要点：

- `calib_file` **必须改**。现场原值指向桌面上的 `4_calib.yaml`，那是**未配准**的标定，配不上新的反向标定 —— 程序会检测到并自动退回旧行为，等于白装
- 这两个路径是**相对安装目录**的，程序会自动解析，不用写绝对路径、也不用手工拷 YAML
- `cal_sel` 现场原值是 `"新版"`，程序仍然认（`"新版"`/`"New Version"`/`"Phiên bản mới"` 都认）。建议顺手改成 `"new"`：老写法在切换界面语言后会失效
- `seam_refine` 和 `calib_file_false` 现场原本没有这两个键，会自动取新默认值（开启）。**建议显式写上**，免得以后看不出当前状态

### 第 3 步：启动后看日志确认

日志在 `D:\vsDriverbox\log\` 下，文件名是启动时间。搜 `Camera:`：

- **没有任何 `Camera:` 开头的告警** → 双 YAML 已生效，接上了
- 出现 `not a compatible calibration pair` → 两份标定不配对，已自动退回旧行为。**回去检查第 2 步的 `calib_file`**
- 出现 `single calibration, target_grid ignored` → 只加载到一份标定，走的是旧行为。检查 `calib_file_false` 路径
- 出现 `failed to load` → 标定文件解析失败，后面跟着具体原因

## 三、怎么关掉（回滚）

不用换代码，改配置即可，两项互相独立：

- 关双 YAML：`"calib_file_false": ""`
- 关闭环校正：`"seam_refine": false`
- 两项都关 → 行为与 v1.11 完全一致

标定文件也可以直接换回原来的绝对路径。

## 四、必须知道的两条限制

### 1. 闭环会跟随布面歪斜，余量用尽时会主动停机

闭环让接缝跟着布走，所以裁剪窗口会持续朝一个方向平移。这是正确行为，但余量有限：窗口 `[canvas_start_pos, canvas_start_pos + 画布宽度)` 两侧的剩余像素就是全部预算。

余量耗尽时程序**主动报错停机**，日志里是 `pushes the cut window ... outside the rectified strip`，并给出可用余量。**这是刻意设计的** —— 夹住边界继续印会得到看不出来的错接缝，停机损失更小。

遇到这个报错的处理：重新标定，或把布面重新对正，然后重启。不要靠调 `canvas_start_pos` 硬扛。

### 2. 我们的验收数字来自另一台机器的几何

实验室验证结果（接缝中位误差 0.19 px、超过 1 px 占比 0）是在另一套几何常数下测的，和现场这台不同：

- `img_stitch_offset` 现场 546 / 实验室 629
- `canvas_start_pos` 现场 3000 / 实验室 7906
- `stitch_left_ref`、`stitch_right_ref` 也不同

**所以别把 0.19 px 当成现场的预期值。** 想要现场的准确数字，请提供：这台机自己的标定 YAML + 一段采集数据目录（`D:\vsDriverbox\cap` 下含 `LocalImageInfos.json` 的那种），可以离线跑出这台机的实际基线和收益。

## 五、本版其他修复（不需要配置）

- **实时显示内存泄漏**：原先每条拼接结果都累积保留并整体重算，长时间打印会耗尽内存、界面卡死。改为固定窗口滚动显示。副作用：查看器的「保存图像」只保存最近约 5 条的范围，完整图像仍然经数据端口正常输出
- **界面语言与标定选择解耦**：`cal_sel` 改用语言无关的取值，切到英文/越南语界面后不再误判成旧标定
- **实时查看器退出**：不再依赖强制结束进程
- **配置项 `seam_refine` 的取值解析**：手工把它写成字符串 `"false"` 时不再被当成开启

## 六、已知遗留问题（本版未处理）

- 「标定图像导出」复选框实际不起作用（`export_calib_img` 未传入相机模块）
- 「导入配置」时下拉框类参数（转发模式、监听模式）不会触发联动刷新
- 托盘离线拼接的超时参数被当作进程通信超时使用，未传到拼接函数

---
© 2026 Jim. All Rights Reserved.
