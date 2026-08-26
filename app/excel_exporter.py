"""Excel 导出 — 将 JD + AI 分析结果保存为 Excel 文件

导出内容：
- 时间戳
- 岗位名称、公司、薪资
- AI 匹配分数、是否匹配、匹配理由
- AI 优势、劣势、建议打招呼消息
- 投递状态（已投递/已跳过）
"""
import os
import time
import threading
from typing import Optional

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
JD_DIR = os.path.join(DATA_DIR, "jd_analysis")

# 表头样式
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
HEADER_FILL = PatternFill(start_color="5b7cfa", end_color="5b7cfa", fill_type="solid")
HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
THIN_BORDER = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin"),
)

# 匹配/不匹配行填充
MATCH_FILL = PatternFill(start_color="e8f5e9", end_color="e8f5e9", fill_type="solid")
SKIP_FILL = PatternFill(start_color="fff3e0", end_color="fff3e0", fill_type="solid")

_lock = threading.Lock()


def _ensure_jd_dir():
    os.makedirs(JD_DIR, exist_ok=True)


def _get_workbook(path: str) -> openpyxl.Workbook:
    """加载现有工作簿或创建新的。"""
    if os.path.exists(path):
        return openpyxl.load_workbook(path)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "JD分析记录"
    _write_header(ws)
    return wb


def _write_header(ws):
    """写入表头。"""
    headers = [
        "时间", "岗位名称", "公司", "薪资", "城市",
        "AI匹配分", "是否匹配", "匹配理由",
        "AI优势", "AI劣势", "建议打招呼",
        "投递状态", "岗位URL", "使用的提示词",
    ]
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = HEADER_ALIGN
        cell.border = THIN_BORDER


def _auto_width(ws):
    """自动调整列宽。"""
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                val = str(cell.value) if cell.value else ""
                # 中文字符算2个宽度
                width = sum(2 if ord(c) > 127 else 1 for c in val)
                if width > max_len:
                    max_len = width
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max_len + 4, 50)


def save_jd_analysis(
    job: dict,
    ai_result: Optional[dict] = None,
    skipped: bool = False,
    query: str = "",
    city: str = "",
    prompt_used: str = "",
) -> str:
    """保存一条 JD + AI 分析记录到 Excel。

    Args:
        job: 岗位信息字典
        ai_result: AI 分析结果（可选）
        skipped: 是否跳过
        query: 搜索关键词
        city: 城市
        prompt_used: 使用的提示词摘要

    Returns:
        保存的文件路径
    """
    _ensure_jd_dir()
    with _lock:
        # 按日期分文件
        date_str = time.strftime("%Y-%m-%d")
        filename = f"JD分析_{date_str}.xlsx"
        filepath = os.path.join(JD_DIR, date_str, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        wb = _get_workbook(filepath)
        ws = wb["JD分析记录"]

        # 追加行
        row_idx = ws.max_row + 1
        score = ai_result.get("score", "") if ai_result else ""
        is_match = "是" if (ai_result and ai_result.get("is_match")) else "否" if ai_result else ""
        reason = ai_result.get("reason", "") if ai_result else ""
        strengths = ", ".join(ai_result.get("strengths", [])) if ai_result else ""
        weaknesses = ", ".join(ai_result.get("weaknesses", [])) if ai_result else ""
        suggested = ai_result.get("suggested_greeting", "") if ai_result else ""
        status = "已跳过" if skipped else "已投递"

        row_data = [
            time.strftime("%Y-%m-%d %H:%M:%S"),
            job.get("job_name", ""),
            job.get("company", ""),
            job.get("salary", ""),
            city,
            score,
            is_match,
            reason,
            strengths,
            weaknesses,
            suggested,
            status,
            job.get("url", ""),
            prompt_used[:500] if prompt_used else "",  # 限制长度
        ]

        for col_idx, val in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.border = THIN_BORDER
            cell.alignment = Alignment(wrap_text=True, vertical="center")
            if status == "已投递":
                cell.fill = MATCH_FILL
            elif status == "已跳过":
                cell.fill = SKIP_FILL

        _auto_width(ws)
        wb.save(filepath)
        return filepath


def get_analysis_files() -> list:
    """获取所有分析 Excel 文件列表。"""
    _ensure_jd_dir()
    files = []
    for f in os.listdir(JD_DIR):
        if f.endswith(".xlsx"):
            path = os.path.join(JD_DIR, f)
            files.append({
                "name": f,
                "path": path,
                "size": os.path.getsize(path),
                "mtime": os.path.getmtime(path),
            })
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return files
