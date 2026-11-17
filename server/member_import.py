import io
import re
from zipfile import BadZipFile, ZipFile
from xml.etree.ElementTree import ParseError

from fastapi import HTTPException
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

MAX_UPLOAD = 5 * 1024 * 1024
MAX_MEMBERS = 2000


def read_members(content):
    try:
        return _read_members(content)
    except (BadZipFile, ValueError, KeyError, OSError, IndexError, TypeError, ParseError, InvalidFileException):
        raise HTTPException(422, '請使用有效的 .xlsx 檔案') from None


def _read_members(content):
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, 'Excel 上限 5 MB')
    try:
        with ZipFile(io.BytesIO(content)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 30 * 1024 * 1024:
                raise ValueError('解壓縮後過大')
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=False)
    except (BadZipFile, ValueError, KeyError, OSError):
        raise HTTPException(422, '請使用有效的 .xlsx 檔案') from None
    try:
        sheet = workbook.worksheets[0]
        rows = sheet.iter_rows(max_col=2)
        headers = [str(cell.value or '').strip() for cell in next(rows, [])]
        if headers[:2] not in (['會員編號', '會員名稱'], ['member_code', 'display_name']):
            raise HTTPException(422, '首列前兩欄須為「會員編號、會員名稱」')
        result, seen, errors = [], set(), []
        for line, cells in enumerate(rows, 2):
            if line > MAX_MEMBERS + 1:
                raise HTTPException(422, '每次最多匯入 2000 列')
            if all(cell.value is None for cell in cells):
                continue
            values = []
            for cell in cells[:2]:
                value = cell.value
                if cell.data_type == 'f' or isinstance(value, bool):
                    values.append('')
                elif isinstance(value, (int, float)) and float(value).is_integer():
                    value = str(int(value))
                    if re.fullmatch(r'0+', cell.number_format):
                        value = value.zfill(len(cell.number_format))
                    values.append(value)
                else:
                    values.append(str(value).strip() if value is not None else '')
            code, name = (values + ['', ''])[:2]
            if not code or not name or len(code) > 80 or len(name) > 100:
                errors.append(f'第 {line} 列：編號或名稱空白、格式不符或過長')
            elif code in seen:
                errors.append(f'第 {line} 列：會員編號 {code} 重複')
            else:
                result.append({'member_code': code, 'display_name': name, 'line': line})
                seen.add(code)
        if errors:
            raise HTTPException(422, '；'.join(errors[:20]))
        if not result:
            raise HTTPException(422, '沒有可匯入的會員')
        return result
    finally:
        workbook.close()
