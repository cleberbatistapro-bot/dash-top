import base64
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.dashboard_engine import (
    _aplicar_filtros,
    _carregar_dados_mapeados,
    _periodo_atual_e_anterior,
    _serializar_valor,
    calcular_kpis,
)
from app.core.report_analysis import gerar_secoes_analise
from app.routers.logotipo import _logo_existente

COR_ACENTO = colors.HexColor("#0F9E90")
COR_TEXTO = colors.HexColor("#12151C")
COR_TEXTO_SECUNDARIO = colors.HexColor("#6B7080")
COR_LINHA = colors.HexColor("#E3E6ED")
COR_ZEBRA = colors.HexColor("#F3F5F8")
COR_POSITIVA_BG = colors.HexColor("#DCF4E5")
COR_POSITIVA_TX = colors.HexColor("#1E9556")
COR_NEGATIVA_BG = colors.HexColor("#FBE0DE")
COR_NEGATIVA_TX = colors.HexColor("#D63A32")
COR_NEUTRA_BG = colors.HexColor("#F3F5F8")
COR_NEUTRA_TX = colors.HexColor("#6B7080")

MAX_LINHAS_TABELA = 50
LARGURA_PAGINA_UTIL = A4[0] - 40 * mm


def _formatar_numero_br(valor: float, casas: int = 2) -> str:
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


def _formatar_valor_kpi(kpi: dict) -> str:
    if kpi["formato"] == "numero":
        return _formatar_numero_br(kpi["valor"], 0)
    if kpi["formato"] == "percentual":
        return f"{_formatar_numero_br(kpi['valor'], 1)}%"
    return f"R$ {_formatar_numero_br(kpi['valor'], 2)}"


def _formatar_data_br(data) -> str:
    return data.strftime("%d/%m/%Y")


def _decodificar_imagem_base64(data_url: str) -> bytes:
    conteudo = data_url.split(",", 1)[1] if "," in data_url else data_url
    return base64.b64decode(conteudo)


def _estilos() -> dict:
    base = getSampleStyleSheet()
    return {
        "titulo_capa": ParagraphStyle(
            "titulo_capa", parent=base["Title"], fontSize=26, textColor=COR_TEXTO,
            alignment=1, spaceAfter=8,
        ),
        "subtitulo_capa": ParagraphStyle(
            "subtitulo_capa", parent=base["Normal"], fontSize=12, textColor=COR_TEXTO_SECUNDARIO,
            alignment=1, spaceAfter=4,
        ),
        "marca_capa": ParagraphStyle(
            "marca_capa", parent=base["Normal"], fontSize=16, textColor=COR_ACENTO,
            alignment=1, fontName="Helvetica-Bold", spaceAfter=4,
        ),
        "secao": ParagraphStyle(
            "secao", parent=base["Heading2"], fontSize=16, textColor=COR_TEXTO,
            spaceAfter=10,
        ),
        "corpo": ParagraphStyle(
            "corpo", parent=base["Normal"], fontSize=10.5, textColor=COR_TEXTO, leading=16,
        ),
        "grafico_titulo": ParagraphStyle(
            "grafico_titulo", parent=base["Heading3"], fontSize=12, textColor=COR_TEXTO, spaceAfter=6,
        ),
        "nota": ParagraphStyle(
            "nota", parent=base["Normal"], fontSize=8.5, textColor=COR_TEXTO_SECUNDARIO,
        ),
    }


def _rodape(canvas_obj, documento) -> None:
    canvas_obj.saveState()
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.setFillColor(COR_TEXTO_SECUNDARIO)
    canvas_obj.drawString(20 * mm, 12 * mm, "Gerado por Dash Top")
    canvas_obj.drawRightString(A4[0] - 20 * mm, 12 * mm, f"Página {documento.page}")
    canvas_obj.restoreState()


def _pagina_capa(categoria, inicio, fim, estilos) -> list:
    elementos = [Spacer(1, 45 * mm)]

    caminho_logo = _logo_existente()
    if caminho_logo and caminho_logo.suffix.lower() == ".png":
        try:
            leitor = ImageReader(str(caminho_logo))
            largura_original, altura_original = leitor.getSize()
            largura_alvo = 45 * mm
            altura_alvo = largura_alvo * altura_original / largura_original
            elementos.append(Image(str(caminho_logo), width=largura_alvo, height=altura_alvo, hAlign="CENTER"))
            elementos.append(Spacer(1, 14 * mm))
        except Exception:
            elementos.append(Paragraph("Dash Top", estilos["marca_capa"]))
            elementos.append(Spacer(1, 14 * mm))
    else:
        elementos.append(Paragraph("Dash Top", estilos["marca_capa"]))
        elementos.append(Spacer(1, 14 * mm))

    elementos.append(Paragraph(f"Relatório de {categoria.nome_exibicao}", estilos["titulo_capa"]))

    if inicio is not None and fim is not None:
        periodo_texto = f"Período: {_formatar_data_br(inicio)} a {_formatar_data_br(fim)}"
    else:
        periodo_texto = "Período: todos os dados disponíveis"
    elementos.append(Paragraph(periodo_texto, estilos["subtitulo_capa"]))

    data_geracao = datetime.now().strftime("%d/%m/%Y às %H:%M")
    elementos.append(Paragraph(f"Gerado em {data_geracao}", estilos["subtitulo_capa"]))

    return elementos


def _montar_resumo_textual(categoria, kpis: list[dict], inicio, fim) -> str:
    if inicio is not None and fim is not None:
        periodo_texto = f"de {_formatar_data_br(inicio)} a {_formatar_data_br(fim)}"
    else:
        periodo_texto = "considerando todos os dados disponíveis"

    if not kpis:
        return f"Não há indicadores calculáveis para {categoria.nome_exibicao} no período {periodo_texto}."

    partes = []
    for kpi in kpis:
        valor_formatado = _formatar_valor_kpi(kpi)
        if kpi["variacao_percentual"] is None:
            partes.append(f"{kpi['label'].lower()} de {valor_formatado}")
        else:
            direcao = "alta" if kpi["tendencia"] == "alta" else "queda"
            partes.append(
                f"{kpi['label'].lower()} de {valor_formatado} "
                f"({direcao} de {abs(kpi['variacao_percentual']):.1f}% em relação ao período anterior)"
            )

    corpo = "; ".join(partes)
    return f"No período analisado para {categoria.nome_exibicao} ({periodo_texto}), os indicadores registrados foram: {corpo}."


def _pagina_resumo(categoria, kpis: list[dict], inicio, fim, estilos) -> list:
    elementos = [Paragraph("Resumo executivo", estilos["secao"]), Spacer(1, 4 * mm)]

    if kpis:
        linhas = [["Indicador", "Valor", "Variação"]]
        estilos_celulas = []
        for indice, kpi in enumerate(kpis, start=1):
            valor_formatado = _formatar_valor_kpi(kpi)
            if kpi["variacao_percentual"] is None:
                variacao_texto = "—"
                cor_fundo, cor_texto = COR_NEUTRA_BG, COR_NEUTRA_TX
            else:
                seta = "▲" if kpi["tendencia"] == "alta" else "▼"
                variacao_texto = f"{seta} {abs(kpi['variacao_percentual']):.1f}%"
                if kpi["cor"] == "positiva":
                    cor_fundo, cor_texto = COR_POSITIVA_BG, COR_POSITIVA_TX
                elif kpi["cor"] == "negativa":
                    cor_fundo, cor_texto = COR_NEGATIVA_BG, COR_NEGATIVA_TX
                else:
                    cor_fundo, cor_texto = COR_NEUTRA_BG, COR_NEUTRA_TX

            linhas.append([kpi["label"], valor_formatado, variacao_texto])
            estilos_celulas.append(("BACKGROUND", (2, indice), (2, indice), cor_fundo))
            estilos_celulas.append(("TEXTCOLOR", (2, indice), (2, indice), cor_texto))

        tabela = Table(linhas, colWidths=[70 * mm, 50 * mm, 50 * mm])
        tabela.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COR_ACENTO),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, COR_LINHA),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            *estilos_celulas,
        ]))
        elementos.append(tabela)
        elementos.append(Spacer(1, 10 * mm))

    elementos.append(Paragraph(_montar_resumo_textual(categoria, kpis, inicio, fim), estilos["corpo"]))
    return elementos


def _encontrar_grafico_por_tipo(graficos_recebidos: dict, tipo: str):
    for chave, grafico in graficos_recebidos.items():
        if chave.startswith(tipo):
            return grafico
    return None


def _inserir_imagem_grafico(elementos: list, grafico) -> None:
    imagem_bytes = _decodificar_imagem_base64(grafico.imagem)
    leitor = ImageReader(io.BytesIO(imagem_bytes))
    largura_original, altura_original = leitor.getSize()

    largura_alvo = 160 * mm
    altura_alvo = largura_alvo * altura_original / largura_original

    elementos.append(Spacer(1, 2 * mm))
    elementos.append(Image(io.BytesIO(imagem_bytes), width=largura_alvo, height=altura_alvo))


def _pagina_analise(secoes: list[dict], graficos_recebidos: dict, estilos) -> list:
    elementos = [Paragraph("Análise detalhada", estilos["secao"]), Spacer(1, 4 * mm)]

    for indice, secao in enumerate(secoes):
        elementos.append(Paragraph(secao["titulo"], estilos["grafico_titulo"]))
        for paragrafo in secao["paragrafos"]:
            elementos.append(Paragraph(paragrafo, estilos["corpo"]))
            elementos.append(Spacer(1, 3 * mm))

        for tipo_grafico in secao["tipos_grafico"]:
            grafico = _encontrar_grafico_por_tipo(graficos_recebidos, tipo_grafico)
            if grafico:
                _inserir_imagem_grafico(elementos, grafico)

        if indice != len(secoes) - 1:
            elementos.append(PageBreak())
        else:
            elementos.append(Spacer(1, 10 * mm))

    return elementos


def _pagina_tabela(df_filtrado, categoria, estilos) -> list:
    elementos = [Paragraph("Detalhamento", estilos["secao"]), Spacer(1, 4 * mm)]

    colunas = [campo for campo in categoria.campos_esperados if campo.id in df_filtrado.columns]
    total_linhas = len(df_filtrado)
    linhas_tabela = df_filtrado.head(MAX_LINHAS_TABELA)

    dados_tabela = [[campo.nome_exibicao for campo in colunas]]
    for _, linha in linhas_tabela.iterrows():
        valores_linha = []
        for campo in colunas:
            valor = _serializar_valor(linha[campo.id])
            valores_linha.append("-" if valor is None else str(valor))
        dados_tabela.append(valores_linha)

    largura_coluna = LARGURA_PAGINA_UTIL / max(len(colunas), 1)
    tabela = Table(dados_tabela, colWidths=[largura_coluna] * len(colunas), repeatRows=1)
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COR_ACENTO),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.4, COR_LINHA),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COR_ZEBRA]),
    ]))
    elementos.append(tabela)

    if total_linhas > MAX_LINHAS_TABELA:
        elementos.append(Spacer(1, 4 * mm))
        elementos.append(Paragraph(
            f"Exibindo primeiras {MAX_LINHAS_TABELA} de {total_linhas} linhas.",
            estilos["nota"],
        ))

    return elementos


def gerar_pdf_relatorio(sessao_id: str, filtros: dict, graficos_recebidos: dict) -> bytes:
    df, categoria = _carregar_dados_mapeados(sessao_id)
    df_filtrado = _aplicar_filtros(df, filtros, categoria)

    filtros_sem_periodo = {k: v for k, v in filtros.items() if k not in ("periodo_inicio", "periodo_fim")}
    df_dimensoes = _aplicar_filtros(df, filtros_sem_periodo, categoria)

    inicio, fim, inicio_anterior, fim_anterior = _periodo_atual_e_anterior(df_filtrado, filtros)

    df_periodo_anterior = None
    if inicio is not None and "data" in df_dimensoes.columns:
        df_periodo_anterior = df_dimensoes[
            (df_dimensoes["data"] >= inicio_anterior) & (df_dimensoes["data"] <= fim_anterior)
        ]

    kpis = calcular_kpis(df_filtrado, df_periodo_anterior, categoria)
    estilos = _estilos()

    versao_executivo = next((v for v in categoria.versoes_dashboard if v.id == "executivo"), None)
    secoes_analise = (
        gerar_secoes_analise(df_filtrado, categoria, versao_executivo, inicio, fim)
        if versao_executivo else []
    )

    buffer = io.BytesIO()
    documento = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=20 * mm, bottomMargin=20 * mm, leftMargin=20 * mm, rightMargin=20 * mm,
    )

    elementos = _pagina_capa(categoria, inicio, fim, estilos)
    elementos.append(PageBreak())
    elementos += _pagina_resumo(categoria, kpis, inicio, fim, estilos)

    if secoes_analise:
        elementos.append(PageBreak())
        elementos += _pagina_analise(secoes_analise, graficos_recebidos, estilos)

    elementos.append(PageBreak())
    elementos += _pagina_tabela(df_filtrado, categoria, estilos)

    documento.build(elementos, onFirstPage=_rodape, onLaterPages=_rodape)

    return buffer.getvalue()
