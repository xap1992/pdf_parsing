class Word:
    def __init__(self, rect, text):
        """
        单行文字
        :param rect:文字位置矩形，x0,y0,x1,y1
        :param text:文字内容
        """
        assert isinstance(rect, list) and len(rect) == 4, 'rect必须为list对象,且长度为4'
        assert isinstance(text, str), 'text必须为str对象'
        self.rect = rect
        self.text = text

    def __str__(self):
        return f"{{'rect':{self.rect}, 'text': {self.text}}}"


class Cell:
    def __init__(self, rect, words):
        """
        表格单个cell
        :param rect:cell位置矩形
        :param words:cell中的文字，一个cell可能包含多个cell
        """
        assert isinstance(rect, list) and len(rect) == 4, 'rect必须为list对象,且长度为4'
        assert isinstance(words, list), 'words必须为list对象'
        self.rect = rect
        self.words = words
        self.col = -1
        self.row = -1
        self.colspan = -1
        self.rowspan = -1
        self.inside = None

    def __str__(self):
        return f"""{{\n\t'row':{self.row},'col':{self.col},'rowspan':{self.rowspan},'colspan':{self.colspan},\n\t'rect': {self.rect},\n\t'words': {[str(w) for w in self.words]}\n}}"""


class Table:
    def __init__(self, rect):
        """
        表格本体
        :param rect:table位置矩形
        """
        assert isinstance(rect, list) and len(rect) == 4, 'rect必须为list对象,且长度为4'
        self.rect = rect
        self.cells = []

    def append_cell(self, cell):
        self.cells.append(cell)

    def __str__(self):
        cell_rect_str = ''
        for cell in self.cells:
            cell_rect_str += str(cell) + ',\n\t'
        return f"{{'rect':{self.rect},'cells':[\n{cell_rect_str[:-3]}\n]}}"


if __name__ == '__main__':
    w = Word([1, 2, 3, 4], '124154')
    c = Cell([23, 4, 5, 6], [w])
    t = Table([2, 3, 4, 5])
    t.append_cell(c)
    c.row += 1
    print(t)
