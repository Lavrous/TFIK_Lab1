import sys
import os
import platform
import subprocess
import json
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


class SymbolTable:
    def __init__(self):
        self.symbols = {}

    def declare(self, name, var_type):
        if name in self.symbols:
            return False
        self.symbols[name] = var_type
        return True

    def lookup(self, name):
        return self.symbols.get(name, None)


class AstNode:
    def __init__(self, label):
        self.label = label
        self.children = []

    def add_child(self, child):
        if child is not None:
            self.children.append(child)

    def to_tree_string(self, indent="", is_last=True, is_root=True):
        result = ""

        if is_root:
            marker = ""
            child_indent = ""
        else:
            marker = "└── " if is_last else "├── "
            child_indent = indent + ("    " if is_last else "│   ")

        lines = self.label.split('\n')

        result += f"{indent}{marker}{lines[0]}\n"

        for line in lines[1:]:
            attr_marker = "├── " if len(self.children) > 0 else "└── "
            if is_root:
                result += f"{attr_marker}{line}\n"
            else:
                result += f"{child_indent}{attr_marker}{line}\n"

        for i, child in enumerate(self.children):
            child_is_last = (i == len(self.children) - 1)
            result += child.to_tree_string(child_indent, child_is_last, is_root=False)

        return result

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
                    tokens.append(self.make_token("ERROR", "Лексическая ошибка (ожидалось >)", lexeme, line, start_pos, pos - 1, True))
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
        self.tokens = [t for t in tokens if not t['is_error']]
        self.pos = 0
        self.errors = []
        self.semantic_errors = []
        self.found_semicolon = False
        self.last_error_pos = -1
        self.symtab = SymbolTable()

    def peek(self):
        if self.pos < len(self.tokens): return self.tokens[self.pos]
        return None

    def advance(self):
        if self.pos < len(self.tokens): self.pos += 1
        return self.peek()

    def add_error(self, message, token=None):
        if self.pos == self.last_error_pos:
            return
        self.last_error_pos = self.pos
        loc = f"строка {token['line']}, поз. {token['start']}-{token['end']}" if token else "Конец файла"
        self.errors.append({
            "code": "ERROR",
            "type": "Синтаксическая ошибка",
            "lexeme": message,
            "location_str": loc,
            "raw_token": token,
            "is_error": True
        })

    def add_semantic_error(self, message, token):
        loc = f"строка {token['line']}, поз. {token['start']}-{token['end']}"
        self.semantic_errors.append({
            "code": "ERROR",
            "type": "Семантическая ошибка",
            "lexeme": message,
            "location_str": loc,
            "raw_token": token,
            "is_error": True
        })

    def match(self, expected_lexeme=None, expected_type=None):
        token = self.peek()
        if not token:
            self.add_error(f"Неожиданный конец кода. Ожидалось: '{expected_lexeme or expected_type}'")
            return None

        if (expected_lexeme and token['lexeme'] == expected_lexeme) or \
                (expected_type and token['type'] == expected_type):
            self.advance()
            return token

        self.add_error(f"Ожидалось '{expected_lexeme or expected_type}', встречено '{token['lexeme']}'", token)
        return None

    def match_no_error(self, expected_lexeme=None, expected_type=None):
        token = self.peek()
        if not token: return None
        if (expected_lexeme and token['lexeme'] == expected_lexeme) or \
                (expected_type and token['type'] == expected_type):
            self.advance()
            return token
        return None

    def parse(self):
        if not self.tokens:
            self.add_error("Пустой код или отсутствуют допустимые лексемы")
            return None, self.errors + self.semantic_errors

        ast_root = None

        junk = []
        while self.peek() and self.peek()['lexeme'] != 'def':
            junk.append(self.tokens[self.pos])
            self.advance()

        if junk:
            first, last = junk[0], junk[-1]
            self.errors.append({
                "code": "ERROR", "type": "Синтаксическая ошибка",
                "lexeme": "Недопустимый код вне функции def (отсутствует def)",
                "location_str": f"строка {first['line']}, поз. {first['start']}-{last['end']}",
                "raw_token": first, "is_error": True
            })

        if self.peek():
            ast_root = self.parse_Start()

        extra = []
        while self.peek():
            extra.append(self.tokens[self.pos])
            self.advance()

        if extra and self.found_semicolon:
            first, last = extra[0], extra[-1]
            self.errors.append({
                "code": "ERROR", "type": "Синтаксическая ошибка",
                "lexeme": "Лишний код после завершения функции",
                "location_str": f"строка {first['line']}, поз. {first['start']}-{last['end']}",
                "raw_token": first, "is_error": True
            })

        return ast_root, self.errors + self.semantic_errors

    # 1. Start -> def id (Params) -> Type : Body
    def parse_Start(self):
        self.match(expected_lexeme='def')

        name_token = self.peek()
        func_name = name_token['lexeme'] if name_token and name_token['type'] == 'идентификатор' else "<unknown>"
        self.match(expected_type='идентификатор')

        root = AstNode(f"FunctionDeclNode\ndef: {func_name}")

        if self.peek() and self.peek()['lexeme'] != '(':
            self.add_error(f"Ожидался '(', встречено '{self.peek()['lexeme']}'", self.peek())
            while self.peek() and self.peek()['lexeme'] != '(':
                self.advance()

        self.match(expected_lexeme='(')

        arg_node = AstNode("ArgNode")
        params = self.parse_Params()
        for p in params:
            arg_node.add_child(p)
        root.add_child(arg_node)

        self.match(expected_lexeme=')')
        self.match(expected_lexeme='->')

        ret_type_token = self.match_no_error(expected_lexeme='int')
        if not ret_type_token:
            self.add_error("Ожидался тип 'int'", self.peek())
            while self.peek() and self.peek()['lexeme'] != ':':
                self.advance()

        ret_type_name = ret_type_token['lexeme'] if ret_type_token else "unknown"
        ret_node = AstNode(f"ReturnTypeNode\nname: {ret_type_name}")

        self.match(expected_lexeme=':')

        body_node = AstNode("statement sequence")
        body = self.parse_Body()
        body_node.add_child(body)
        root.add_child(body_node)
        root.add_child(ret_node)

        return root

    # 2. Params -> Param Params’ | ε
    def parse_Params(self):
        parsed_params = []
        if self.peek() and self.peek()['lexeme'] != ')':
            p = self.parse_Param()
            if p: parsed_params.append(p)
            while self.peek() and self.peek()['lexeme'] == ',':
                self.advance()
                p = self.parse_Param()
                if p: parsed_params.append(p)
        return parsed_params

    # 4. Param -> id: Type
    def parse_Param(self):
        has_error = False
        id_token = self.peek()

        if not self.match_no_error(expected_type='идентификатор'):
            self.add_error("Ожидалось имя параметра", self.peek())
            has_error = True
        elif not self.match_no_error(expected_lexeme=':'):
            self.add_error("Ожидалось ':'", self.peek())
            has_error = True
        elif not self.match_no_error(expected_lexeme='int'):
            self.add_error("Ожидался тип 'int'", self.peek())
            has_error = True

        if has_error:
            self.sync_param()
            return None
        param_name = id_token['lexeme']
        if not self.symtab.declare(param_name, 'int'):
            self.add_semantic_error(f"Повторное объявление идентификатора '{param_name}'", id_token)

        return AstNode(f"IntNode\nname: {param_name}")

    def sync_param(self):
        bracket_count = 0
        while self.peek():
            lex = self.peek()['lexeme']
            if lex == '(':
                bracket_count += 1
            elif lex == ')':
                if bracket_count > 0:
                    bracket_count -= 1
                else:
                    break
            elif lex == ',' and bracket_count == 0:
                break
            self.advance()

    # 5. Body -> return Expr ;
    def parse_Body(self):
        self.match(expected_lexeme='return')

        ret_node = AstNode("ReturnNode")
        expr_node = self.parse_Expr()
        ret_node.add_child(expr_node)

        while self.peek() and self.peek()['lexeme'] == ')':
            self.add_error("Лишняя закрывающая скобка ')'", self.peek())
            self.advance()

        if self.match_no_error(expected_lexeme=';'):
            self.found_semicolon = True
        else:
            self.add_error("Ожидалась ';' в конце функции", self.peek())

        return ret_node

    # 6. Expr -> Term Expr’
    def parse_Expr(self):
        left = self.parse_Term()
        return self.parse_Expr_prime(left)

    # 7. Expr’ -> + Term Expr’ | ε
    def parse_Expr_prime(self, left):
        while self.peek() and self.peek()['lexeme'] == '+':
            op_token = self.peek()
            self.advance()
            right = self.parse_Term()

            new_node = AstNode(f"BinOpNode\nop: {op_token['lexeme']}")
            new_node.add_child(left)
            new_node.add_child(right)
            left = new_node

        return left

    # 8. Term -> Factor Term’
    def parse_Term(self):
        left = self.parse_Factor()
        return self.parse_Term_prime(left)

    # 9. Term’ -> * Factor Term’ | ε
    def parse_Term_prime(self, left):
        while self.peek() and self.peek()['lexeme'] == '*':
            op_token = self.peek()
            self.advance()
            right = self.parse_Factor()

            new_node = AstNode(f"BinOpNode\nop: {op_token['lexeme']}")
            new_node.add_child(left)
            new_node.add_child(right)
            left = new_node

        return left

    # 10. Factor -> id | (Expr)
    def parse_Factor(self):
        token = self.peek()
        if not token:
            self.add_error("Ожидалось выражение, но код закончился")
            return None

        if token['type'] == 'идентификатор':
            var_name = token['lexeme']

            if not self.symtab.lookup(var_name):
                self.add_semantic_error(f"Использование необъявленной переменной '{var_name}'", token)

            self.advance()
            return AstNode(f"IntNode\nname: {var_name}")

        elif token['lexeme'] == '(':
            self.advance()
            expr_node = self.parse_Expr()
            self.match(expected_lexeme=')')
            return expr_node

        else:
            self.add_error(f"Ожидался идентификатор или '(', встречено '{token['lexeme']}'", token)
            self.advance()
            return None

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
        ast_root, sync_and_sem_errors = parser.parse()

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

        all_errors.extend(sync_and_sem_errors)

        if not all_errors:
            if ast_root:
                tree_str = ast_root.to_tree_string()
                ast_file_path = os.path.join(os.getcwd(), "AST.txt")

                with open(ast_file_path, "w", encoding="utf-8") as f:
                    f.write(tree_str)

                    os.startfile(ast_file_path)

            QMessageBox.information(self.window, "Результат",
                                    "Код написан верно! Ошибок не найдено.\nДерево AST открыто в текстовом редакторе.")
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