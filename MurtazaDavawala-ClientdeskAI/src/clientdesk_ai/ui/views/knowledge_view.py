"""Local knowledge base & SOP full-text search powered offline by SQLite FTS5."""

from typing import Optional, Dict, Any, List
from src.clientdesk_ai.ui.qt_compat import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QTextEdit, QSplitter,
    QDialog, QComboBox, QMessageBox, Qt
)
from src.clientdesk_ai.ui.theme import configure_modern_table
from src.clientdesk_ai.domain.models import UserRole


class KnowledgeArticleDialog(QDialog):
    """Dialog for creating or updating SOP Knowledge articles in the Firm Wiki."""

    def __init__(self, main_window, article_data: Optional[Dict[str, Any]] = None, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.article_data = article_data
        is_edit = bool(article_data)

        self.setWindowTitle("Edit SOP / Article" if is_edit else "Add New SOP / Article")
        self.resize(640, 520)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        t_lbl = QLabel("<b>Article Title:</b>")
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("e.g. GST Registration Verification Protocol")
        layout.addWidget(t_lbl)
        layout.addWidget(self.title_edit)

        # Service Group
        sg_lbl = QLabel("<b>Service Group:</b>")
        self.service_combo = QComboBox()
        self.service_combo.setEditable(True)
        default_groups = [
            "General Compliance", "GST", "ITR", "Company Formation",
            "Partnership Registration", "LLP Incorporation", "MCA Annual Compliance", "Other"
        ]
        existing_groups: List[str] = []
        try:
            repo = getattr(self.main_window, "knowledge_repo", None) or self.main_window.log_repo
            if hasattr(repo, "list_groups"):
                existing_groups = repo.list_groups()
        except Exception:
            pass

        all_groups = []
        for g in existing_groups + default_groups:
            if g and g not in all_groups:
                all_groups.append(g)

        for g in all_groups:
            self.service_combo.addItem(g)
        layout.addWidget(sg_lbl)
        layout.addWidget(self.service_combo)

        # Article Content
        c_lbl = QLabel("<b>Article Content / SOP Guidelines:</b>")
        self.content_edit = QTextEdit()
        self.content_edit.setPlaceholderText("Enter comprehensive statutory rules, verification steps, checklist items, and exceptions...")
        self.content_edit.setStyleSheet(
            "font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; line-height: 1.5; "
            "background-color: #FFFFFF; border: 1.5px solid #CBD5E1; border-radius: 6px; padding: 10px;"
        )
        layout.addWidget(c_lbl)
        layout.addWidget(self.content_edit)

        # If editing, populate existing values
        if article_data:
            self.title_edit.setText(article_data.get("title", ""))
            sg = article_data.get("service_group", "")
            idx = self.service_combo.findText(sg)
            if idx >= 0:
                self.service_combo.setCurrentIndex(idx)
            else:
                self.service_combo.setEditText(sg)
            self.content_edit.setPlainText(article_data.get("content", ""))

        # Buttons
        btn_bar = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setProperty("class", "btn-secondary")
        btn_cancel.setMinimumHeight(36)
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("Save Article")
        btn_save.setProperty("class", "btn-primary")
        btn_save.setMinimumHeight(36)
        btn_save.clicked.connect(self.save_article)

        btn_bar.addStretch()
        btn_bar.addWidget(btn_cancel)
        btn_bar.addWidget(btn_save)
        layout.addLayout(btn_bar)

    def save_article(self):
        title = self.title_edit.text().strip()
        service_group = self.service_combo.currentText().strip() or "General Compliance"
        content = self.content_edit.toPlainText().strip()

        if not title:
            QMessageBox.warning(self, "Validation Error", "Please provide a title for the knowledge article.")
            self.title_edit.setFocus()
            return

        if not content:
            QMessageBox.warning(self, "Validation Error", "Article content cannot be empty.")
            self.content_edit.setFocus()
            return

        repo = getattr(self.main_window, "knowledge_repo", None) or self.main_window.log_repo
        try:
            if self.article_data:
                doc_id = self.article_data["doc_id"]
                repo.update_knowledge(doc_id, title=title, content=content, service_group=service_group)
                QMessageBox.information(self, "Article Updated", f"Successfully updated SOP '{title}'.")
            else:
                repo.add_knowledge(title=title, service_group=service_group, content=content)
                QMessageBox.information(self, "Article Created", f"Successfully added new SOP '{title}'.")

            # Refresh FTS5 index
            if hasattr(self.main_window, "search_service") and hasattr(self.main_window.search_service, "rebuild_index"):
                self.main_window.search_service.rebuild_index()

            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to save article:\n{e}")


class KnowledgeView(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.init_ui()

    def check_manage_permission(self) -> bool:
        """Only ADMIN, PARTNER, and SENIOR roles can add/edit/delete Knowledge articles."""
        user = getattr(self.main_window, "current_user", None)
        if not user:
            return False
        role_str = str(user.role.value if hasattr(user.role, "value") else user.role).upper()
        return role_str in ("ADMIN", "PARTNER", "SENIOR", "USERROLE.ADMIN", "USERROLE.PARTNER", "USERROLE.SENIOR")

    def create_kpi_card(self, title: str, value: str, accent_color: str) -> QFrame:
        card = QFrame()
        card.setProperty("class", "card")
        card.setFixedHeight(54)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(12, 4, 12, 4)
        c_layout.setSpacing(1)

        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("font-size: 10px; font-weight: 600; color: #64748B; letter-spacing: 0.5px;")
        v_lbl = QLabel(value)
        v_lbl.setObjectName("kpi_value")
        v_lbl.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {accent_color};")

        c_layout.addWidget(t_lbl)
        c_layout.addWidget(v_lbl)
        return card

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 14, 24, 14)
        layout.setSpacing(10)

        # 1. Header with "+ Add New SOP / Article" on top right
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title_lbl = QLabel("Firm Wiki & SOP Knowledge Base")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: 700; color: #0F172A;")
        sub_lbl = QLabel("Dynamic offline full-text indexed retrieval for compliance SOPs, statutory thresholds, and checklist guidelines.")
        sub_lbl.setStyleSheet("font-size: 12.5px; color: #64748B;")
        title_box.addWidget(title_lbl)
        title_box.addWidget(sub_lbl)
        header_layout.addLayout(title_box)
        header_layout.addStretch()

        self.btn_add = QPushButton("+ Add New SOP / Article")
        self.btn_add.setProperty("class", "btn-primary")
        self.btn_add.setMinimumHeight(32)
        self.btn_add.clicked.connect(self.open_add_dialog)
        header_layout.addWidget(self.btn_add)

        btn_rebuild = QPushButton("🔄 Rebuild Index")
        btn_rebuild.setProperty("class", "btn-secondary")
        btn_rebuild.setMinimumHeight(32)
        btn_rebuild.clicked.connect(self.rebuild_search_index)
        header_layout.addWidget(btn_rebuild)

        layout.addLayout(header_layout)

        # 2. Executive SOP KPI Metric Cards (Compact 62px height)
        cards_grid = QGridLayout()
        cards_grid.setSpacing(10)

        self.card_total = self.create_kpi_card("TOTAL KNOWLEDGE ARTICLES", "0", "#2563EB")
        self.card_groups = self.create_kpi_card("SERVICE DISCIPLINES", "0", "#0D9488")
        self.card_status = self.create_kpi_card("FULL-TEXT SEARCH", "FTS5 Active", "#059669")
        self.card_scope = self.create_kpi_card("PRACTICE COMPLIANCE", "Internal SOP Wiki", "#D97706")

        cards_grid.addWidget(self.card_total, 0, 0)
        cards_grid.addWidget(self.card_groups, 0, 1)
        cards_grid.addWidget(self.card_status, 0, 2)
        cards_grid.addWidget(self.card_scope, 0, 3)
        layout.addLayout(cards_grid)

        # 3. Filter & Search Toolbar Card (Compact 46px height)
        filter_card = QFrame()
        filter_card.setProperty("class", "card")
        filter_card.setFixedHeight(46)
        fc_layout = QHBoxLayout(filter_card)
        fc_layout.setContentsMargins(12, 6, 12, 6)
        fc_layout.setSpacing(10)

        lbl_filter = QLabel("<b>Filter:</b>")
        lbl_filter.setStyleSheet("color: #0F172A; font-size: 12px;")
        fc_layout.addWidget(lbl_filter)

        self.group_combo = QComboBox()
        self.group_combo.setFixedHeight(28)
        self.group_combo.addItem("All Service Groups")
        self.group_combo.currentIndexChanged.connect(self.perform_search)
        fc_layout.addWidget(self.group_combo)

        self.search_edit = QLineEdit()
        self.search_edit.setFixedHeight(28)
        self.search_edit.setPlaceholderText("Search SOPs, thresholds, rules (e.g. 'turnover threshold', 'SPICe+', 'DIR-3', 'Form 16')...")
        self.search_edit.textChanged.connect(self.perform_search)
        self.search_edit.returnPressed.connect(self.perform_search)
        fc_layout.addWidget(self.search_edit)

        btn_search = QPushButton("Search")
        btn_search.setProperty("class", "btn-primary")
        btn_search.setFixedHeight(28)
        btn_search.setStyleSheet("padding: 4px 12px; font-size: 12px;")
        btn_search.clicked.connect(self.perform_search)
        fc_layout.addWidget(btn_search)

        btn_clear = QPushButton("Clear")
        btn_clear.setProperty("class", "btn-secondary")
        btn_clear.setFixedHeight(28)
        btn_clear.setStyleSheet("padding: 4px 12px; font-size: 12px;")
        btn_clear.clicked.connect(self.clear_search)
        fc_layout.addWidget(btn_clear)

        fc_layout.addStretch()

        fts_pill = QLabel("⚡ SQLite FTS5: BM25 Ranked Offline Search")
        fts_pill.setFixedHeight(26)
        fts_pill.setStyleSheet(
            "color: #0369A1; font-size: 11px; font-weight: 600; background-color: #F0F9FF; "
            "border: 1px solid #BAE6FD; border-radius: 4px; padding: 3px 8px;"
        )
        fc_layout.addWidget(fts_pill)
        layout.addWidget(filter_card)

        # 4. Splitter: Results Table on Left, Passage Reader on Right (stretch 1 to fill available height)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left Card: Matching Articles Table
        left_card = QFrame()
        left_card.setProperty("class", "card")
        left_card.setMinimumWidth(360)
        left_card.setMaximumWidth(480)
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(8)

        self.res_title = QLabel("Knowledge Articles & SOPs")
        self.res_title.setStyleSheet("font-size: 14px; font-weight: 600; color: #0F172A;")
        left_layout.addWidget(self.res_title)

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(2)
        self.results_table.setHorizontalHeaderLabels(["Group", "Article Title"])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.results_table.setColumnWidth(0, 140)
        configure_modern_table(self.results_table)
        self.results_table.itemSelectionChanged.connect(self.on_article_selected)
        self.results_table.cellClicked.connect(lambda r, c: self.on_article_selected())
        self.results_table.itemClicked.connect(lambda itm: self.on_article_selected())
        self.results_table.cellDoubleClicked.connect(lambda r, c: self.open_edit_dialog())
        left_layout.addWidget(self.results_table)

        splitter.addWidget(left_card)

        # Right Card: Passage Reader & Action Buttons
        right_card = QFrame()
        right_card.setProperty("class", "card")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(12)

        r_header = QHBoxLayout()
        self.doc_title_lbl = QLabel("Select an article to view procedural instructions.")
        self.doc_title_lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #0F172A;")
        r_header.addWidget(self.doc_title_lbl)
        r_header.addStretch()

        self.btn_edit = QPushButton("✏️ Edit SOP")
        self.btn_edit.setProperty("class", "btn-secondary")
        self.btn_edit.setMinimumHeight(32)
        self.btn_edit.clicked.connect(self.open_edit_dialog)
        self.btn_edit.setEnabled(False)

        self.btn_delete = QPushButton("🗑️ Delete")
        self.btn_delete.setProperty("class", "btn-danger")
        self.btn_delete.setMinimumHeight(32)
        self.btn_delete.clicked.connect(self.delete_selected_article)
        self.btn_delete.setEnabled(False)

        r_header.addWidget(self.btn_edit)
        r_header.addWidget(self.btn_delete)
        right_layout.addLayout(r_header)

        self.doc_reader = QTextEdit()
        self.doc_reader.setReadOnly(True)
        self.doc_reader.setStyleSheet(
            "font-family: 'Segoe UI', Arial, sans-serif; font-size: 13.5px; line-height: 1.6; "
            "color: #1E293B; background-color: #FFFFFF; border: 1px solid #E2E8F0; "
            "border-radius: 6px; padding: 12px;"
        )
        right_layout.addWidget(self.doc_reader)

        splitter.addWidget(right_card)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([380, 720])
        layout.addWidget(splitter, 1)

        # Initial Security State & Auto-populate articles
        self.update_security_state()
        self.refresh_data()

    def update_security_state(self):
        can_manage = self.check_manage_permission()
        self.btn_add.setVisible(can_manage)
        self.btn_edit.setVisible(can_manage)
        self.btn_delete.setVisible(can_manage)

    def refresh_data(self):
        self.update_security_state()

        # Refresh group dropdown dynamically
        cur_group = self.group_combo.currentText()
        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        self.group_combo.addItem("All Service Groups")
        groups: List[str] = []
        try:
            repo = getattr(self.main_window, "knowledge_repo", None) or self.main_window.log_repo
            if hasattr(repo, "list_groups"):
                groups = repo.list_groups()
        except Exception:
            pass

        for g in groups:
            self.group_combo.addItem(g)

        idx = self.group_combo.findText(cur_group)
        if idx >= 0:
            self.group_combo.setCurrentIndex(idx)
        else:
            self.group_combo.setCurrentIndex(0)
        self.group_combo.blockSignals(False)

        self.perform_search()

    def clear_search(self):
        self.search_edit.clear()
        self.group_combo.setCurrentIndex(0)
        self.perform_search()

    def rebuild_search_index(self):
        try:
            if hasattr(self.main_window, "search_service") and hasattr(self.main_window.search_service, "rebuild_index"):
                self.main_window.search_service.rebuild_index()
            QMessageBox.information(self, "Index Rebuilt", "SQLite FTS5 full-text index rebuilt successfully.")
            self.refresh_data()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to rebuild index:\n{e}")

    def get_selected_article(self) -> Optional[Dict[str, Any]]:
        row = self.results_table.currentRow()
        if row < 0:
            return None
        item = self.results_table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def open_add_dialog(self):
        if not self.check_manage_permission():
            QMessageBox.warning(self, "Permission Denied", "Only ADMIN, PARTNER, or SENIOR roles can add SOP articles.")
            return
        dlg = KnowledgeArticleDialog(self.main_window, article_data=None, parent=self)
        if dlg.exec():
            self.refresh_data()

    def open_edit_dialog(self):
        if not self.check_manage_permission():
            QMessageBox.warning(self, "Permission Denied", "Only ADMIN, PARTNER, or SENIOR roles can edit SOP articles.")
            return
        article = self.get_selected_article()
        if not article:
            QMessageBox.information(self, "Selection Required", "Please select an article from the list to edit.")
            return
        dlg = KnowledgeArticleDialog(self.main_window, article_data=article, parent=self)
        if dlg.exec():
            self.refresh_data()

    def delete_selected_article(self):
        if not self.check_manage_permission():
            QMessageBox.warning(self, "Permission Denied", "Only ADMIN, PARTNER, or SENIOR roles can delete SOP articles.")
            return
        article = self.get_selected_article()
        if not article:
            QMessageBox.information(self, "Selection Required", "Please select an article to delete.")
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to permanently delete SOP article:\n\n'<b>{article.get('title')}</b>'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        repo = getattr(self.main_window, "knowledge_repo", None) or self.main_window.log_repo
        try:
            repo.delete_knowledge(article["doc_id"])
            if hasattr(self.main_window, "search_service") and hasattr(self.main_window.search_service, "rebuild_index"):
                self.main_window.search_service.rebuild_index()
            QMessageBox.information(self, "Article Deleted", f"Deleted article '{article.get('title')}'.")
            self.refresh_data()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete article:\n{e}")

    def perform_search(self):
        query = self.search_edit.text().strip()
        group = self.group_combo.currentText().strip()
        selected_group = group if group != "All Service Groups" else None

        results = self.main_window.search_service.search(query, service_group=selected_group)
        self.results_table.setRowCount(0)

        # Update KPI cards
        total_count = len(results)
        unique_groups = len({r["service_group"] for r in results if r.get("service_group")})
        self.card_total.findChild(QLabel, "kpi_value").setText(str(total_count))
        self.card_groups.findChild(QLabel, "kpi_value").setText(str(unique_groups))
        self.res_title.setText(f"Knowledge Articles & SOPs ({total_count})")

        for idx, res in enumerate(results):
            self.results_table.insertRow(idx)

            grp_item = QTableWidgetItem(res["service_group"])
            grp_item.setData(Qt.ItemDataRole.UserRole, res)
            self.results_table.setItem(idx, 0, grp_item)

            self.results_table.setItem(idx, 1, QTableWidgetItem(res["title"]))

        if results:
            self.results_table.setCurrentCell(0, 0)
            self.on_article_selected()
        else:
            self.doc_title_lbl.setText("No matching procedural instructions found.")
            self.doc_reader.setPlainText(
                "No knowledge articles or SOP guidelines matched your search criteria.\n\n"
                "• Try searching with broader keywords (e.g. 'turnover', 'DIR-3', 'SPICe+', 'GST', 'ITR', 'Form 16').\n"
                "• Clear the Service Group filter to search across all practice areas.\n"
                "• Click '+ Add New SOP / Article' on the top right to document practice guidelines."
            )
            self.btn_edit.setEnabled(False)
            self.btn_delete.setEnabled(False)

    def on_article_selected(self):
        row = self.results_table.currentRow()
        if row < 0:
            self.btn_edit.setEnabled(False)
            self.btn_delete.setEnabled(False)
            return

        item = self.results_table.item(row, 0)
        if not item:
            self.btn_edit.setEnabled(False)
            self.btn_delete.setEnabled(False)
            return

        res_data = item.data(Qt.ItemDataRole.UserRole)
        if not res_data:
            self.btn_edit.setEnabled(False)
            self.btn_delete.setEnabled(False)
            return

        self.doc_title_lbl.setText(f"📖 [{res_data.get('service_group', 'General')}] {res_data.get('title', '')}")
        self.doc_reader.setPlainText(res_data.get("content", ""))

        can_manage = self.check_manage_permission()
        self.btn_edit.setEnabled(can_manage)
        self.btn_delete.setEnabled(can_manage)
