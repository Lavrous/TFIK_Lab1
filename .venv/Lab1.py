import sys
import os
from PySide6.QtWidgets import (QApplication, QFileDialog, QMessageBox)
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

        self.window.installEventFilter(self)

    def show_work_areas(self):
        self.window.codeArea.setVisible(True)
        self.window.outputArea.setVisible(True)

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