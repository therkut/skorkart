import sys
import os

# .py'nın bulunduğu dizinin bir üstünü Python path'e ekle
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from skorkart import scorecard_data

# Tüm hisseler tek Excel dosyasında
results = scorecard_data(
    stock_codes=["A1CAP", "A1YEN"],
    start_period="2025/03",
    end_period="2025/06",
    lang="tr",
    save_to_excel=True,
    merge_to_single_excel=False,  
    merge_tables_per_stock=False,
    convert_to_html=True,
    output_folder="data/bilanco/202506/",
)
print(results)
