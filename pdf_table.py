import fitz
import numpy as np
import cv2
import itertools
import copy
from entity import *

# 将float列表转为int列表
as_int = lambda x: list(map(int, x))
# 判断点p是否在矩形框内r
inside_rectangle = lambda p, r: True if r[0] <= p[0] <= r[2] and r[1] <= p[1] <= r[3] else False

# 判断两个矩形是否位置相似
equal_rect = lambda r1, r2, border: True if abs(r1[0] - r2[0]) < border and abs(r1[1] - r2[1]) < border \
                                            and abs(r1[2] - r2[2]) < border and abs(r1[3] - r2[3]) < border else False


def page_to_words_list(page: fitz.fitz.Page) -> list:
    '''
    将每一页中的textWords信息使用list封装，这样方便后续使用
    :param page:
    :return:
    '''
    # 获取文字及坐标信息
    words = page.get_text_words()
    # 将元素转为list
    # 因为list[0],list[1]....对于不熟悉的人很容易忘记含义，所以用对象封装
    word_list = []
    for w in words:
        # 有些文字旋转过，需要旋转回来
        p1 = fitz.Point(w[0], w[1]) * page.rotation_matrix
        p2 = fitz.Point(w[2], w[3]) * page.rotation_matrix
        # 旋转后矩形点位置发生改变，需要还原
        p3 = min(p1[0], p2[0]), min(p1[1], p2[1])
        p4 = max(p1[0], p2[0]), max(p1[1], p2[1])
        word_list.append(Word([p3[0], p3[1], p4[0], p4[1]], w[4]))
    # 按y坐标排序
    word_list = sorted(word_list, key=lambda word: (word.rect[1], word.rect[0]))
    return word_list


def draw_pdf_tables(page: fitz.fitz.Page):
    """
    使用cv2绘制表格
    :param page: 单页pdf对象
    :return: 绘制出了线条的pdf图片
    """
    assert isinstance(page, fitz.fitz.Page), '必须传入fitz.Page对象'
    # 创建一个白色的画布
    pixmap = page.get_pixmap(matrix=fitz.Matrix(1, 1))
    # 二进制数据，宽，高
    img = np.zeros([pixmap.h, pixmap.w], dtype=np.uint8) + 255
    draws = page.get_drawings()
    # 在白色的画布上，画上黑色的线条
    for draw in draws:
        color = draw['color']
        fill = draw['fill']
        if (color == [1.0, 1.0, 1.0] and fill is None) or (fill == [1.0, 1.0, 1.0] and color is None) or (
                fill == [1.0, 1.0, 1.0] and color == [1.0, 1.0, 1.0]):
            continue
        items_ = draw['items']
        for item_ in items_:
            item_ = list(item_)
            # 线条
            if 'l' == item_[0]:
                p1, p2 = as_int(item_[1]), as_int(item_[2])
                img = cv2.line(img, (p1[0], p1[1]), (p2[0], p2[1]), (0))
            elif 're' == item_[0]:
                p = as_int(item_[1])
                img = cv2.rectangle(img, (p[0], p[1]), (p[2], p[3]), (0))
            # elif 'c' == item_[0]:
            #     print('c', item_)
            # else:
            #     print(item_)
    # 使用漫水填充算法，将周围变为黑色
    # 这样也可以去掉单独的线条
    cv2.floodFill(img, None, (1, 1), (0), cv2.FLOODFILL_FIXED_RANGE)
    # 开运算，去掉细小的空隙
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    img = cv2.morphologyEx(img, cv2.MORPH_OPEN, kernel, iterations=2)
    return img


def get_page_all_cell(img, words):
    """
    获取一页pdf中每个Cell的信息，需要注意的一页pdf可能有多个表格，每个表格有多个框
    :param img:每页的线条已经转为cv2的Mat对象
    :param words:这一页中提取的所有word对象
    :return: Cell列表
    """
    # 查找相应的轮廓，得到每个表格cell的矩形框
    contours, hierarchy = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cells = []
    # 整合表格和文字的信息
    for c in contours:
        r = cv2.boundingRect(c)
        r = [r[0], r[1], r[0] + r[2], r[1] + r[3]]
        ws = []
        for word in words[:]:
            w = word.rect
            # 文字中心点
            center = [(w[0] + w[2]) / 2, (w[1] + w[3]) / 2]
            # 判断文字是否在表格cell中
            if inside_rectangle(center, r):
                ws.append(word)
                words.remove(word)
            # 如果文字中心点y轴已经超过cell的y坐标了，那就退出循环
            if center[1] > r[3]:
                break
        cells.append(Cell(r, ws))
    return cells


def get_page_all_table(img):
    """
    获取一页pdf中每个表格的信息，一页pdf可能有多个表格
    :param img: 每页的线条已经转为cv2的Mat对象
    :return:
    """
    # 闭运算，是为了去掉表格中间的线条，这样就只剩下轮廓了
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    morp = cv2.morphologyEx(img, cv2.MORPH_CLOSE, kernel, iterations=3)
    # 查找相应的轮廓，得到每个表格的矩形框
    contours, hierarchy = cv2.findContours(morp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    tables = []
    for c in contours:
        r = cv2.boundingRect(c)
        r = [r[0], r[1], r[0] + r[2], r[1] + r[3]]
        tables.append(Table(r))
    return tables


def get_small_cell(table, img):
    '''
    针对出现合并单元格的表格
    将复杂格式的cell生成最小单元的cell
    :param table:单页中的单个表格
    :param img:单页图片
    :return:最小单元cell
    '''
    # 获取表格坐标位置
    t_r = table.rect
    table_img = copy.deepcopy(img)
    # 截取表格所有区域的图片
    table_img = table_img[t_r[1]:t_r[3], t_r[0]:t_r[2]]
    # 表格所有的cell
    cells = table.cells
    # 将每个格子的线条都延长到边缘
    for cell in cells:
        r = cell.rect
        table_img[:, r[0] - t_r[0]] = 0
        table_img[:, r[2] - t_r[2]] = 0
        table_img[r[1] - t_r[1]] = 0
        table_img[r[3] - t_r[3]] = 0
    # 开运算，避免出现细小漏洞
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    table_img = cv2.morphologyEx(table_img, cv2.MORPH_OPEN, kernel, iterations=3)
    cells = []
    # 查找相应的轮廓，得到每个表格cell的矩形框
    contours, hierarchy = cv2.findContours(table_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in contours:
        r = cv2.boundingRect(c)
        r = [r[0] + t_r[0], r[1] + t_r[1], r[0] + r[2] + t_r[0], r[1] + r[3] + t_r[1]]
        cells.append(r)
    cells = sorted(cells, key=lambda data: (data[1], data[0]))
    return cells


def get_table_words(page: fitz.fitz.Page, words=None):
    '''
    :param page:一页pdf
    :param words:从pdf中提取的无序文字
    :return:
    '''
    assert isinstance(page, fitz.fitz.Page), '必须传入fitz.Page对象'
    # 获取这一页中所有的文字信息
    if words is None:
        words = page_to_words_list(page)
    # 绘制线条图片
    img = draw_pdf_tables(page)
    # 获取所有的cell，包含位置和文字信息
    all_cells = get_page_all_cell(img, words)
    # 获取所有的表格位置
    tables = get_page_all_table(img)
    # 根据cell的坐标和table的坐标排序
    table_cell = sorted(all_cells, key=lambda data: (data.rect[1], data.rect[0]))
    table_rects = sorted(tables, key=lambda data: (data.rect[1], data.rect[0]))
    # 将cell合并到表中
    tables_words = []
    for table in table_rects:
        for cell in table_cell:
            c = cell.rect
            center = [(c[0] + c[2]) / 2, (c[1] + c[3]) / 2]
            if inside_rectangle(center, table.rect):
                table.append_cell(cell)
            # 如果文字中心点y轴已经超过cell的y坐标了，那就退出循环
            if center[1] > table.rect[3]:
                break
        tables_words.append(table)
    return tables_words, img


def table_parse(table, img, border=5):
    '''
    解析表格，形成最终的表格数据
    :param table:
    :param img:
    :return:
    '''
    table_cell = table.cells
    # 延长表格中的线条，获取到最小的单元格，并按行分组
    cells = get_small_cell(table, img)
    # 按y轴分组
    cells_group = itertools.groupby(cells, key=lambda x: (x[1]))
    # i为行坐标
    for i, (k, line_cells) in enumerate(cells_group):
        line_cells = list(line_cells)
        # j为列坐标
        for j, c in enumerate(line_cells):
            for cell in table_cell:
                center = [(c[0] + c[2]) / 2, (c[1] + c[3]) / 2]
                '''
                如果最小单元格的格子中心，落在表格中，那么他一定是属于这个表格的
                因为上文中已经对所有的格子做了x,y轴排序，此处只需对比当前格子和上一个格子的位置关系,就能确定跨行跨列的相关信息
                inside是指cell中内部的上一次遇到的表格
                '''
                if inside_rectangle(center, cell.rect):
                    r = cell.rect
                    # 起点或者两个框相等
                    if equal_rect(r, c, border) or (abs(r[0] - c[0]) < border and abs(r[1] - c[1]) < border):
                        cell.col, cell.row = j, i
                        cell.colspan, cell.rowspan = 1, 1
                        cell.inside = c
                    elif cell.inside is not None:
                        # 纵坐标差不多，表示同一行
                        if abs(cell.inside[1] - c[1]) < border:
                            cell.colspan += 1
                            cell.inside = c
                        # 下面格子顶坐标和上面格子底坐标
                        elif abs(cell.inside[3] - c[1]) < border:
                            cell.rowspan += 1
                            cell.inside = c
                        else:
                            print('error:', r, c, cell.inside, i, j)
                        break
                    else:
                        print('error:', r, c, cell.inside, i, j)


def extract_pdf_table(doc):
    tables = []
    for page in doc:
        # 获取一页中所有的表格文字
        table_words, img = get_table_words(page)
        page_table = []
        # 解析每一个表格
        for table in table_words:
            # 将表格的数据
            table_parse(table, img)
            page_table.append(table)
        tables.append(page_table)
    return tables


def page_to_img(page: fitz.fitz.Page, zoom: int = 1) -> np.ndarray:
    assert isinstance(page, fitz.fitz.Page), '必须传入fitz.Page对象'
    # 返回bmp格式的图片
    pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    print(type(pixmap))
    # 二进制数据，宽，高
    data, width, height = pixmap.samples, pixmap.w, pixmap.h
    # 将字节数组转为np格式数据
    np_data = np.frombuffer(data, np.uint8)
    # bmp格式数据转图片
    if len(np_data) % (width * height) == 0:
        img = np.reshape(np_data, (height, width, len(np_data) // (width * height)))
    else:
        # jpg或png格式转图片
        img = cv2.imdecode(np_data, cv2.IMREAD_ANYCOLOR)
    if img is not None:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return img


def test(pdf_path):
    # 加载pdf文件
    doc = fitz.open(pdf_path)
    # 提取所有的表格
    tables = extract_pdf_table(doc)
    print(tables)
    # 一个pdf有多页
    for i, tables in enumerate(tables):
        img = page_to_img(doc[i])
        # 一页有多个表格
        for table in tables:
            table_cell = table.cells
            # 一个表格有多个cell
            for cell in table_cell:
                p = cell.rect
                print(cell)
                cv2.rectangle(img, (p[0], p[1]), (p[2], p[3]), (0, 255, 0))
                cv2.imshow('123', img)
                cv2.waitKey(0)


if __name__ == '__main__':
    path = r'202003建行.pdf'
    test(path)
