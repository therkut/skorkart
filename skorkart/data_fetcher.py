import os
import time
import pandas as pd
from io import StringIO
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import TimeoutException

from .setup_webdriver import setup_webdriver
from .utils import (
    TABS_BILANCO,
    previous_period,
    period_regex,
    get_localized_message,
    format_period,
)


def scorecard_data(
    stock_codes: list[str] | str,
    start_period: str,
    end_period: str,
    lang: str = "tr",
    save_to_excel: bool = False,
    merge_to_single_excel: bool = True,
    merge_tables_per_stock: bool = False,
    convert_to_html: bool = False,
    output_folder: str = None,
    wait_seconds: float = 3,
    financials: bool = True,
    profitability: bool = True,
    multiples: bool = True,
) -> dict[str, dict[str, pd.DataFrame]]:
    wait_seconds = max(3, float(wait_seconds))
    if isinstance(stock_codes, str):
        stock_codes = [stock_codes]

    try:
        start_period = format_period(start_period, lang)
        end_period = format_period(end_period, lang)
    except ValueError as e:
        print(e)
        return {}

    if merge_to_single_excel and merge_tables_per_stock:
        raise ValueError("merge_to_single_excel ve merge_tables_per_stock aynı anda True olamaz.")

    tab_choices = []
    if financials:
        tab_choices.append("Financials")
    if profitability:
        tab_choices.append("Profitability")
    if multiples:
        tab_choices.append("Multiples")
    filtered_tabs = [tab for tab in TABS_BILANCO if tab["name"] in tab_choices]

    tables = {tab['name']: {} for tab in filtered_tabs}

    for stock_code in stock_codes:
        driver, wait = setup_webdriver(lang)
        url = f"https://analizim.halkyatirim.com.tr/Financial/ScoreCardDetail?hisseKod={stock_code}"
        driver.get(url)
        time.sleep(wait_seconds)

        period = end_period
        temp_tables = {tab['name']: pd.DataFrame() for tab in filtered_tabs}
        stock_invalid = False

        try:
            while True:
                try:
                    select_elem = wait.until(lambda d: d.find_element("id", "seciliHisseDonem"))
                except TimeoutException:
                    print(get_localized_message("stock_not_found", lang, stock_code))
                    stock_invalid = True
                    break

                select = Select(select_elem)
                try:
                    select.select_by_visible_text(period)
                except Exception:
                    print(get_localized_message("period_not_found", lang, period, stock_code))
                    period = previous_period(period)
                    if period < start_period:
                        stock_invalid = True
                        break
                    continue

                time.sleep(wait_seconds)
                refresh_btn = wait.until(lambda d: d.find_element("id", "btnRefresh"))
                refresh_btn.click()
                time.sleep(wait_seconds)

                for tab in filtered_tabs:
                    tab_element = wait.until(lambda d: d.find_element("css selector", f'a[href="{tab["tab_href"]}"]'))
                    tab_element.click()
                    time.sleep(wait_seconds)
                    table = wait.until(lambda d: d.find_element("css selector", f'div#{tab["tab_id"]} table'))
                    html = table.get_attribute('outerHTML')
                    df = pd.read_html(StringIO(html), header=0)[0]

                    first_col = df.columns[0]
                    if stock_code in str(first_col) or "Tarih" not in str(first_col):
                        df.columns = ['Tarih'] + list(df.columns[1:])
                    df['Hisse Adı'] = stock_code

                    temp_tables[tab['name']] = pd.concat([temp_tables[tab['name']], df], ignore_index=True)

                all_periods = temp_tables[filtered_tabs[0]['name']].iloc[:, 0].astype(str)
                valid_periods = [d for d in all_periods if period_regex.match(d)]
                if start_period in valid_periods:
                    break
                if valid_periods:
                    last_period = valid_periods[-1]
                else:
                    print(get_localized_message("no_valid_period", lang, stock_code))
                    break
                if last_period == period or last_period < start_period:
                    break
                period = previous_period(last_period)

            if stock_invalid:
                continue

            for name in temp_tables:
                df = temp_tables[name]
                if "Tarih" not in df.columns:
                    continue
                df = df[df['Tarih'].astype(str).str.match(period_regex)]
                df = df[df['Tarih'].astype(str) >= start_period]
                df = df[df['Tarih'].astype(str) <= end_period]
                df = df.drop_duplicates()
                tables[name][stock_code] = df

            print(get_localized_message("stock_done", lang, stock_code))

        except TimeoutException:
            print(get_localized_message("stock_not_found", lang, stock_code))
            continue
        finally:
            driver.quit()

    # === Excel Kaydetme Bölümü ===
    if save_to_excel:
        os.makedirs(output_folder or ".", exist_ok=True)

        if merge_to_single_excel:
            for table_name, stock_dfs in tables.items():
                if not stock_dfs:
                    continue
                filename = f"{table_name.lower()}_{start_period.replace('/', '')}_{end_period.replace('/', '')}.xlsx"
                filepath = os.path.join(output_folder or ".", filename)
                with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
                    for stock_code, df in stock_dfs.items():
                        sheet_name = stock_code[:31]
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
                print(get_localized_message("saved_excel", lang, filepath))

        elif merge_tables_per_stock:
            all_stock_codes = set()
            for stock_dfs in tables.values():
                all_stock_codes.update(stock_dfs.keys())

            for stock_code in all_stock_codes:
                filename = f"{stock_code}_{start_period.replace('/', '')}_{end_period.replace('/', '')}.xlsx"
                filepath = os.path.join(output_folder or ".", filename)
                with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
                    for table_name, stock_dfs in tables.items():
                        if stock_code in stock_dfs:
                            df = stock_dfs[stock_code]
                            sheet_name = table_name[:31]
                            df.to_excel(writer, sheet_name=sheet_name, index=False)
                print(get_localized_message("saved_excel", lang, filepath))

        else:
            for table_name, stock_dfs in tables.items():
                if not stock_dfs:
                    continue
                combined_df = pd.concat(stock_dfs.values(), ignore_index=True)
                filename = f"{table_name.lower()}_{start_period.replace('/', '')}_{end_period.replace('/', '')}.xlsx"
                filepath = os.path.join(output_folder or ".", filename)
                combined_df.to_excel(filepath, index=False)
                print(get_localized_message("saved_excel", lang, filepath))

    # === HTML'e Dönüştürme (Excel'den) ===
    if convert_to_html and save_to_excel:
        for filename in os.listdir(output_folder or "."):
            if filename.endswith(".xlsx"):
                excel_path = os.path.join(output_folder or ".", filename)
                html_path = os.path.join(output_folder or ".", filename.replace(".xlsx", ".html"))
                try:
                    df_dict = pd.read_excel(excel_path, sheet_name=None)

                    # Sayıları Excel'deki gibi formatla
                    def format_numbers(df: pd.DataFrame) -> pd.DataFrame:
                        formatted_df = df.copy()
                        for col in formatted_df.columns:
                            if pd.api.types.is_numeric_dtype(formatted_df[col]):
                                formatted_df[col] = formatted_df[col].map(
                                    lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if pd.notnull(x) else ""
                                )
                        return formatted_df

                    if isinstance(df_dict, dict):
                        with open(html_path, "w", encoding="utf-8") as f:
                            for sheet_name, sheet_df in df_dict.items():
                                sheet_df = format_numbers(sheet_df)
                                f.write(f"<h2>{sheet_name}</h2>\n")
                                f.write(sheet_df.to_html(index=False, border=1, na_rep=""))
                                f.write("<br><hr><br>")
                    else:
                        df_dict = format_numbers(df_dict)
                        df_dict.to_html(html_path, index=False, border=1, na_rep="")

                    print(get_localized_message("saved_html", lang, html_path))
                except Exception as e:
                    print(f"⚠️ {filename} dönüştürülürken hata: {e}")

    print(get_localized_message("all_done", lang))
    return tables
