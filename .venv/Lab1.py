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
        self.keywords = {"def": 2, "return": 3, "int": 4}

    def make_token(self, code, type_name, lexeme, line, start, end, is_error=False):
        return {
            "code": code,
            "type": type_name,
            "lexeme": lexeme,
            "line": line,
            "start": start,
            "end": end,
            "is_error": is_error
        }

    def classify_word(self, word, line, start, end):
        if word in self.keywords:
            return self.make_token(self.keywords[word], "ключевое слово", word, line, start, end)
        else:
            return self.make_token(1, "идентификатор", word, line, start, end)

    def analyze(self, text):
        tokens = []
        state = 0
        lexeme = ""
        line = 1
        pos = 1
        start_pos = 1

        i = 0
        while i < len(text):
            char = text[i]

            if state == 0:
                start_pos = pos
                if char in ' \t\r':
                    pass
                elif char == '\n':
                    line += 1
                    pos = 0
                elif char.isalpha() or char == '_':
                    state = 1
                    lexeme += char
                elif char in '():+,*':
                    tokens.append(self.make_token(5, "разделитель/оператор", char, line, pos, pos))
                elif char == '-':
                    state = 3
                    lexeme += char
                elif char == ';':
                    tokens.append(self.make_token(13, "конец функции", ";", line, pos, pos))
                else:
                    tokens.append(self.make_token("ERROR", "Лексическая ошибка", char, line, pos, pos, True))

            elif state == 1:
                if char.isalpha() or char.isdigit() or char == '_':
                    lexeme += char
                else:
                    tokens.append(self.classify_word(lexeme, line, start_pos, pos - 1))
                    lexeme = ""
                    state = 0
                    i -= 1
                    pos -= 1

            elif state == 3:
                if char == '>':
                    lexeme += char
                    tokens.append(self.make_token(6, "оператор", lexeme, line, start_pos, pos))
                    lexeme = ""
                    state = 0
                else:
                    tokens.append(
                        self.make_token("ERROR", "Лексическая ошибка (ожидалось >)", lexeme, line, start_pos, pos - 1,
                                        True))
                    lexeme = ""
                    state = 0
                    i -= 1
                    pos -= 1

            i += 1
            pos += 1

        if state == 1:
            tokens.append(self.classify_word(lexeme, line, start_pos, pos - 1))
        elif state == 3:
            tokens.append(self.make_token("ERROR", "Лексическая ошибка", lexeme, line, start_pos, pos - 1, True))

        return tokens


class SyntaxParser:
    def __init__(self, tokens):
        self.all_tokens = tokens
        self.tokens = [t for t in tokens if not t['is_error']]
        self.pos = 0
        self.errors = []
        self.found_semicolon = False
        self.last_error_pos = -1

    def peek(self):
        if self.pos < len(self.tokens): return self.tokens[self.pos]
        return None

    def advance(self):
        if self.pos < len(self.tokens): self.pos += 1
        return self.peek()

    def add_error(self, message, token=None):
        if self.errors:
            last_err = self.errors[-1]
            if last_err['lexeme'] == message and self.last_error_pos == self.pos:
                return

        self.last_error_pos = self.pos

        if token:
            loc = f"строка {token['line']}, поз. {token['start']}-{token['end']}"
        else:
            loc = "Конец файла"

        self.errors.append({
            "code": "ERROR",
            "type": "Синтаксическая ошибка",
            "lexeme": message,
            "location_str": loc,
            "raw_token": token,
            "is_error": True
        })

    def match(self, expected_lexeme=None, expected_type=None):
        token = self.peek()
        if not token:
            self.add_error(f"Неожиданный конец кода. Ожидалось: '{expected_lexeme or expected_type}'")
            return False

        if (expected_lexeme and token['lexeme'] == expected_lexeme) or \
                (expected_type and token['type'] == expected_type):
            self.advance()
            return True

        self.add_error(f"Ожидалось '{expected_lexeme or expected_type}', встречено '{token['lexeme']}'", token)
        return False

    def match_no_error(self, expected_lexeme=None, expected_type=None):
        token = self.peek()
        if not token: return False
        if (expected_lexeme and token['lexeme'] == expected_lexeme) or \
                (expected_type and token['type'] == expected_type):
            self.advance()
            return True
        return False

    def parse(self):
        if not self.tokens:
            self.add_error("Пустой код или отсутствуют допустимые лексемы")
            return self.errors
        self.parse_Start()

        extra = []
        while self.peek():
            extra.append(self.tokens[self.pos])
            self.advance()

        if extra and self.found_semicolon:
            first, last = extra[0], extra[-1]
            self.errors.append({
                "code": "ERROR",
                "type": "Синтаксическая ошибка",
                "lexeme": "Лишний код после завершения функции",
                "location_str": f"строка {first['line']}, поз. {first['start']}-{last['end']}",
                "raw_token": first,
                "is_error": True
            })

        return self.errors

    # 1. Start -> def id (Params) -> Type : Body
    def parse_Start(self):
        token = self.peek()
        if token and token['lexeme'] != 'def':
            if token['lexeme'] == ';':
                self.add_error("Символ конца функции ';' до её начала", token)
            else:
                self.add_error("Ожидалось ключевое слово 'def'", token)
            while self.peek():
                if self.peek()['lexeme'] == 'def':
                    self.advance()
                    break

                if self.peek()['type'] == 'идентификатор':
                    if self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1]['lexeme'] == '(':
                        break
                    if self.pos + 2 < len(self.tokens) and self.tokens[self.pos + 1]['type'] == 'идентификатор' and \
                            self.tokens[self.pos + 2]['lexeme'] == '(':
                        tok1 = self.peek()
                        tok2 = self.tokens[self.pos + 1]
                        if tok1 in self.all_tokens and tok2 in self.all_tokens:
                            idx1 = self.all_tokens.index(tok1)
                            idx2 = self.all_tokens.index(tok2)
                            if any(t['is_error'] for t in self.all_tokens[idx1+1:idx2]):
                                break
                self.advance()
        elif token and token['lexeme'] == 'def':
            self.advance()
        else:
            self.add_error("Пустой код. Ожидалось 'def'")
            return

        if not self.match_no_error(expected_type='идентификатор'):
            self.add_error("Ожидалось имя функции (идентификатор)", self.peek())
            while self.peek() and self.peek()['lexeme'] != '(':
                self.advance()
        else:
            if self.peek():
                if self.peek()['type'] == 'идентификатор':
                    self.add_error("Ошибка в имени функции (возможно, недопустимые символы)", self.peek())
                    while self.peek() and self.peek()['lexeme'] != '(':
                        self.advance()
                elif self.peek()['lexeme'] == '(' and self.pos + 1 < len(self.tokens):
                    next_tok = self.tokens[self.pos + 1]
                    if next_tok['type'] == 'идентификатор' and self.pos + 2 < len(self.tokens) and \
                            self.tokens[self.pos + 2]['lexeme'] == '(':
                        self.add_error("Ошибка в имени функции (недопустимый символ '(')", self.peek())
                        self.advance()
                        self.advance()

        self.match(expected_lexeme='(')
        self.parse_Params()
        self.match(expected_lexeme=')')
        if not self.match_no_error(expected_lexeme='->'):
            err_tok = self.peek()
            if err_tok in self.all_tokens:
                idx = self.all_tokens.index(err_tok)
                for i in range(idx - 1, -1, -1):
                    if not self.all_tokens[i]['is_error']:
                        break
                    if self.all_tokens[i]['lexeme'] == '-':
                        err_tok = self.all_tokens[i]
                        break

            self.add_error("Ожидалось '->'", err_tok)
            while self.peek() and self.peek()['lexeme'] not in ['int', ':']:
                self.advance()

        if not self.match_no_error(expected_lexeme='int'):
            self.add_error("Ожидался тип 'int'", self.peek())
            while self.peek() and self.peek()['lexeme'] not in [':', 'return']:
                self.advance()

        self.match(expected_lexeme=':')
        self.parse_Body()

    # 2. Params -> Param Params’ | ε
    def parse_Params(self):
        if self.peek() and self.peek()['lexeme'] != ')':
            self.parse_Param()
            while self.peek() and self.peek()['lexeme'] == ',':
                self.advance()
                self.parse_Param()

    # 4. Param -> id: Type
    def parse_Param(self):
        has_error = False
        if not self.match_no_error(expected_type='идентификатор'):
            self.add_error("Ожидалось имя параметра (идентификатор)", self.peek())
            has_error = True
        elif not self.match_no_error(expected_lexeme=':'):
            self.add_error("Ожидалось ':' после имени параметра", self.peek())
            has_error = True
        elif not self.match_no_error(expected_lexeme='int'):
            self.add_error("Ожидался тип 'int'", self.peek())
            has_error = True
        if has_error:
            self.sync_param()

    def sync_param(self):
        while self.peek():
            lex = self.peek()['lexeme']
            if lex in [',', ')']:
                break
            self.advance()

    # 5. Body -> return Expr ;
    def parse_Body(self):
        if not self.match_no_error(expected_lexeme='return'):
            self.add_error("Ожидалось ключевое слово 'return'", self.peek())
            while self.peek():
                if self.peek()['lexeme'] == '(':
                    break
                if self.pos < len(self.tokens) - 1:
                    next_lex = self.tokens[self.pos + 1]['lexeme']
                    if self.peek()['type'] == 'идентификатор' and next_lex in ['+', '*', ')', ';']:
                        break
                self.advance()

        self.parse_Expr()

        has_garbage = False
        while self.peek() and self.peek()['lexeme'] not in [';', ')']:
            if not has_garbage:
                self.add_error(f"Пропущен оператор или неожиданный токен '{self.peek()['lexeme']}'", self.peek())
                has_garbage = True
            self.advance()

        while self.peek() and self.peek()['lexeme'] == ')':
            self.add_error("Лишняя закрывающая скобка ')'", self.peek())
            self.advance()

        if self.match_no_error(expected_lexeme=';'):
            self.found_semicolon = True
        else:
            self.add_error("Ожидалась ';' в конце функции", self.peek())

    # 6. Expr -> Term Expr’
    def parse_Expr(self):
        self.parse_Term()
        self.parse_Expr_prime()

    # 7. Expr’ -> + Term Expr’ | ε
    def parse_Expr_prime(self):
        while self.peek() and self.peek()['lexeme'] == '+':
            self.advance()
            self.parse_Term()

    # 8. Term -> Factor Term’
    def parse_Term(self):
        self.parse_Factor()
        self.parse_Term_prime()

    # 9. Term’ -> * Factor Term’ | ε
    def parse_Term_prime(self):
        while self.peek() and self.peek()['lexeme'] == '*':
            self.advance()
            self.parse_Factor()

    # 10. Factor -> id | (Expr)
    def parse_Factor(self):
        token = self.peek()
        if not token:
            self.add_error("Ожидалось выражение, но код закончился")
            return

        if token['type'] == 'идентификатор':
            self.advance()
        elif token['lexeme'] == '(':
            self.advance()
            self.parse_Expr()
            self.match(expected_lexeme=')')
        else:
            self.add_error(f"Ожидался идентификатор или '(', встречено '{token['lexeme']}'", token)
            self.advance()


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

        first_lex = next((t for t in all_tokens if t['is_error']), None)
        lexical_errors = [first_lex] if first_lex else []

        parser = SyntaxParser(all_tokens)
        syntax_errors = parser.parse()

        all_errors = []
        for err in lexical_errors:
            all_errors.append({
                "code": err['code'],
                "type": err['type'],
                "lexeme": err['lexeme'],
                "location_str": f"строка {err['line']}, поз. {err['start']}-{err['end']}",
                "raw_token": err,
                "is_error": True
            })

        all_errors.extend(syntax_errors)

        if not all_errors:
            QMessageBox.information(self.window, "Результат", "Код написан верно! Ошибок не найдено.")
            return

        error_color = QColor(255, 200, 200)

        for idx, err in enumerate(all_errors):
            table.insertRow(idx)

            item_code = QTableWidgetItem(str(err['code']))
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

    def table_click(self, item):
        row = item.row()
        loc_item = self.window.outputTable.item(row, 3)
        token_data = loc_item.data(Qt.UserRole)

        if not token_data:
            return

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