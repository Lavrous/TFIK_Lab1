import sys
import os
import re
import resources_rc
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QMessageBox, QDialog,
    QVBoxLayout, QTextBrowser, QTableWidgetItem, QHeaderView
)
from PySide6.QtGui import QTextCursor
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice, QObject, QEvent, Qt


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class RegexAnalyzer:
    def __init__(self):
        self.patterns = [
            # Числа, начинающиеся на 9
            re.compile(r"(?<![\d\w.,])9\d*(?:[.,]\d+)?\b"),

            # Карты Amex (начинаются с 34 или 37, всего 15 цифр, возможны пробелы или тире)
            re.compile(r"\b(?:34|37)\d{2}[ -]?\d{6}[ -]?\d{5}\b"),

            # Валюты
            re.compile(r"(?:[$€£¥]\s?\d+(?:[.,]\d+)?|\d+(?:[.,]\d+)?\s?[₽€])")
        ]

    def analyze_regex(self, text, pattern_index):
        matches_data = []
        pattern = self.patterns[pattern_index]

        for match in pattern.finditer(text):
            start_abs = match.start()
            end_abs = match.end()
            matched_string = match.group()
            length = end_abs - start_abs

            text_before = text[:start_abs]
            line = text_before.count('\n') + 1
            col = len(text_before.split('\n')[-1]) + 1

            matches_data.append({
                "string": matched_string,
                "line": line,
                "col": col,
                "length": length,
                "start_abs": start_abs,
                "end_abs": end_abs
            })

        return matches_data


class AmexAutomatonAnalyzer:
    def analyze(self, text):
        matches_data = []
        state = 0
        digit_count = 0
        start_abs = -1
        i = 0

        while i < len(text):
            char = text[i]

            if state == 0:
                if char == '3':
                    if i == 0 or not (text[i - 1].isalnum() or text[i - 1] == '_'):
                        state = 1
                        start_abs = i

            elif state == 1:
                if char in '47':
                    state = 2
                    digit_count = 0
                else:
                    i = start_abs
                    state = 0

            elif state == 2:
                if char.isdigit():
                    digit_count += 1
                    if digit_count == 2:
                        state = 3
                else:
                    i = start_abs
                    state = 0

            elif state == 3:
                if char in ' -':
                    state = 4
                    digit_count = 0
                elif char.isdigit():
                    state = 4
                    digit_count = 1  # Разделителя нет, это уже первая цифра второго блока
                else:
                    i = start_abs
                    state = 0

            elif state == 4:
                if char.isdigit():
                    digit_count += 1
                    if digit_count == 6:
                        state = 5
                else:
                    i = start_abs
                    state = 0

            elif state == 5:
                if char in ' -':
                    state = 6
                    digit_count = 0
                elif char.isdigit():
                    state = 6
                    digit_count = 1
                else:
                    i = start_abs
                    state = 0

            elif state == 6:
                if char.isdigit():
                    digit_count += 1
                    if digit_count == 5:
                        if i == len(text) - 1 or not (text[i + 1].isalnum() or text[i + 1] == '_'):
                            end_abs = i + 1
                            matched_string = text[start_abs:end_abs]
                            length = end_abs - start_abs

                            text_before = text[:start_abs]
                            line = text_before.count('\n') + 1
                            col = len(text_before.split('\n')[-1]) + 1

                            matches_data.append({
                                "string": matched_string,
                                "line": line,
                                "col": col,
                                "length": length,
                                "start_abs": start_abs,
                                "end_abs": end_abs
                            })
                            state = 0
                        else:
                            i = start_abs
                            state = 0
                else:
                    i = start_abs
                    state = 0

            i += 1  # Переход к следующему символу

        return matches_data

class LanguageProcessorApp(QObject):
    def __init__(self):
        super().__init__()
        ui_file_name = resource_path("design.ui")
        ui_file = QFile(ui_file_name)
        if not ui_file.open(QIODevice.ReadOnly):
            print(f"Не удалось открыть {ui_file_name}")
            sys.exit(-1)

        loader = QUiLoader()
        self.window = loader.load(ui_file)
        ui_file.close()
        self.current_file_path = None

        self.window.codeArea.setVisible(False)
        self.window.outputTable.setVisible(False)

        if hasattr(self.window, 'regexSelector'):
            self.window.regexSelector.setVisible(False)
            self.window.matchCountLabel.setVisible(False)

        header = self.window.outputTable.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        self.window.outputTable.itemClicked.connect(self.table_click)

        self.regex_analyzer = RegexAnalyzer()
        self.automaton_analyzer = AmexAutomatonAnalyzer()

        self.window.actionAdd.triggered.connect(self.create_file)
        self.window.actionOpen.triggered.connect(self.open_file)
        self.window.actionSave.triggered.connect(self.save_file)
        self.window.actionSaveAs.triggered.connect(self.save_file_as)
        self.window.actionExit.triggered.connect(self.window.close)

        self.window.menuGo.triggered.connect(self.run_code)

        self.window.actionUndo.triggered.connect(self.edit_undo)
        self.window.actionRedo.triggered.connect(self.edit_redo)
        self.window.actionCut.triggered.connect(self.edit_cut)
        self.window.actionCopy.triggered.connect(self.edit_copy)
        self.window.actionPaste.triggered.connect(self.edit_paste)
        self.window.actionDelete.triggered.connect(self.edit_delete)
        self.window.actionSelectAll.triggered.connect(self.edit_select_all)

        self.window.actionNote.triggered.connect(self.show_note)
        self.window.actionAbout.triggered.connect(self.show_about)

        self.window.installEventFilter(self)

    # Вспомогательные функции
    def show_work_areas(self):
        self.window.codeArea.setVisible(True)
        self.window.outputTable.setVisible(True)
        if hasattr(self.window, 'regexSelector'):
            self.window.regexSelector.setVisible(True)
            self.window.matchCountLabel.setVisible(True)

    def get_active_text_area(self):
        focused_widget = QApplication.focusWidget()
        if focused_widget == self.window.codeArea:
            return focused_widget
        return None

    # Функции правки
    def edit_undo(self):
        target = self.get_active_text_area()
        if target: target.undo()

    def edit_redo(self):
        target = self.get_active_text_area()
        if target: target.redo()

    def edit_cut(self):
        target = self.get_active_text_area()
        if target: target.cut()

    def edit_copy(self):
        target = self.get_active_text_area()
        if target: target.copy()

    def edit_paste(self):
        target = self.get_active_text_area()
        if target: target.paste()

    def edit_delete(self):
        target = self.get_active_text_area()
        if target:
            cursor = target.textCursor()
            if cursor.hasSelection():
                cursor.removeSelectedText()
            else:
                cursor.deleteChar()

    def edit_select_all(self):
        target = self.get_active_text_area()
        if target: target.selectAll()

    # Файловые функции
    def create_file(self):
        file_path, _ = QFileDialog.getSaveFileName(self.window, "Создать новый файл", "",
                                                   "Text Files (*.txt);;All Files (*)")
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("")
                self.current_file_path = file_path
                self.window.codeArea.clear()
                self.window.outputTable.setRowCount(0)
                if hasattr(self.window, 'matchCountLabel'):
                    self.window.matchCountLabel.setText("Найдено: 0")
                self.show_work_areas()
                self.window.setWindowTitle(f"Языковой процессор - {os.path.basename(file_path)}")
            except Exception as e:
                QMessageBox.critical(self.window, "Ошибка", f"Не удалось создать файл:\n{e}")

    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self.window, "Открыть файл", "", "Text Files (*.txt);;All Files (*)")
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.window.codeArea.setPlainText(content)
                self.window.outputTable.setRowCount(0)
                if hasattr(self.window, 'matchCountLabel'):
                    self.window.matchCountLabel.setText("Найдено: 0")
                self.current_file_path = file_path
                self.show_work_areas()
                self.window.setWindowTitle(f"Языковой процессор - {os.path.basename(file_path)}")
            except Exception as e:
                QMessageBox.critical(self.window, "Ошибка", f"Не удалось открыть файл:\n{e}")

    def save_file(self):
        if not self.current_file_path:
            self.save_file_as()
            return
        try:
            content = self.window.codeArea.toPlainText()
            with open(self.current_file_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception as e:
            QMessageBox.critical(self.window, "Ошибка", f"Не удалось сохранить файл:\n{e}")

    def save_file_as(self):
        file_path, _ = QFileDialog.getSaveFileName(self.window, "Сохранить файл как", "",
                                                   "Text Files (*.txt);;All Files (*)")
        if file_path:
            try:
                content = self.window.codeArea.toPlainText()
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.current_file_path = file_path
                self.window.setWindowTitle(f"Языковой процессор - {os.path.basename(file_path)}")
            except Exception as e:
                QMessageBox.critical(self.window, "Ошибка", f"Не удалось сохранить файл:\n{e}")

    def show_note(self):
        dialog = QDialog(self.window)
        dialog.setWindowTitle("Справка: Руководство пользователя")
        dialog.resize(500, 400)

        layout = QVBoxLayout(dialog)
        browser = QTextBrowser(dialog)

        html_content = """
        <h2>Руководство пользователя</h2>
        <p>Добро пожаловать в Языковой процессор! Ниже представлено описание основных функций.</p>
        <h3>Меню "Файл"</h3>
        <ul>
            <li><b>Создать:</b> Создает новый пустой текстовый файл.</li>
            <li><b>Открыть:</b> Открывает существующий файл в редакторе.</li>
            <li><b>Сохранить:</b> Сохраняет текущие изменения в открытом файле.</li>
            <li><b>Сохранить как:</b> Позволяет сохранить текущий текст в новый файл.</li>
            <li><b>Выход:</b> Закрывает программу с предупреждением</li>
        </ul>
        <h3>Меню "Правка"</h3>
        <ul>
            <li><b>Отменить (Ctrl+Z):</b> Отменяет последнее действие в активном поле.</li>
            <li><b>Повторить (Ctrl+Y):</b> Повторяет отмененное действие.</li>
            <li><b>Вырезать (Ctrl+X):</b> Удаляет выделенный текст и помещает его в буфер обмена.</li>
            <li><b>Копировать (Ctrl+C):</b> Помещает выделенный текст в буфер обмена.</li>
            <li><b>Вставить (Ctrl+V):</b> Вставляет текст из буфера обмена.</li>
            <li><b>Удалить (Ctrl+D):</b> Удаляет выделенный текст без сохранения в буфер.</li>
            <li><b>Выделить всё (Ctrl+A):</b> Выделяет весь текст в активном поле.</li>
        </ul>
        """
        browser.setHtml(html_content)
        layout.addWidget(browser)
        dialog.exec()

    def show_about(self):
        about_text = """
        <h3>Поиск подстрок с РВ v1.0</h3>
        <p>Лабораторная работа 4: Реализация алгоритма поиска подстрок с помощью регулярных выражений.</p>
        """
        QMessageBox.about(self.window, "О программе", about_text)

    def run_code(self):
        text = self.window.codeArea.toPlainText()

        if not text.strip():
            QMessageBox.warning(self.window, "Внимание", "Нет данных для поиска. Введите текст.")
            return

        try:
            pattern_index = self.window.regexSelector.currentIndex()
        except AttributeError:
            QMessageBox.critical(self.window, "Ошибка интерфейса",
                                 "Не найден элемент regexSelector.")
            return

        if pattern_index == 2:
            matches = self.automaton_analyzer.analyze(text)
        else:
            matches = self.regex_analyzer.analyze_regex(text, pattern_index)

        table = self.window.outputTable
        table.setRowCount(0)

        self.window.matchCountLabel.setText(f"Найдено: {len(matches)}")

        for row_idx, match in enumerate(matches):
            table.insertRow(row_idx)

            item_str = QTableWidgetItem(match['string'])
            loc_text = f"Стр: {match['line']}, Симв: {match['col']}"
            item_loc = QTableWidgetItem(loc_text)
            item_len = QTableWidgetItem(str(match['length']))

            item_str.setData(Qt.UserRole, match)

            table.setItem(row_idx, 0, item_str)
            table.setItem(row_idx, 1, item_loc)
            table.setItem(row_idx, 2, item_len)

    def table_click(self, item):
        row = item.row()
        match_item = self.window.outputTable.item(row, 0)
        match_data = match_item.data(Qt.UserRole)

        if not match_data:
            return

        editor = self.window.codeArea
        cursor = editor.textCursor()

        cursor.setPosition(match_data['start_abs'])
        cursor.setPosition(match_data['end_abs'], QTextCursor.KeepAnchor)

        editor.setTextCursor(cursor)
        editor.setFocus()

    def eventFilter(self, obj, event):
        if obj == self.window and event.type() == QEvent.Close:
            reply = QMessageBox.question(
                self.window, 'Подтверждение выхода', 'Вы действительно хотите выйти?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.window.removeEventFilter(self)
                event.accept()
                return False
            else:
                event.ignore()
                return True
        return super().eventFilter(obj, event)

    def show(self):
        self.window.show()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_app = LanguageProcessorApp()
    main_app.show()
    sys.exit(app.exec())