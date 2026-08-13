import pandas as pd
import os

def parse_addresses(file_path):
    if not os.path.exists(file_path):
        return []
    
    try:
        # Пытаемся прочитать как Excel
        df = pd.read_excel(file_path)
    except:
        # Если не получилось, читаем как CSV (текстовый файл)
        try:
            df = pd.read_csv(file_path)
        except:
            return []
    
    # Ищем колонку 'Адрес'
    if 'Адрес' in df.columns:
        addresses = df['Адрес'].dropna().tolist()
    else:
        addresses = df.iloc[:, 0].dropna().tolist()
    
    addresses = [str(addr).strip() for addr in addresses if str(addr).strip()]
    return addresses
