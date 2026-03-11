import sys
import os
import resources_rc
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QMessageBox, QDialog,
    QVBoxLayout, QTextBrowser, QPushButton, QTableWidgetItem, QHeaderView
)
from PySide6.QtGui import QTextCursor, QColor
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice, QObject, QEvent, Qt

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class LexicalAnalyzer:
    def __init__(self):
        self.keywords = {
            "def": 2,
            "return": 3,
            "int": 4
        }
    # Вспомогательные функции для сканера
    def make_token(self, code, type, lexeme, line, start, end, is_error=False): # Быстрый словарь для analyze
        return {
            "code": code,
            "type": type,
            "lexeme": lexeme,
            "line": line,
            "start": start,
            "end": end,
            "is_error": is_error
        }

    def classify_word(self, word, line, start, end): # Для ключевых слов
        if word in self.keywords:
            return self.make_token(self.keywords[word], "ключевое слово", word, line, start, end)
        else:
            return self.make_token(4, "идентификатор", word, line, start, end)

    def analyze(self, text):
        tokens = []
        state = 0 # от 0 до 3
        lexeme = "" # Буфер
        line = 1
        pos = 1  # Текущая позиция в строке
        start_pos = 1  # Позиция начала текущей лексемы

        i = 0
        while i < len(text):
            char = text[i]

            # 0 = начальное состояние
            if state == 0:
                start_pos = pos

                if char.isalpha() or char == '_':
                    state = 1
                    lexeme += char
                elif char in ' \t':
                    state = 2
                    lexeme += char
                elif char == '\n':
                    tokens.append(self.make_token(13, "перенос строки", "\\n", line, start_pos, pos))
                    line += 1
                    pos = 0  # Обнулится до 1 в конце цикла
                elif char == '(':
                    tokens.append(self.make_token(5, "разделитель", "(", line, start_pos, pos))
                elif char == ')':
                    tokens.append(self.make_token(6, "разделитель", ")", line, start_pos, pos))
                elif char == ':':
                    tokens.append(self.make_token(7, "разделитель", ":", line, start_pos, pos))
                elif char == '+':
                    tokens.append(self.make_token(8, "оператор", "+", line, start_pos, pos))
                elif char == ',':
                    tokens.append(self.make_token(9, "разделитель", ",", line, start_pos, pos))
                elif char == '*':
                    tokens.append(self.make_token(12, "оператор", "*", line, start_pos, pos))
                elif char == '-':
                    state = 3  # Переход к проверке стрелки ->
                    lexeme += char
                else:
                    tokens.append(self.make_token("ERROR", "ОШИБКА", char, line, start_pos, pos, is_error=True))

            # 1 = Сбор букв
            elif state == 1:
                if char.isalpha() or char.isdigit() or char == '_':
                    lexeme += char
                else:
                    # Слово закончилось, классифицируем
                    tokens.append(self.classify_word(lexeme, line, start_pos, pos - 1))
                    lexeme = ""
                    state = 0
                    i -= 1
                    pos -= 1

            # 2 = Сбор пробелов
            elif state == 2:
                if char in ' \t':
                    lexeme += char
                else:
                    tokens.append(self.make_token(10, "разделитель", "пробел(ы)", line, start_pos, pos - 1))
                    lexeme = ""
                    state = 0
                    i -= 1
                    pos -= 1

            # 3 = Обработка (для ->)
            elif state == 3:
                if char == '>':
                    lexeme += char
                    tokens.append(self.make_token(11, "оператор", "->", line, start_pos, pos))
                else:
                    # Если после минуса не >, по примеру это должна быть ошибка?
                    tokens.append(self.make_token("ERROR", "ОШИБКА (ожидалось >)", lexeme, line, start_pos, pos - 1,
                                                   is_error=True))
                    i -= 1
                    pos -= 1
                lexeme = ""
                state = 0

            i += 1
            pos += 1

        # Обработка конца файла (если файл закончился, а мы в состоянии сбора)
        if state == 1:
            tokens.append(self.classify_word(lexeme, line, start_pos, pos - 1))
        elif state == 2:
            tokens.append(self.make_token(10, "разделитель", "пробел(ы)", line, start_pos, pos - 1))
        elif state == 3:
            tokens.append(self.make_token("ERROR", "ОШИБКА", lexeme, line, start_pos, pos - 1, is_error=True))

        tokens.append(self.make_token(14, "конец функции (EOF)", "EOF", line, pos, pos))

        return tokens


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
        self.window.outputTable.itemClicked.connect(self.table_click)
        self.scanner = LexicalAnalyzer()

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

    def get_active_text_area(self):
        focused_widget = QApplication.focusWidget()
        if focused_widget in (self.window.codeArea, self.window.outputTable):
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
                self.window.outputTable.setRowCount(0)
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
                self.window.outputTable.setRowCount(0)
                self.current_file_path = file_path
                self.show_work_areas()
                self.window.setWindowTitle(f"Языковой процессор - {os.path.basename(file_path)}")
            except Exception as e:
                QMessageBox.critical(self.window, "Ошибка", f"Не удалось открыть файл:\n{e}")

    def save_file(self):
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
        <h3>Языковой процессор v0.1</h3>
        <p>Данная программа является результатом лабораторных работ по ТФИК.</p>
        <p><b>Разработано с использованием:</b> Python и PySide6.</p>
        """
        QMessageBox.about(self.window, "О программе", about_text)

    def run_code(self): # Не заглушка
        code_text = self.window.codeArea.toPlainText()
        tokens = self.scanner.analyze(code_text)
        table = self.window.outputTable
        table.setRowCount(0)
        for row_idx, token in enumerate(tokens):
            table.insertRow(row_idx)

            # Формирование строки местоположения
            loc_str = f"строка {token['line']}, {token['start']}-{token['end']}"

            # Создание элементов ячеек
            item_code = QTableWidgetItem(str(token['code']))
            item_type = QTableWidgetItem(token['type'])
            item_lexeme = QTableWidgetItem(token['lexeme'])
            item_loc = QTableWidgetItem(loc_str)

            # Сохраняем данные о позиции
            item_loc.setData(Qt.UserRole, token)

            table.setItem(row_idx, 0, item_code)
            table.setItem(row_idx, 1, item_type)
            table.setItem(row_idx, 2, item_lexeme)
            table.setItem(row_idx, 3, item_loc)

    def table_click(self, item):
        row = item.row()
        loc_item = self.window.outputTable.item(row, 3) # У местоположения индекс 3 в таблице
        token_data = loc_item.data(Qt.UserRole)

        if not token_data:
            return

        # Если это ошибка, перемещаем курсор
        if token_data['is_error']:
            editor = self.window.codeArea
            cursor = editor.textCursor()

            cursor.movePosition(QTextCursor.Start)
            cursor.movePosition(QTextCursor.Down, QTextCursor.MoveAnchor, token_data['line'] - 1)
            cursor.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, token_data['start'] - 1)

            length = token_data['end'] - token_data['start'] + 1
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, length)

            editor.setTextCursor(cursor)
            editor.setFocus()


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