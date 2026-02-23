import sys
import os
import resources_rc
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QMessageBox, QDialog,
    QVBoxLayout, QTextBrowser, QPushButton
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice, QObject, QEvent


class LanguageProcessorApp(QObject):
    def __init__(self):
        super().__init__()

        ui_file_name = "design.ui"
        ui_file = QFile(ui_file_name)
        ui_file.open(QIODevice.ReadOnly)
        loader = QUiLoader()
        self.window = loader.load(ui_file)
        ui_file.close()
        self.current_file_path = None
        self.window.codeArea.setVisible(False)
        self.window.outputArea.setVisible(False)

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
        self.window.outputArea.setVisible(True)

    def get_active_text_area(self):
        focused_widget = QApplication.focusWidget()
        if focused_widget in (self.window.codeArea, self.window.outputArea):
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
        file_path, _ = QFileDialog.getSaveFileName(
            self.window, "Создать новый файл", "", "Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("")
                self.current_file_path = file_path
                self.window.codeArea.clear()
                self.window.outputArea.clear()
                self.show_work_areas()
                self.window.setWindowTitle(f"Языковой процессор - {os.path.basename(file_path)}")
            except Exception as e:
                QMessageBox.critical(self.window, "Ошибка", f"Не удалось создать файл:\n{e}")

    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self.window, "Открыть файл", "", "Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.window.codeArea.setPlainText(content)
                self.current_file_path = file_path
                self.show_work_areas()
                self.window.setWindowTitle(f"Языковой процессор - {os.path.basename(file_path)}")
            except Exception as e:
                QMessageBox.critical(self.window, "Ошибка", f"Не удалось открыть файл:\n{e}")

    def save_file(self):
        if self.current_file_path:
            try:
                content = self.window.codeArea.toPlainText()
                with open(self.current_file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            except Exception as e:
                QMessageBox.critical(self.window, "Ошибка", f"Не удалось сохранить файл:\n{e}")
        else:
            self.save_file_as()

    def save_file_as(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self.window, "Сохранить файл как", "", "Text Files (*.txt);;All Files (*)"
        )
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
            <li><b>Выход:</b> Закрывает программу с предупреждением о потере данных.</li>
        </ul>
        <h3>Меню "Правка"</h3>
        <ul>
            <li><b>Отменить (Ctrl+Z):</b> Отменяет последнее действие в активном поле.</li>
            <li><b>Повторить (Ctrl+Y):</b> Повторяет отмененное действие.</li>
            <li><b>Вырезать (Ctrl+X):</b> Удаляет выделенный текст и помещает его в буфер обмена.</li>
            <li><b>Копировать (Ctrl+C):</b> Помещает выделенный текст в буфер обмена.</li>
            <li><b>Вставить (Ctrl+V):</b> Вставляет текст из буфера обмена.</li>
            <li><b>Удалить (Del):</b> Удаляет выделенный текст без сохранения в буфер.</li>
            <li><b>Выделить всё (Ctrl+A):</b> Выделяет весь текст в активном поле.</li>
        </ul>
        """
        browser.setHtml(html_content)
        layout.addWidget(browser)
        dialog.exec()

    def show_about(self):
        about_text = """
        <h3>Языковой процессор v0.1</h3>
        <p>Данная программа является результатом лабораторных работ по ТФИК.</p>
        <p><b>Разработано с использованием:</b> Python и PySide6.</p>
        """
        QMessageBox.about(self.window, "О программе", about_text)

    def run_code(self):
        code_text = self.window.codeArea.toPlainText()
        self.window.outputArea.setPlainText(code_text)

    # Для закрытия
    def eventFilter(self, obj, event):
        if obj == self.window and event.type() == QEvent.Close:
            reply = QMessageBox.question(
                self.window,
                'Подтверждение выхода',
                'Вы действительно хотите выйти?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                self.window.removeEventFilter(self) # Чтобы не ловил закрытие дважды
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