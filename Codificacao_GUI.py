import sys
import os
from datetime import datetime
from typing import Optional, List, Dict
import pandas as pd
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                           QHBoxLayout, QGridLayout, QLabel, QPushButton, QFileDialog,
                           QTableWidget, QTableWidgetItem, QMessageBox,
                           QProgressBar, QHeaderView, QRadioButton, QButtonGroup, QFrame,
                           QLineEdit, QComboBox, QCheckBox, QAbstractItemView)
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QFont, QPixmap, QColor, QDoubleValidator
from Codificacao_Core import (ManagerPluviometrica, ManagerFluviometrica, resource_path,
                               traduzir_erro, ENTIDADES_RESPONSAVEIS, UNIDADES_HIDRO)

# Campos de tipo de estação exibidos no formulário de cadastro manual, conforme a codificação escolhida
FLUVIO_TIPO_FIELDS = [
    ('TipoEstacaoEscala', 'Escala'),
    ('TipoEstacaoRegistradorNivel', 'Registrador de Nível'),
    ('TipoEstacaoDescLiquida', 'Descarga Líquida'),
    ('TipoEstacaoSedimentos', 'Sedimentos'),
    ('TipoEstacaoQualAgua', 'Qualidade da Água'),
]
PLUVIO_TIPO_FIELDS = [
    ('TipoEstacaoPluviometro', 'Pluviômetro'),
    ('TipoEstacaoRegistradorChuva', 'Registrador de Chuva'),
    ('TipoEstacaoTanqueEvapo', 'Tanque Evaporimétrico'),
    ('TipoEstacaoClimatologica', 'Climatológica'),
]
# Telemétrica se aplica tanto a estações fluviométricas quanto pluviométricas, então fica
# sempre visível no formulário em vez de alternar junto com FLUVIO_TIPO_FIELDS/PLUVIO_TIPO_FIELDS.
TIPO_FIELD_TELEMETRICA = ('TipoEstacaoTelemetrica', 'Telemétrica')

# Mapeia cada campo de tipo para o prefixo das colunas de período do template ANA
# (PeriodoXInicio/PeriodoXFim), usado quando a pessoa informa o período de operação no cadastro.
PERIODO_PREFIXOS = {
    'TipoEstacaoEscala': 'PeriodoEscala',
    'TipoEstacaoRegistradorNivel': 'PeriodoRegistradorNivel',
    'TipoEstacaoDescLiquida': 'PeriodoDescLiquida',
    'TipoEstacaoSedimentos': 'PeriodoSedimentos',
    'TipoEstacaoQualAgua': 'PeriodoQualAgua',
    'TipoEstacaoPluviometro': 'PeriodoPluviometro',
    'TipoEstacaoRegistradorChuva': 'PeriodoRegistradorChuva',
    'TipoEstacaoTanqueEvapo': 'PeriodoTanqueEvapo',
    'TipoEstacaoClimatologica': 'PeriodoClimatologica',
    'TipoEstacaoTelemetrica': 'PeriodoTelemetrica',
}

# Faixa aproximada do território brasileiro, usada só como aviso (não bloqueia o cadastro)
LAT_MIN_BR, LAT_MAX_BR = -34.0, 6.0
LON_MIN_BR, LON_MAX_BR = -74.0, -32.0

# Nomes de coluna aceitos na importação de Excel, além do nome oficial do template ANA.
# Cobre planilhas que a pessoa monta do jeito dela, sem ter o schema do SQL Server em mãos.
COLUNA_ALIASES = {
    'nome': ['nome', 'nome da estacao', 'nome da estação', 'estacao', 'estação'],
    'latitude': ['latitude', 'lat'],
    'longitude': ['longitude', 'lon', 'long', 'longitude '],
    'areadrenagem': ['areadrenagem', 'area de drenagem', 'área de drenagem', 'area drenagem', 'area (km2)', 'área (km²)'],
    'responsavelcodigo': ['responsavelcodigo', 'responsável', 'responsavel', 'codigo responsavel', 'código responsável'],
    'operadoracodigo': ['operadoracodigo', 'operadora', 'codigo operadora', 'código operadora'],
    'codigoadicional': ['codigoadicional', 'codigo adicional', 'código adicional'],
}

COR_FALLBACK = QColor(255, 205, 178)
COR_EXTRAPOLADO = QColor(255, 243, 176)
COR_INTERPOLADO = QColor(205, 240, 205)
COR_DUPLICADO = QColor(255, 170, 170)


class Worker(QObject):
    finished = Signal(list)
    error = Signal(str)
    progress = Signal(int)

    def __init__(self, manager_class, dados_entrada):
        super().__init__()
        self.manager_class = manager_class
        self.dados_entrada = dados_entrada
        self.manager = None
        self._cancelado = False

    def cancelar(self):
        self._cancelado = True

    def _deve_continuar(self) -> bool:
        return not self._cancelado

    def run(self):
        try:
            self.progress.emit(2)
            self.manager = self.manager_class()
            self.progress.emit(10)

            if self.dados_entrada['tipo'] == 'manual':
                df_input = self.manager.montar_df_de_linhas_manuais(self.dados_entrada['linhas'])
            else:
                df_input = self.manager.carregar_df_de_mdb(self.dados_entrada['caminho'])

            res = self.manager.processar(df_input, progress_callback=self.progress.emit,
                                          should_continue=self._deve_continuar)
            self.progress.emit(100)
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(traduzir_erro(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sistema de Codificação da Agência Nacional de Águas e Saneamento Básico (ANA)")
        self.setMinimumSize(1050, 780)
        self.dados_processados = []
        self.pendentes = []
        self.manager = None
        self.worker = None
        self.checks_tipo = {}
        self.inputs_periodo = {}
        self.setup_ui()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # --- Cabeçalho ---
        header = QFrame()
        header.setObjectName("Card")
        header.setFixedHeight(120)
        header.setStyleSheet("background-color: #FFFFFF;")
        header_layout = QHBoxLayout(header)

        self.logo_ana = QLabel()
        path_ana = resource_path(os.path.join("assets", "ana_logo.png"))
        pixmap_ana = QPixmap(path_ana)
        if not pixmap_ana.isNull():
            self.logo_ana.setPixmap(pixmap_ana.scaledToHeight(80, Qt.SmoothTransformation))
        header_layout.addWidget(self.logo_ana)

        title = QLabel("Sistema de Codificação de Estações\n(Rede Hidrometeorológica Nacional)")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #000000;")
        title.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(title, 2)

        self.logo_rhn = QLabel()
        path_rhn = resource_path(os.path.join("assets", "rhn_logo.png"))
        pixmap_rhn = QPixmap(path_rhn)
        if not pixmap_rhn.isNull():
            self.logo_rhn.setPixmap(pixmap_rhn.scaledToHeight(120, Qt.SmoothTransformation))
        header_layout.addWidget(self.logo_rhn)

        layout.addWidget(header)

        # --- Card Principal ---
        main_card = QFrame()
        main_layout = QVBoxLayout(main_card)
        main_layout.setSpacing(15)

        # 1. Seletor de Tipo de Estação
        type_widget = QWidget()
        type_layout = QHBoxLayout(type_widget)
        type_label = QLabel("Tipo de Codificação:")
        type_label.setStyleSheet("font-weight: bold; font-size: 16px;")

        self.radio_pluvio = QRadioButton("Pluviométrica (Geográfica)")
        self.radio_pluvio.setChecked(True)
        self.radio_fluvio = QRadioButton("Fluviométrica (Topológica)")

        self.type_group = QButtonGroup()
        self.type_group.addButton(self.radio_pluvio)
        self.type_group.addButton(self.radio_fluvio)
        self.radio_fluvio.toggled.connect(self.atualizar_campos_tipo)

        type_layout.addWidget(type_label)
        type_layout.addWidget(self.radio_pluvio)
        type_layout.addWidget(self.radio_fluvio)
        type_layout.addStretch()
        main_layout.addWidget(type_widget)

        # 2. Seletor de origem dos dados
        modo_widget = QWidget()
        modo_layout = QHBoxLayout(modo_widget)
        modo_label = QLabel("Origem dos Dados:")
        modo_label.setStyleSheet("font-weight: bold; font-size: 16px;")

        self.radio_manual = QRadioButton("Cadastrar estações manualmente")
        self.radio_manual.setChecked(True)
        self.radio_mdb = QRadioButton("Importar arquivo")

        self.modo_group = QButtonGroup()
        self.modo_group.addButton(self.radio_manual)
        self.modo_group.addButton(self.radio_mdb)
        self.radio_manual.toggled.connect(self.atualizar_modo_entrada)

        modo_layout.addWidget(modo_label)
        modo_layout.addWidget(self.radio_manual)
        modo_layout.addWidget(self.radio_mdb)
        modo_layout.addStretch()
        main_layout.addWidget(modo_widget)

        # 2a. Painel de cadastro manual
        self.painel_manual = self._construir_painel_manual()
        main_layout.addWidget(self.painel_manual)

        # 2b. Painel de importação de .mdb (modo legado)
        self.painel_mdb = self._construir_painel_mdb()
        main_layout.addWidget(self.painel_mdb)
        self.painel_mdb.setVisible(False)

        # 3. Tabela de Resultados
        self.tabela = QTableWidget()
        self.setup_tabela()
        main_layout.addWidget(self.tabela)

        # 4. Progresso e Botões de Ação
        self.progress = QProgressBar()
        main_layout.addWidget(self.progress)

        botoes_acao = QHBoxLayout()
        self.btn_processar = QPushButton("PROCESSAR CODIFICAÇÃO")
        self.btn_processar.setFixedHeight(40)
        self.btn_processar.setStyleSheet("font-weight: bold; background-color: #0078d4; color: white;")
        self.btn_processar.clicked.connect(self.processar)
        botoes_acao.addWidget(self.btn_processar)

        self.btn_cancelar = QPushButton("CANCELAR")
        self.btn_cancelar.setFixedHeight(40)
        self.btn_cancelar.setStyleSheet("font-weight: bold; background-color: #d13438; color: white;")
        self.btn_cancelar.clicked.connect(self.cancelar_processamento)
        self.btn_cancelar.setVisible(False)
        botoes_acao.addWidget(self.btn_cancelar)
        main_layout.addLayout(botoes_acao)

        # 5. Botão Exportar
        self.btn_exportar = QPushButton("EXPORTAR RESULTADOS")
        self.btn_exportar.setFixedHeight(40)
        self.btn_exportar.setEnabled(False)
        self.btn_exportar.clicked.connect(self.exportar)
        main_layout.addWidget(self.btn_exportar)

        layout.addWidget(main_card)

    # ------------------------------------------------------------------
    # Painel de cadastro manual (Parte 2 do plano de melhorias)
    # ------------------------------------------------------------------
    def _criar_grid_tipos(self, campos) -> QWidget:
        """Uma linha por parâmetro: checkbox + Início/Fim próprios (cada parâmetro pode ter
        período de operação diferente dos demais)."""
        widget = QWidget()
        grid_tipo = QGridLayout(widget)
        grid_tipo.setContentsMargins(0, 0, 0, 0)
        for i, (campo, rotulo) in enumerate(campos):
            check = QCheckBox(rotulo)
            check.setMinimumWidth(160)
            self.checks_tipo[campo] = check

            input_inicio = QLineEdit()
            input_inicio.setPlaceholderText("Início (dd/mm/aaaa ou mm/aaaa)")
            input_fim = QLineEdit()
            input_fim.setPlaceholderText("Fim (em branco = ainda opera)")
            self.inputs_periodo[campo] = (input_inicio, input_fim)

            grid_tipo.addWidget(check, i, 0)
            grid_tipo.addWidget(input_inicio, i, 1)
            grid_tipo.addWidget(input_fim, i, 2)
        return widget

    def _construir_painel_manual(self) -> QWidget:
        painel = QWidget()
        v = QVBoxLayout(painel)
        v.setContentsMargins(0, 0, 0, 0)

        form_frame = QFrame()
        form_frame.setStyleSheet("""
            QFrame { background-color: #F5F5F5; border-radius: 4px; }
            QLabel, QCheckBox { color: #1A1A1A; background-color: transparent; }
            QLineEdit, QComboBox {
                color: #1A1A1A; background-color: #FFFFFF;
                border: 1px solid #B0B0B0; border-radius: 3px; padding: 3px;
            }
            QComboBox QAbstractItemView { color: #1A1A1A; background-color: #FFFFFF; }
            QPushButton {
                color: #FFFFFF; background-color: #0078d4;
                border-radius: 3px; padding: 5px 10px;
            }
            QPushButton:hover { background-color: #106ebe; }
        """)
        grid = QGridLayout(form_frame)

        self.input_nome = QLineEdit()
        self.input_nome.setPlaceholderText("Nome da estação (obrigatório)")

        self.input_lat = QLineEdit()
        self.input_lat.setPlaceholderText("Ex: -15.793889")
        self.input_lat.setValidator(QDoubleValidator(-90.0, 90.0, 6))

        self.input_lon = QLineEdit()
        self.input_lon.setPlaceholderText("Ex: -47.882778")
        self.input_lon.setValidator(QDoubleValidator(-180.0, 180.0, 6))

        self.input_area = QLineEdit()
        self.input_area.setPlaceholderText("Área de drenagem km² (opcional)")

        self.input_cod_adicional = QLineEdit()
        self.input_cod_adicional.setPlaceholderText("Código adicional (opcional)")

        self.combo_responsavel = QComboBox()
        self.combo_operadora = QComboBox()
        for combo in (self.combo_responsavel, self.combo_operadora):
            combo.addItem("(não informado)", None)
            for codigo in sorted(ENTIDADES_RESPONSAVEIS):
                combo.addItem(f"{codigo} — {ENTIDADES_RESPONSAVEIS[codigo]}", codigo)

        self.combo_responsavel_unidade = QComboBox()
        self.combo_operadora_unidade = QComboBox()
        for combo in (self.combo_responsavel_unidade, self.combo_operadora_unidade):
            combo.addItem("(não informado)", None)
            for codigo in sorted(UNIDADES_HIDRO):
                combo.addItem(UNIDADES_HIDRO[codigo], codigo)

        grid.addWidget(QLabel("Nome:"), 0, 0)
        grid.addWidget(self.input_nome, 0, 1, 1, 3)
        grid.addWidget(QLabel("Latitude:"), 1, 0)
        grid.addWidget(self.input_lat, 1, 1)
        grid.addWidget(QLabel("Longitude:"), 1, 2)
        grid.addWidget(self.input_lon, 1, 3)
        grid.addWidget(QLabel("Área de Drenagem:"), 2, 0)
        grid.addWidget(self.input_area, 2, 1)
        grid.addWidget(QLabel("Código Adicional:"), 2, 2)
        grid.addWidget(self.input_cod_adicional, 2, 3)
        grid.addWidget(QLabel("Responsável:"), 3, 0)
        grid.addWidget(self.combo_responsavel, 3, 1)
        grid.addWidget(QLabel("UF do Responsável:"), 3, 2)
        grid.addWidget(self.combo_responsavel_unidade, 3, 3)
        grid.addWidget(QLabel("Operadora:"), 4, 0)
        grid.addWidget(self.combo_operadora, 4, 1)
        grid.addWidget(QLabel("UF da Operadora:"), 4, 2)
        grid.addWidget(self.combo_operadora_unidade, 4, 3)

        # Tipo de estação + período de operação por parâmetro (cada um pode ter Início/Fim
        # diferentes; Fim em branco em qualquer um deles indica que a estação ainda opera nele)
        self.painel_tipo_fluvio = self._criar_grid_tipos(FLUVIO_TIPO_FIELDS)
        self.painel_tipo_pluvio = self._criar_grid_tipos(PLUVIO_TIPO_FIELDS)

        grid.addWidget(QLabel("Tipo:"), 5, 0)
        grid.addWidget(self.painel_tipo_pluvio, 5, 1, 1, 3)
        grid.addWidget(self.painel_tipo_fluvio, 5, 1, 1, 3)
        self.painel_tipo_fluvio.setVisible(False)

        # Telemétrica se aplica aos dois tipos de codificação, então fica sempre visível
        painel_telemetrica = self._criar_grid_tipos([TIPO_FIELD_TELEMETRICA])
        grid.addWidget(painel_telemetrica, 6, 1, 1, 3)

        btn_adicionar = QPushButton("Adicionar à lista")
        btn_adicionar.clicked.connect(self.adicionar_estacao_pendente)
        grid.addWidget(btn_adicionar, 7, 3)

        v.addWidget(form_frame)

        # Tabela de estações pendentes + ações de lista
        self.tabela_pendentes = QTableWidget()
        self.tabela_pendentes.setColumnCount(5)
        self.tabela_pendentes.setHorizontalHeaderLabels(["Nome", "Lat", "Lon", "Responsável", "Operadora"])
        self.tabela_pendentes.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabela_pendentes.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela_pendentes.setMaximumHeight(150)
        v.addWidget(self.tabela_pendentes)

        acoes_pendentes = QHBoxLayout()
        btn_remover = QPushButton("Remover selecionada")
        btn_remover.clicked.connect(self.remover_estacao_pendente)
        btn_importar_excel = QPushButton("Importar Excel simples...")
        btn_importar_excel.clicked.connect(self.importar_excel_simples)
        acoes_pendentes.addWidget(btn_remover)
        acoes_pendentes.addWidget(btn_importar_excel)
        acoes_pendentes.addStretch()
        v.addLayout(acoes_pendentes)

        return painel

    def _construir_painel_mdb(self) -> QWidget:
        painel = QWidget()
        file_layout = QHBoxLayout(painel)
        file_layout.setContentsMargins(0, 0, 0, 0)
        self.file_label = QLabel("Nenhum arquivo selecionado (.mdb)")
        btn_arquivo = QPushButton("Selecionar MDB")
        btn_arquivo.clicked.connect(self.selecionar_arquivo)
        file_layout.addWidget(self.file_label)
        file_layout.addWidget(btn_arquivo)
        return painel

    def atualizar_modo_entrada(self):
        modo_manual = self.radio_manual.isChecked()
        self.painel_manual.setVisible(modo_manual)
        self.painel_mdb.setVisible(not modo_manual)

    def atualizar_campos_tipo(self):
        fluvio = self.radio_fluvio.isChecked()
        self.painel_tipo_fluvio.setVisible(fluvio)
        self.painel_tipo_pluvio.setVisible(not fluvio)

    # ------------------------------------------------------------------
    # Cadastro manual: adicionar / remover / importar
    # ------------------------------------------------------------------
    def adicionar_estacao_pendente(self):
        nome = self.input_nome.text().strip()
        lat_txt = self.input_lat.text().strip().replace(',', '.')
        lon_txt = self.input_lon.text().strip().replace(',', '.')

        if not nome or not lat_txt or not lon_txt:
            QMessageBox.warning(self, "Campos obrigatórios", "Preencha Nome, Latitude e Longitude.")
            return
        try:
            lat = float(lat_txt)
            lon = float(lon_txt)
        except ValueError:
            QMessageBox.warning(self, "Valor inválido", "Latitude e Longitude devem ser números.")
            return

        if not (LAT_MIN_BR <= lat <= LAT_MAX_BR) or not (LON_MIN_BR <= lon <= LON_MAX_BR):
            resposta = QMessageBox.question(
                self, "Coordenada fora do Brasil",
                f"Latitude/Longitude ({lat}, {lon}) parece fora do território brasileiro.\n"
                "Deseja adicionar mesmo assim?",
                QMessageBox.Yes | QMessageBox.No)
            if resposta == QMessageBox.No:
                return

        linha = {
            'Nome': nome,
            'Latitude': lat,
            'Longitude': lon,
            'ResponsavelCodigo': self.combo_responsavel.currentData(),
            'OperadoraCodigo': self.combo_operadora.currentData(),
            'ResponsavelUnidade': self.combo_responsavel_unidade.currentData(),
            'OperadoraUnidade': self.combo_operadora_unidade.currentData(),
        }

        area_txt = self.input_area.text().strip().replace(',', '.')
        if area_txt:
            try:
                linha['AreaDrenagem'] = float(area_txt)
            except ValueError:
                pass

        cod_adicional = self.input_cod_adicional.text().strip()
        if cod_adicional:
            linha['CodigoAdicional'] = cod_adicional

        # Cada parâmetro marcado tem seu próprio período (Início/Fim). Se pelo menos um
        # parâmetro estiver com Fim em branco, a estação como um todo está em operação.
        campos_tipo = (FLUVIO_TIPO_FIELDS if self.radio_fluvio.isChecked() else PLUVIO_TIPO_FIELDS) \
            + [TIPO_FIELD_TELEMETRICA]

        algum_periodo_informado = False
        algum_periodo_sem_fim = False

        for campo, rotulo in campos_tipo:
            check = self.checks_tipo.get(campo)
            if check is None or not check.isChecked():
                continue
            linha[campo] = 1

            input_inicio, input_fim = self.inputs_periodo[campo]
            try:
                data_inicio = self._parse_data_br(input_inicio.text())
                data_fim = self._parse_data_br(input_fim.text())
            except ValueError as e:
                QMessageBox.warning(self, "Data inválida", f"{rotulo}: {e}")
                return

            prefixo = PERIODO_PREFIXOS.get(campo)
            if prefixo and data_inicio:
                linha[f'{prefixo}Inicio'] = data_inicio
                algum_periodo_informado = True
                if data_fim:
                    linha[f'{prefixo}Fim'] = data_fim
                else:
                    algum_periodo_sem_fim = True

        if algum_periodo_informado:
            linha['Operando'] = 1 if algum_periodo_sem_fim else 0

        self.pendentes.append(linha)
        self.atualizar_tabela_pendentes()

        self.input_nome.clear()
        self.input_lat.clear()
        self.input_lon.clear()
        self.input_area.clear()
        self.input_cod_adicional.clear()
        for check in self.checks_tipo.values():
            check.setChecked(False)
        for input_inicio, input_fim in self.inputs_periodo.values():
            input_inicio.clear()
            input_fim.clear()
        self.input_nome.setFocus()

    def remover_estacao_pendente(self):
        linha_sel = self.tabela_pendentes.currentRow()
        if linha_sel < 0:
            QMessageBox.information(self, "Nenhuma seleção", "Selecione uma linha na lista de pendentes para remover.")
            return
        del self.pendentes[linha_sel]
        self.atualizar_tabela_pendentes()

    def atualizar_tabela_pendentes(self):
        self.tabela_pendentes.setRowCount(len(self.pendentes))
        for i, linha in enumerate(self.pendentes):
            self.tabela_pendentes.setItem(i, 0, QTableWidgetItem(str(linha.get('Nome', ''))))
            self.tabela_pendentes.setItem(i, 1, QTableWidgetItem(f"{linha.get('Latitude', 0):.6f}"))
            self.tabela_pendentes.setItem(i, 2, QTableWidgetItem(f"{linha.get('Longitude', 0):.6f}"))
            resp = ENTIDADES_RESPONSAVEIS.get(linha.get('ResponsavelCodigo'), '')
            oper = ENTIDADES_RESPONSAVEIS.get(linha.get('OperadoraCodigo'), '')
            self.tabela_pendentes.setItem(i, 3, QTableWidgetItem(resp))
            self.tabela_pendentes.setItem(i, 4, QTableWidgetItem(oper))

    @staticmethod
    def _parse_float_br(valor) -> Optional[float]:
        """Converte um valor de célula (número ou texto com vírgula decimal) para float."""
        if valor is None:
            return None
        if isinstance(valor, (int, float)):
            return None if pd.isna(valor) else float(valor)
        texto = str(valor).strip().replace(',', '.')
        return float(texto) if texto else None

    @staticmethod
    def _parse_data_br(texto: str):
        """Converte dd/mm/aaaa ou mm/aaaa para date(); string vazia vira None."""
        texto = (texto or '').strip()
        if not texto:
            return None
        for fmt in ('%d/%m/%Y', '%m/%Y'):
            try:
                return datetime.strptime(texto, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Data '{texto}' não reconhecida. Use dd/mm/aaaa ou mm/aaaa.")

    @staticmethod
    def _achar_coluna(colunas_lower: Dict[str, str], aliases: List[str]) -> Optional[str]:
        for alias in aliases:
            if alias in colunas_lower:
                return colunas_lower[alias]
        return None

    def importar_excel_simples(self):
        caminho, _ = QFileDialog.getOpenFileName(self, "Importar Excel simples", "", "Excel Files (*.xlsx *.xls)")
        if not caminho:
            return
        try:
            df = pd.read_excel(caminho)
        except Exception as e:
            QMessageBox.critical(self, "Erro ao ler Excel", traduzir_erro(e))
            return

        colunas_lower = {str(c).lower().strip(): c for c in df.columns}
        col_nome = self._achar_coluna(colunas_lower, COLUNA_ALIASES['nome'])
        col_lat = self._achar_coluna(colunas_lower, COLUNA_ALIASES['latitude'])
        col_lon = self._achar_coluna(colunas_lower, COLUNA_ALIASES['longitude'])

        faltando = [rotulo for rotulo, col in
                    [('Nome', col_nome), ('Latitude', col_lat), ('Longitude', col_lon)] if col is None]
        if faltando:
            QMessageBox.warning(self, "Colunas não reconhecidas",
                                 "Não encontrei no Excel as colunas obrigatórias: " + ", ".join(faltando) + ".\n\n"
                                 "O cabeçalho não precisa ser idêntico ao do banco — aceito também variações como "
                                 "'Lat'/'Lon'. Renomeie a coluna correspondente e tente de novo.")
            return

        col_area = self._achar_coluna(colunas_lower, COLUNA_ALIASES['areadrenagem'])
        col_resp = self._achar_coluna(colunas_lower, COLUNA_ALIASES['responsavelcodigo'])
        col_oper = self._achar_coluna(colunas_lower, COLUNA_ALIASES['operadoracodigo'])
        col_cod_ad = self._achar_coluna(colunas_lower, COLUNA_ALIASES['codigoadicional'])

        importadas = 0
        ignoradas = []
        avisos = []

        for idx, row in df.iterrows():
            num_linha = idx + 2  # +2: linha 1 do Excel é o cabeçalho

            nome = str(row[col_nome]).strip() if pd.notna(row[col_nome]) else ''
            if not nome:
                ignoradas.append(f"Linha {num_linha}: Nome vazio")
                continue

            try:
                lat = self._parse_float_br(row[col_lat])
                lon = self._parse_float_br(row[col_lon])
            except (ValueError, TypeError):
                ignoradas.append(f"Linha {num_linha} ({nome}): Latitude/Longitude não são números "
                                  "(confira se não ficou texto ou fórmula com erro na célula)")
                continue
            if lat is None or lon is None:
                ignoradas.append(f"Linha {num_linha} ({nome}): Latitude/Longitude em branco")
                continue
            if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
                ignoradas.append(f"Linha {num_linha} ({nome}): coordenada fora de qualquer faixa válida "
                                  "(Latitude deve estar entre -90/90, Longitude entre -180/180 — confira se não "
                                  "estão trocadas)")
                continue
            if not (LAT_MIN_BR <= lat <= LAT_MAX_BR) or not (LON_MIN_BR <= lon <= LON_MAX_BR):
                avisos.append(f"Linha {num_linha} ({nome}): coordenada fora do território brasileiro — "
                               "importada mesmo assim, confira antes de processar")

            linha = {'Nome': nome, 'Latitude': lat, 'Longitude': lon}

            if col_area is not None and pd.notna(row[col_area]):
                try:
                    linha['AreaDrenagem'] = self._parse_float_br(row[col_area])
                except (ValueError, TypeError):
                    avisos.append(f"Linha {num_linha} ({nome}): Área de Drenagem não numérica, ignorada")

            for col, campo, rotulo in [(col_resp, 'ResponsavelCodigo', 'Responsável'),
                                        (col_oper, 'OperadoraCodigo', 'Operadora')]:
                if col is None or pd.isna(row[col]):
                    continue
                try:
                    codigo = int(float(row[col]))
                except (ValueError, TypeError):
                    avisos.append(f"Linha {num_linha} ({nome}): código de {rotulo} '{row[col]}' não é um número "
                                   "válido, ignorado")
                    continue
                if codigo not in ENTIDADES_RESPONSAVEIS:
                    avisos.append(f"Linha {num_linha} ({nome}): código de {rotulo} {codigo} não consta na "
                                   "tabela de entidades da ANA — importado mesmo assim, confira se não foi "
                                   "digitado errado")
                linha[campo] = codigo

            if col_cod_ad is not None and pd.notna(row[col_cod_ad]):
                linha['CodigoAdicional'] = str(row[col_cod_ad]).strip()

            self.pendentes.append(linha)
            importadas += 1

        self.atualizar_tabela_pendentes()
        self._mostrar_resumo_importacao(importadas, ignoradas, avisos)

    def _mostrar_resumo_importacao(self, importadas: int, ignoradas: List[str], avisos: List[str]):
        limite = 15
        partes = [f"{importadas} estação(ões) importada(s) com sucesso."]

        if ignoradas:
            partes.append(f"\n{len(ignoradas)} linha(s) ignorada(s) (não entraram na lista):")
            partes.extend(f"  • {msg}" for msg in ignoradas[:limite])
            if len(ignoradas) > limite:
                partes.append(f"  ... e mais {len(ignoradas) - limite}.")

        if avisos:
            partes.append(f"\n{len(avisos)} aviso(s) (entraram na lista mesmo assim, vale conferir):")
            partes.extend(f"  • {msg}" for msg in avisos[:limite])
            if len(avisos) > limite:
                partes.append(f"  ... e mais {len(avisos) - limite}.")

        texto = "\n".join(partes)
        if ignoradas or avisos:
            QMessageBox.warning(self, "Importação concluída com observações", texto)
        else:
            QMessageBox.information(self, "Importação concluída", texto)

    # ------------------------------------------------------------------
    # Modo legado: importação de .mdb existente
    # ------------------------------------------------------------------
    def selecionar_arquivo(self):
        f, _ = QFileDialog.getOpenFileName(self, "Abrir Banco Access", "", "Access Files (*.mdb *.accdb)")
        if f:
            self.file_label.setText(f)

    # ------------------------------------------------------------------
    # Tabela de resultados (Parte 3 do plano de melhorias)
    # ------------------------------------------------------------------
    def setup_tabela(self):
        colunas = ["Nome", "Lat", "Lon", "Bacia/Sub", "Info BHO6", "CÓDIGO GERADO", "Confiabilidade"]
        self.tabela.setColumnCount(len(colunas))
        self.tabela.setHorizontalHeaderLabels(colunas)
        self.tabela.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabela.itemChanged.connect(self.on_codigo_editado)

    def _criar_item_somente_leitura(self, texto: str) -> QTableWidgetItem:
        item = QTableWidgetItem(texto)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def atualizar_tabela(self):
        self.tabela.blockSignals(True)
        self.tabela.setRowCount(len(self.dados_processados))
        for i, row in enumerate(self.dados_processados):
            self.tabela.setItem(i, 0, self._criar_item_somente_leitura(str(row.get('Nome'))))
            self.tabela.setItem(i, 1, self._criar_item_somente_leitura(f"{row.get('Latitude'):.6f}"))
            self.tabela.setItem(i, 2, self._criar_item_somente_leitura(f"{row.get('Longitude'):.6f}"))

            bacia_info = f"Sub: {row.get('SubBaciaCodigo')}"
            aux = row.get('Info Auxiliar', 'N/A')
            self.tabela.setItem(i, 3, self._criar_item_somente_leitura(bacia_info))
            self.tabela.setItem(i, 4, self._criar_item_somente_leitura(aux))

            item_cod = QTableWidgetItem(str(row.get('Codigo')))
            item_cod.setBackground(Qt.yellow)
            item_cod.setForeground(Qt.black)
            self.tabela.setItem(i, 5, item_cod)

            metodo = row.get('MetodoGeracao', '—')
            item_conf = self._criar_item_somente_leitura(metodo)
            if metodo.startswith("Fallback"):
                item_conf.setBackground(COR_FALLBACK)
            elif metodo.startswith("Extrapolado"):
                item_conf.setBackground(COR_EXTRAPOLADO)
            elif metodo.startswith("Interpolado"):
                item_conf.setBackground(COR_INTERPOLADO)
            self.tabela.setItem(i, 6, item_conf)
        self.tabela.blockSignals(False)

    def on_codigo_editado(self, item: QTableWidgetItem):
        if item.column() != 5:
            return
        linha = item.row()
        texto = item.text().strip()
        try:
            novo_codigo = int(texto)
        except ValueError:
            QMessageBox.warning(self, "Código inválido", "O código deve ser um número inteiro.")
            self.tabela.blockSignals(True)
            item.setText(str(self.dados_processados[linha].get('Codigo')))
            self.tabela.blockSignals(False)
            return

        self.dados_processados[linha]['Codigo'] = novo_codigo

        outros_codigos = [d.get('Codigo') for j, d in enumerate(self.dados_processados) if j != linha]
        self.tabela.blockSignals(True)
        if novo_codigo in outros_codigos:
            item.setBackground(COR_DUPLICADO)
            QMessageBox.warning(self, "Código duplicado",
                                 f"O código {novo_codigo} já está sendo usado por outra estação nesta lista.\n"
                                 "A exportação usará o valor editado mesmo assim — ajuste se necessário.")
        else:
            item.setBackground(Qt.yellow)
        self.tabela.blockSignals(False)

    # ------------------------------------------------------------------
    # Processamento
    # ------------------------------------------------------------------
    def _habilitar_entradas(self, habilitado: bool):
        self.radio_pluvio.setEnabled(habilitado)
        self.radio_fluvio.setEnabled(habilitado)
        self.radio_manual.setEnabled(habilitado)
        self.radio_mdb.setEnabled(habilitado)
        self.btn_processar.setEnabled(habilitado)

    def processar(self):
        if self.radio_manual.isChecked():
            if not self.pendentes:
                QMessageBox.warning(self, "Aviso", "Adicione ao menos uma estação à lista antes de processar.")
                return
            dados_entrada = {'tipo': 'manual', 'linhas': list(self.pendentes)}
        else:
            arquivo = self.file_label.text()
            if not os.path.exists(arquivo) or not arquivo.endswith(".mdb"):
                QMessageBox.warning(self, "Aviso", "Selecione um arquivo .mdb válido.")
                return
            dados_entrada = {'tipo': 'mdb', 'caminho': arquivo}

        self._habilitar_entradas(False)
        self.btn_exportar.setEnabled(False)
        self.btn_cancelar.setVisible(True)
        self.btn_cancelar.setEnabled(True)
        self.btn_cancelar.setText("CANCELAR")
        self.tabela.setRowCount(0)
        self.progress.setValue(0)

        manager_class = ManagerPluviometrica if self.radio_pluvio.isChecked() else ManagerFluviometrica

        self.thread = QThread()
        self.worker = Worker(manager_class, dados_entrada)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_processing_finished)
        self.worker.error.connect(self.on_processing_error)
        self.worker.progress.connect(self.progress.setValue)

        self.thread.start()

    def cancelar_processamento(self):
        if self.worker is not None:
            self.worker.cancelar()
        self.btn_cancelar.setEnabled(False)
        self.btn_cancelar.setText("Cancelando...")

    def on_processing_finished(self, resultados):
        self.dados_processados = resultados
        self.manager = self.worker.manager
        self.btn_cancelar.setVisible(False)
        self._habilitar_entradas(True)

        if not resultados:
            QMessageBox.warning(self, "Sem Resultados",
                                "Nenhuma estação encontrada para os critérios selecionados.\n"
                                "Verifique se as estações no MDB possuem ResponsavelCodigo = 1 ou OperadoraCodigo = 82.")
            self.thread.quit()
            return

        tipo_proc = "Pluviométrica" if self.radio_pluvio.isChecked() else "Fluviométrica"
        self.atualizar_tabela()

        self.progress.setValue(100)
        QMessageBox.information(self, "Sucesso", f"Codificação {tipo_proc} concluída!")

        self.btn_exportar.setEnabled(True)
        self.thread.quit()

    def on_processing_error(self, error_message):
        self.progress.setValue(0)
        self.btn_cancelar.setVisible(False)
        self._habilitar_entradas(True)
        QMessageBox.critical(self, "Erro no Processamento", error_message)
        self.thread.quit()

    def exportar(self):
        if not self.dados_processados:
            QMessageBox.warning(self, "Erro", "Não há dados processados para exportar.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Salvar Resultados", "", "Access (*.mdb);;Excel (*.xlsx)")
        if path:
            try:
                self.manager.exportar_resultados(self.dados_processados, path)
                QMessageBox.information(self, "Sucesso", "Exportação concluída com sucesso!")
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Falha na exportação: {traduzir_erro(e)}")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
