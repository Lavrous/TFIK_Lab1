import sys
import os
import resources_rc
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QMessageBox, QDialog,
    QVBoxLayout, QTextBrowser, QTableWidgetItem, QLabel
)
from PySide6.QtGui import QTextCursor, QColor, QFont
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice, QObject, QEvent, Qt


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class LexicalAnalyzer:
    def make_token(self, type_name, lexeme, line, start, end, is_error=False):
        return {
            "type": type_name,
            "lexeme": lexeme,
            "line": line,
            "start": start,
            "end": end,
            "is_error": is_error
        }

    def analyze(self, text):
        tokens = []
        line = 1
        pos = 1
        i = 0
        n = len(text)

        while i < n:
            char = text[i]

            if char in ' \t\r':
                i += 1
                pos += 1
                continue
            elif char == '\n':
                line += 1
                pos = 1
                i += 1
                continue

            start_pos = pos

            # Идентификаторы (id -> letter {letter | digit | _})
            if char.isalpha():
                lexeme = char
                i += 1
                pos += 1
                while i < n and (text[i].isalnum() or text[i] == '_'):
                    lexeme += text[i]
                    i += 1
                    pos += 1
                tokens.append(self.make_token("id", lexeme, line, start_pos, pos - 1))
                continue

            # Числа (num -> digit {digit})
            if char.isdigit():
                lexeme = char
                i += 1
                pos += 1
                while i < n and text[i].isdigit():
                    lexeme += text[i]
                    i += 1
                    pos += 1
                tokens.append(self.make_token("num", lexeme, line, start_pos, pos - 1))
                continue

            # Операторы из 2 символов (**, //)
            if i + 1 < n:
                two_char = text[i:i + 2]
                if two_char in ['**', '//']:
                    tokens.append(self.make_token("op", two_char, line, start_pos, pos))
                    i += 2
                    pos += 2
                    continue

            # Операторы из 1 символа и скобки
            if char in ['+', '-', '*', '/', '%']:
                tokens.append(self.make_token("op", char, line, start_pos, start_pos))
                i += 1
                pos += 1
                continue
            elif char in ['(', ')']:
                tokens.append(self.make_token("paren", char, line, start_pos, start_pos))
                i += 1
                pos += 1
                continue

            tokens.append(self.make_token("ERROR", char, line, start_pos, start_pos, True))
            i += 1
            pos += 1

        return tokens


class SyntaxParser:
    def __init__(self, tokens):
        self.tokens = [t for t in tokens if not t['is_error']]
        self.pos = 0
        self.errors = []

        self.quads = []
        self.rpn = []
        self.temp_count = 1
        self.is_int_only = True

    def peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def advance(self):
        if self.pos < len(self.tokens):
            self.pos += 1
        return self.peek()

    def add_error(self, message, token=None):
        loc = f"строка {token['line']}, поз. {token['start']}-{token['end']}" if token else "Конец файла"
        self.errors.append({
            "type": "Синтаксическая ошибка",
            "lexeme": message,
            "location_str": loc,
            "raw_token": token,
            "is_error": True
        })

    def match_lexeme(self, expected):
        token = self.peek()
        if token and token['lexeme'] == expected:
            self.advance()
            return True
        return False

    def new_temp(self):
        t = f"t{self.temp_count}"
        self.temp_count += 1
        return t

    def parse(self):
        if not self.tokens:
            self.add_error("Пустое выражение")
            return

        self.parse_E()

    # E -> TA
    def parse_E(self):
        left_val = self.parse_T()
        if left_val is not None:
            return self.parse_A(left_val)
        return None

    # A -> + TA | - TA | ε
    def parse_A(self, left_val):
        token = self.peek()
        if token and token['lexeme'] in ['+', '-']:
            op = token['lexeme']
            self.advance()
            right_val = self.parse_T()
            if right_val is not None:
                res = self.new_temp()
                self.quads.append((op, left_val, right_val, res))
                self.rpn.append(op)
                return self.parse_A(res)
        return left_val

    # T -> FB
    def parse_T(self):
        left_val = self.parse_F()
        if left_val is not None:
            return self.parse_B(left_val)
        return None

    # B -> * FB | / FB | // FB | % FB | ** FB | ε
    def parse_B(self, left_val):
        token = self.peek()
        if token and token['lexeme'] in ['*', '/', '//', '%', '**']:
            op = token['lexeme']
            self.advance()
            right_val = self.parse_F()
            if right_val is not None:
                res = self.new_temp()
                self.quads.append((op, left_val, right_val, res))
                self.rpn.append(op)
                return self.parse_B(res)
        return left_val

    # F -> num | id | (E)
    def parse_F(self):
        token = self.peek()
        if not token:
            self.add_error("Ожидался операнд, но выражение закончилось")
            return None

        if token['type'] == 'num':
            val = token['lexeme']
            self.rpn.append(val)
            self.advance()
            return val

        elif token['type'] == 'id':
            self.is_int_only = False
            val = token['lexeme']
            self.rpn.append(val)
            self.advance()
            return val

        elif token['lexeme'] == '(':
            self.advance()
            val = self.parse_E()
            if not self.match_lexeme(')'):
                self.add_error("Пропущена закрывающая скобка ')'", self.peek())
            return val

        else:
            self.add_error(f"Неверный символ/операнд: '{token['lexeme']}'", token)
            self.advance()
            return None

    def evaluate_rpn(self):
        if not self.is_int_only or self.errors:
            return None

        stack = []
        try:
            for item in self.rpn:
                if item.isdigit():
                    stack.append(int(item))
                else:
                    b = stack.pop()
                    a = stack.pop()
                    if item == '+':
                        stack.append(a + b)
                    elif item == '-':
                        stack.append(a - b)
                    elif item == '*':
                        stack.append(a * b)
                    elif item == '/':
                        stack.append(a / b)
                    elif item == '//':
                        stack.append(a // b)
                    elif item == '%':
                        stack.append(a % b)
                    elif item == '**':
                        stack.append(a ** b)
            return stack[0] if stack else None
        except Exception as e:
            return f"Ошибка вычисления: {str(e)}"


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

        self.window.installEventFilter(self)

    def show_work_areas(self):
        self.window.codeArea.setVisible(True)
        self.window.outputTable.setVisible(True)

    def get_active_text_area(self):
        focused_widget = QApplication.focusWidget()
        if focused_widget == self.window.codeArea:
            return focused_widget
        return None

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
        """
        browser.setHtml(html_content)
        layout.addWidget(browser)
        dialog.exec()

    def show_about(self):
        about_text = """
        <h3>Языковой процессор v0.2</h3>
        <p>Данная программа является результатом лабораторных работ по ТФИК.</p>
        <p><b>Разработано с использованием:</b> Python и PySide6.</p>
        """
        QMessageBox.about(self.window, "О программе", about_text)

    def run_code(self):
        code_text = self.window.codeArea.toPlainText()
        table = self.window.outputTable
        table.setRowCount(0)

        all_tokens = self.scanner.analyze(code_text)
        lexical_errors = [t for t in all_tokens if t['is_error']]

        parser = SyntaxParser(all_tokens)
        parser.parse()

        all_errors = []
        for err in lexical_errors:
            all_errors.append({
                "type": "Лексическая ошибка",
                "lexeme": err['lexeme'],
                "location_str": f"строка {err['line']}, поз. {err['start']}-{err['end']}",
                "raw_token": err
            })
        all_errors.extend(parser.errors)

        if all_errors:
            QMessageBox.warning(self.window, "Ошибки", "Найдены ошибки. Генерация тетрад отменена.")
            error_color = QColor(255, 200, 200)
            for idx, err in enumerate(all_errors):
                table.insertRow(idx)
                item_code = QTableWidgetItem("ERROR")
                item_type = QTableWidgetItem(err['type'])
                item_lexeme = QTableWidgetItem(err['lexeme'])
                item_loc = QTableWidgetItem(err['location_str'])
                item_loc.setData(Qt.UserRole, err['raw_token'])

                for item in (item_code, item_type, item_lexeme, item_loc):
                    item.setBackground(error_color)

                table.setItem(idx, 0, item_code)
                table.setItem(idx, 1, item_type)
                table.setItem(idx, 2, item_lexeme)
                table.setItem(idx, 3, item_loc)
            return

        self.show_success_dialog(parser)

    def show_success_dialog(self, parser):
        dialog = QDialog(self.window)
        dialog.setWindowTitle("Внутренняя форма и ПОЛИЗ")
        dialog.resize(400, 500)
        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel("<b>Тетрады (op, arg1, arg2, result):</b>"))
        quads_browser = QTextBrowser()
        quads_browser.setFont(QFont("Consolas", 11))
        if parser.quads:
            quads_text = "\n".join([f"({q[0]}, {q[1]}, {q[2]}, {q[3]})" for q in parser.quads])
        else:
            quads_text = "Нет операций (простое значение)."
        quads_browser.setText(quads_text)
        layout.addWidget(quads_browser)

        layout.addWidget(QLabel("<b>ПОЛИЗ:</b>"))
        rpn_browser = QTextBrowser()
        rpn_browser.setFont(QFont("Consolas", 11))
        rpn_browser.setMaximumHeight(60)
        rpn_text = " ".join(parser.rpn)
        rpn_browser.setText(rpn_text)
        layout.addWidget(rpn_browser)

        layout.addWidget(QLabel("<b>Результат вычисления:</b>"))
        res_browser = QTextBrowser()
        res_browser.setFont(QFont("Consolas", 11))
        res_browser.setMaximumHeight(60)

        if parser.is_int_only:
            result = parser.evaluate_rpn()
            res_browser.setText(str(result))
        else:
            res_browser.setText("Невозможно вычислить: присутствуют идентификаторы (переменные).")
        layout.addWidget(res_browser)

        dialog.exec()

    def table_click(self, item):
        row = item.row()
        loc_item = self.window.outputTable.item(row, 3)
        token_data = loc_item.data(Qt.UserRole)

        if not token_data: return

        editor = self.window.codeArea
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.Start)
        cursor.movePosition(QTextCursor.Down, QTextCursor.MoveAnchor, token_data['line'] - 1)
        cursor.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, token_data['start'] - 1)

        length = token_data['end'] - token_data['start'] + 1
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, length)

        editor.setTextCursor(cursor)
        editor.setFocus()

    def eventFilter(self, obj, event):
        if obj == self.window and event.type() == QEvent.Close:
            reply = QMessageBox.question(self.window, 'Выход', 'Выйти?', QMessageBox.Yes | QMessageBox.No,
                                         QMessageBox.No)
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