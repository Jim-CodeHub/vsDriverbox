# -*- coding: utf-8 -*-
import re
import os
from datetime import datetime
import matplotlib.pyplot as plt
from tkinter import messagebox, Tk

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei'] 
plt.rcParams['axes.unicode_minus'] = False

def show_msg(title, content, type='info'):
    root = Tk()
    root.withdraw()
    if type == 'info':
        messagebox.showinfo(title, content, parent=root)
    elif type == 'warning':
        messagebox.showwarning(title, content, parent=root)
    elif type == 'error':
        messagebox.showerror(title, content, parent=root)
    root.destroy()

def parse_log_line(line):
    # Pattern: [2026-05-16 17:06:21.218] [INFO] Message
    pattern = r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\] \[(\w+)\] (.*)'
    match = re.match(pattern, line)
    if match:
        timestamp_str = match.group(1)
        level = match.group(2)
        message = match.group(3)
        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
        return timestamp, level, message
    return None

def generate_gantt_from_log(log_path):
    # 轨道定义：简化为两个核心轨道
    TRACK_NAMES = [
        "Camera Process (Start -> End)",
        "Printer Process (Accept -> Close)"
    ]
    
    # 自动确定 PDF 保存路径 (与日志文件同目录)
    pdf_path = os.path.splitext(log_path)[0] + "_gantt.pdf"
    cam_starts = {} # {idx: ts}
    
    # Printer 状态跟踪: {addr: {'start': ts, 'pkt_id': str}}
    printer_pending = {} 
    
    nodes = [] 

    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                parsed = parse_log_line(line)
                if not parsed: continue
                ts, level, msg = parsed
                
                # --- Camera Logic: ID = [N] + 1 ---
                if "Camera frame started" in msg:
                    idx = re.search(r'\[(\d+)\]', msg).group(1)
                    cam_starts[idx] = ts
                elif "Camera send ended" in msg:
                    idx = re.search(r'\[(\d+)\]', msg).group(1)
                    if idx in cam_starts:
                        start_ts = cam_starts.pop(idx)
                        display_id = int(idx) + 1
                        nodes.append({
                            'track': 0, 'id': f"Cam #{display_id}", 's': start_ts, 'e': ts,
                            'color_key': f"cam_{idx}"
                        })

                # --- Printer Logic: Accept -> Receive(ID) -> Close ---
                elif "Accepted connection from" in msg:
                    addr = re.search(r'from: (.*)', msg).group(1)
                    printer_pending[addr] = {'start': ts, 'pkt_id': None}
                
                elif "received successfully" in msg:
                    # 获取 Packet ID
                    pkt_idx = re.search(r'Packet #(\d+)', msg).group(1)
                    # 假设收到成功的包对应的是该地址当前处于 pending 状态的连接
                    # 如果有多个地址，这里取最后一个匹配到的地址（通常同时只有一个活动连接）
                    if printer_pending:
                        last_addr = list(printer_pending.keys())[-1]
                        printer_pending[last_addr]['pkt_id'] = pkt_idx
                
                elif "Connection closed" in msg:
                    addr = re.search(r'closed: (.*)', msg).group(1)
                    if addr in printer_pending:
                        info = printer_pending.pop(addr)
                        if info['pkt_id'] is not None:
                            nodes.append({
                                'track': 1, 'id': f"Pkt #{info['pkt_id']}", 
                                's': info['start'], 'e': ts,
                                'color_key': f"prt_{info['pkt_id']}"
                            })

        if not nodes:
            show_msg("解析结果", "未发现符合条件的成组事件（需包含完整的起止流程）", type='warning')
            return

        # 增加处理的数据组数，从 30 增加到 100，以便观察更长周期的系统表现
        nodes = nodes[:100]
        start_time = min(n['s'] for n in nodes)
        
        # 计算相对时间和耗时
        for n in nodes:
            n['s_rel'] = (n['s'] - start_time).total_seconds()
            n['e_rel'] = (n['e'] - start_time).total_seconds()
            n['p'] = n['e_rel'] - n['s_rel']

        # 动态宽度：由于数据量增加，进一步优化宽度计算逻辑
        dynamic_width = max(18, len(nodes) * 0.7) # 略微收紧单组宽度，防止图表过长难以操作
        # 拉大高度比例，确保多组数据下的视觉空间
        fig, ax = plt.subplots(figsize=(dynamic_width, 12), dpi=150, constrained_layout=True)
        ax.set_facecolor('white')
        
        COLORS = ['#d35400', '#2980b9', '#27ae60', '#8e44ad', '#f39c12', '#c0392b', '#16a085']
        color_map = {}
        
        # 定义轨道纵向坐标，拉大间距 (从之前的 0, 1 变为 0, 3)
        # 这样即使有上下错位的标签，也不会跑到邻近轨道的区域
        TRACK_Y = [0, 3] 
        
        # 绘制背景轨道线
        for y in TRACK_Y:
            ax.axhline(y, color='#eeeeee', linewidth=2, zorder=0)
        
        # 绘制节点
        for i, node in enumerate(nodes):
            # 获取拉大后的 Y 坐标
            t_idx = TRACK_Y[node['track']]
            s = node['s_rel']
            e = node['e_rel']
            p = node['p']
            
            if node['color_key'] not in color_map:
                color_map[node['color_key']] = COLORS[len(color_map) % len(COLORS)]
            c = color_map[node['color_key']]
            
            # 1. 绘制中间的连接线 (Bar)
            ax.plot([s, e], [t_idx, t_idx], color=c, linewidth=4, solid_capstyle='round', zorder=2)
            
            # 2. 绘制端点圆圈
            ax.scatter([s, e], [t_idx, t_idx], color='white', edgecolors=c, s=40, linewidths=2, zorder=3)
            
            # 3. 绘制标签框 (Box)
            label_text = (f"Id: {node['id']}\n"
                         f"S: {s:.3f}s\n"
                         f"E: {e:.3f}s\n"
                         f"P: {p:.3f}s")
            
            # 4 级垂直错位，收紧偏移量以防止跨行
            stagger = [1.0, 0.5, -0.5, -1.0]
            offset = stagger[i % 4]
            
            # 指引虚线
            ax.plot([s + (e-s)/2, s + (e-s)/2], [t_idx, t_idx + offset], 
                    linestyle='--', color=c, linewidth=0.8, alpha=0.3, zorder=1)
            
            # 标签文本
            ax.text(s + (e-s)/2, t_idx + offset, label_text, 
                    fontsize=7, ha='center', va='center', fontweight='bold',
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=c, lw=2, alpha=1))

        # 坐标轴微调
        ax.set_yticks(TRACK_Y)
        ax.set_yticklabels(TRACK_NAMES, fontsize=12, fontweight='bold')
        # 调整 Y 轴显示范围以匹配拉大后的间距
        ax.set_ylim(min(TRACK_Y) - 1.5, max(TRACK_Y) + 1.5)
        
        ax.set_xlabel('相对时间 / Total Time (秒/s)', fontsize=12)
        ax.set_title(f'甘特图成组分析 (Gantt Style) - {os.path.basename(log_path)}', fontsize=18, pad=30)
        
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.spines['bottom'].set_visible(True)
        ax.spines['bottom'].set_color('#dddddd')
        
        ax.xaxis.grid(True, linestyle='--', color='#f0f0f0', alpha=0.8)

        # 保存为 PDF
        plt.savefig(pdf_path, format='pdf', bbox_inches='tight')
        plt.close(fig) # 自动关闭绘图对象释放内存

        return pdf_path

    except Exception as e:
        import traceback
        show_msg("生成错误", f"解析失败：\n{str(e)}\n\n{traceback.format_exc()}", type='error')
