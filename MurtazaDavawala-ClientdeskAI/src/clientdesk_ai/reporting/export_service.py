"""Reporting and export utilities for Excel and PDF."""

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from src.clientdesk_ai.domain.models import Engagement, EngagementChecklistItem
from src.clientdesk_ai.config.settings import CONFIG


class ReportExportService:
    @staticmethod
    def export_engagements_to_excel(engagements: List[Engagement], output_path: Path) -> Path:
        """Generate a formatted Excel workbook of engagements."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Engagements"

        # Headers
        headers = [
            "Engagement ID", "Client Name", "Service", "Financial Year",
            "Period", "Due Date", "Priority", "Status", "Assigned Operator", "Reviewer"
        ]
        ws.append(headers)

        header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        border_thin = Border(
            left=Side(style="thin", color="E2E8F0"),
            right=Side(style="thin", color="E2E8F0"),
            top=Side(style="thin", color="E2E8F0"),
            bottom=Side(style="thin", color="E2E8F0")
        )

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        data_font = Font(name="Segoe UI", size=10)
        for r_idx, eng in enumerate(engagements, start=2):
            row_data = [
                f"ENG-{eng.engagement_id:04d}",
                eng.client_name,
                eng.service_name,
                eng.financial_year,
                eng.tax_period,
                eng.due_date,
                eng.priority.value,
                eng.status.value,
                eng.assigned_name or "Unassigned",
                eng.reviewer_name or "Unassigned"
            ]
            ws.append(row_data)
            for c_idx in range(1, len(row_data) + 1):
                c = ws.cell(row=r_idx, column=c_idx)
                c.font = data_font
                c.border = border_thin

        # Auto-adjust column widths
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(output_path))
        return output_path

    @staticmethod
    def export_checklist_to_excel(engagement: Engagement, items: List[EngagementChecklistItem], output_path: Path) -> Path:
        """Generate a client-ready checklist Excel export."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Document Checklist"

        ws.append(["CLIENT SERVICE DOCUMENT CHECKLIST"])
        ws.append([f"Client: {engagement.client_name} | Service: {engagement.service_name} | FY: {engagement.financial_year}"])
        ws.append([f"Status: {engagement.status.value} | Due Date: {engagement.due_date}"])
        ws.append([])

        headers = ["#", "Category", "Document Name", "Requirement", "Applicability", "Status", "Received Date", "Remarks"]
        ws.append(headers)

        header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
        title_font = Font(name="Segoe UI", size=14, bold=True, color="0F172A")
        data_font = Font(name="Segoe UI", size=10)

        ws.cell(row=1, column=1).font = title_font

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=5, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill

        for idx, itm in enumerate(items, start=1):
            ws.append([
                idx,
                itm.category_name,
                itm.document_name_snapshot,
                itm.requirement_snapshot.value,
                itm.applicability_status.value,
                itm.collection_status.value,
                itm.received_date or "-",
                itm.waiver_reason or itm.deficiency_reason or itm.internal_remarks
            ])
            curr_row = 5 + idx
            for c_idx in range(1, len(headers) + 1):
                ws.cell(row=curr_row, column=c_idx).font = data_font

        output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(output_path))
        return output_path
