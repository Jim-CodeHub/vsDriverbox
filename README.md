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

---
© 2026 Jim. All Rights Reserved.
