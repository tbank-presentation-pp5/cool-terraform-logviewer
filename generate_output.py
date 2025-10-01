import os
import pathlib
from fnmatch import fnmatch

def read_gitignore(root_path):
    """Читает .gitignore файл и возвращает список шаблонов для игнорирования"""
    gitignore_path = root_path / '.gitignore'
    ignore_patterns = []
    
    if gitignore_path.exists():
        with open(gitignore_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    ignore_patterns.append(line)
    
    # Базовые исключения
    base_ignores = [
        '.git',
        'generate_output.py',
        'output.txt',
        'frontend/package-lock.json',
        'venv/pyvenv.cfg',
        '__pycache__',
        'venv/Scripts',
        'venv/Lib',
        'venv',
        'node_modules',
        'old'
    ]
    
    ignore_patterns.extend(base_ignores)
    return ignore_patterns

def should_ignore(path, ignore_patterns, root_path):
    """Проверяет, должен ли файл/папка быть проигнорирован"""
    relative_path = path.relative_to(root_path).as_posix()
    
    # Для папок добавляем / в конец для правильного сопоставления
    if path.is_dir():
        test_path = relative_path + '/'
    else:
        test_path = relative_path
    
    for pattern in ignore_patterns:
        # Обрабатываем паттерны с /
        if pattern.endswith('/'):
            pattern = pattern[:-1]
        
        # Проверяем совпадение с паттерном
        if (fnmatch(relative_path, pattern) or 
            fnmatch(test_path, pattern) or
            any(fnmatch(part, pattern) for part in relative_path.split('/'))):
            return True
        
        # Проверяем совпадение для родительских директорий
        parts = relative_path.split('/')
        for i in range(len(parts)):
            parent_path = '/'.join(parts[:i+1])
            if (fnmatch(parent_path, pattern) or 
                fnmatch(parent_path + '/', pattern)):
                return True
    
    return False

def get_all_files(root_path, ignore_patterns):
    """Рекурсивно получает все файлы, исключая игнорируемые"""
    all_files = []
    
    for item in root_path.rglob('*'):
        if should_ignore(item, ignore_patterns, root_path):
            continue
        
        if item.is_file():
            all_files.append(item)
    
    return all_files

def is_text_file(file_path):
    """Проверяет, является ли файл текстовым"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            f.read(1024)  # Читаем первые 1024 байта для проверки
        return True
    except (UnicodeDecodeError, Exception):
        return False

def main():
    root_path = pathlib.Path('.').resolve()
    output_file = root_path / 'output.txt'
    
    print(f"Поиск файлов в: {root_path}")
    
    # Читаем .gitignore и добавляем дополнительные исключения
    ignore_patterns = read_gitignore(root_path)
    print(f"Найдено {len(ignore_patterns)} игнорируемых шаблонов")
    
    # Получаем все файлы
    all_files = get_all_files(root_path, ignore_patterns)
    print(f"Найдено {len(all_files)} файлов для обработки")
    print()
    
    # Создаем output.txt
    with open(output_file, 'w', encoding='utf-8') as out:
        for file_path in all_files:
            print(file_path)
            try:
                # Записываем путь к файлу
                relative_path = file_path.relative_to(root_path).as_posix()
                out.write(f"--- Файл: {relative_path} ---\n")
                
                # Проверяем, является ли файл текстовым
                if is_text_file(file_path):
                    # Читаем и записываем содержимое файла
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        out.write(content)
                else:
                    out.write("[БИНАРНЫЙ ФАЙЛ - СОДЕРЖИМОЕ ПРОПУЩЕНО]")
                
                out.write('\n\n')  # Разделитель между файлами
                
            except Exception as e:
                print(f"Ошибка при обработке {file_path}: {e}")
    print()
    print(f"Результат сохранен в: {output_file}")

if __name__ == "__main__":
    main()