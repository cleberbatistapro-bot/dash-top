from pathlib import Path

import pandas as pd


def ler_planilha(caminho: Path) -> pd.DataFrame:
    if caminho.suffix.lower() == ".csv":
        return pd.read_csv(caminho)
    return pd.read_excel(caminho, engine="openpyxl" if caminho.suffix.lower() == ".xlsx" else None)
