import os
import sys
import pyodbc
import numpy as np
import pandas as pd
import geopandas as gpd
from sqlalchemy import create_engine
from shapely.geometry import Point
from typing import List, Dict, Optional, Set, Callable
import shutil
from datetime import datetime
from dotenv import load_dotenv

# Carrega variáveis do arquivo .env
load_dotenv()

# --- CONSTANTES TÉCNICAS (PADRÃO ANA/SGB) ---
TIPO_ESTACAO_FLUVIOMETRICA = 1
TIPO_ESTACAO_PLUVIOMETRICA = 2
COLUNA_SUBBACIA_DNAEE = 'DNS_NU_SUB'
TABELA_ESTACAO_SQL = 'HIDRO.dbo.Estacao'
TABELA_NOVAS_MDB = 'Estacoes_Novas'

# Drivers de Conexão
DRIVER_SQL_SERVER = "ODBC Driver 17 for SQL Server"
DRIVER_ACCESS = "Microsoft Access Driver (*.mdb, *.accdb)"

# Insumos (Base BHO6 e Referências)
GPKG_BHO_DRENAGEM = r"insumo\geoft_bho6_trecho_drenagem.gpkg"
CAMADA_BHO_TRECHO = "geoft_bho6_trecho_drenagem" 
GPKG_MUNICIPIOS = r"insumo\Municipio_IBGE_Hidro.gpkg"
GPKG_SUBBACIAS_DNAEE = r"insumo\geoft_dnaee_subbacia.gpkg"
TEMPLATE_MDB = r"mdb\template.mdb"  # ships com o projeto/release, NÃO faz parte da pasta insumo (rede da ANA)

# Sistemas de Referência (Nota Técnica 05/2024)
CRS_SIRGAS2000 = "EPSG:4674"
CRS_POLICONICA = "EPSG:5880" 

# Configurações de Precisão e Espaçamento
BUFFER_SNAPPING_METROS = 200 
INCREMENTO_FLU = 10           # Incremento de 10 em 10 para Fluviométrica
INCREMENTO_PLUVIO = 1         # Incremento unitário para Pluviométrica
INCREMENTO_PADRAO_FALLBACK = 10000 

# Colunas do Template Oficial da ANA (68 colunas)
COLUNAS_TEMPLATE_MDB = [
    'RegistroID', 'Importado', 'Temporario', 'Removido', 'ImportadoRepetido',
    'BaciaCodigo', 'SubBaciaCodigo', 'RioCodigo', 'EstadoCodigo', 'MunicipioCodigo',
    'ResponsavelCodigo', 'ResponsavelUnidade', 'ResponsavelJurisdicao', 'OperadoraCodigo',
    'OperadoraUnidade', 'OperadoraSubUnidade', 'TipoEstacao', 'Codigo', 'Nome',
    'CodigoAdicional', 'Latitude', 'Longitude', 'Altitude', 'AreaDrenagem',
    'TipoEstacaoEscala', 'TipoEstacaoRegistradorNivel', 'TipoEstacaoDescLiquida',
    'TipoEstacaoSedimentos', 'TipoEstacaoQualAgua', 'TipoEstacaoPluviometro',
    'TipoEstacaoRegistradorChuva', 'TipoEstacaoTanqueEvapo', 'TipoEstacaoClimatologica',
    'TipoEstacaoPiezometria', 'TipoEstacaoTelemetrica', 'PeriodoEscalaInicio',
    'PeriodoEscalaFim', 'PeriodoRegistradorNivelInicio', 'PeriodoRegistradorNivelFim',
    'PeriodoDescLiquidaInicio', 'PeriodoDescLiquidaFim', 'PeriodoSedimentosInicio',
    'PeriodoSedimentosFim', 'PeriodoQualAguaInicio', 'PeriodoQualAguaFim',
    'PeriodoPluviometroInicio', 'PeriodoPluviometroFim', 'PeriodoRegistradorChuvaInicio',
    'PeriodoRegistradorChuvaFim', 'PeriodoTanqueEvapoInicio', 'PeriodoTanqueEvapoFim',
    'PeriodoClimatologicaInicio', 'PeriodoClimatologicaFim', 'PeriodoPiezometriaInicio',
    'PeriodoPiezometriaFim', 'PeriodoTelemetricaInicio', 'PeriodoTelemetricaFim',
    'TipoRedeBasica', 'TipoRedeEnergetica', 'TipoRedeNavegacao', 'TipoRedeCursoDagua',
    'TipoRedeEstrategica', 'TipoRedeCaptacao', 'TipoRedeSedimentos', 'TipoRedeQualAgua',
    'TipoRedeClasseVazao', 'UltimaAtualizacao', 'Operando', 'Descricao', 'Historico', 'NumImagens',
    'DataIns','DataAlt', 'RespAlt'
]

# Tabela 4 do Inventario das Estacoes Fluviometricas (ANA, 2009) - entidades responsaveis/operadoras
ENTIDADES_RESPONSAVEIS = {
    1: 'ANA Agência Nacional de Águas',
    2: 'DNOS Departamento Nacional de Obras de Saneamento',
    3: 'DNIT Departamento Nacional de Infra-Estrutura de Transportes',
    4: 'CODEVASF Cia de Desenvolvimento dos Vales do São Francisco e Parnaíba',
    5: 'INMET Instituto Nacional de Meteorologia',
    6: 'CESP Cia Energética de São Paulo',
    7: 'CEEE Cia Estadual de Energia Elétrica do Rio Grande do Sul',
    8: 'LIGHT Light Serviços de Eletricidade S.A.',
    9: 'FUNCEME Fundação Cearense de Meteorologia e Recursos Hídricos',
    10: 'FCTH/DAEE-SP Departamento de Águas e Energia Elétrica do Estado de São Paulo',
    11: 'SUDENE Superintendência do Desenvolvimento do Nordeste',
    12: 'PRADA Cia Prada de Eletricidade',
    13: 'CEMAT Centrais Elétricas Matogrossenses S.A.',
    14: 'EFMM Estrada de Ferro Madeira-Mamoré',
    15: 'CELESC Centrais Elétricas de Santa Catarina S.A.',
    16: 'EEVPSA Empresa de Eletricidade Vale do Paranapanema S.A.',
    17: 'SUL PAULISTA Empresa de Eletricidade Sul Paulista S.A.',
    18: 'CEA Cia de Eletricidade do Amapá',
    19: 'CELPA Centrais Elétricas do Pará S.A.',
    20: 'ALUMINAS Alumínio Minas Gerais S.A.',
    21: 'EFVM Estrada de Ferro Vitória-Minas',
    22: 'CBCC Cia Brasileira de Carbureto de Cálcio',
    23: 'CEMIG Cia Energética de Minas Gerais',
    24: 'SCHLEMN Cia Alexandre Schlemn',
    25: 'ICB Instituto do Cacau da Bahia',
    26: 'EESC Escola de Engenharia de São Carlos',
    27: 'SANBRA Sociedade Algodoeira do Nordeste do Brasil',
    28: 'COPEL Cia Paranaense de Energia',
    29: 'SOUZA CRUZ Cia de Cigarros Souza Cruz Indústria e Comércio Ltda.',
    30: 'ICOMI Industria e Comércio de Minérios',
    31: 'ACCO Anderson Clayton e Cia Ltda.',
    32: 'CMNP Cia de Melhoramento Norte do Paraná',
    33: 'CTNP Cia de Terras Norte do Paraná',
    34: 'CEMAR Cia Energética do Maranhão S.A.',
    35: 'FABA Fomento Agrícola da Bahia',
    36: 'CPFL Cia Paulista de Ferro Ligas',
    37: 'COELBA Cia de Eletricidade do Estado da Bahia',
    38: 'SABA Secretaria da Agricultura da Bahia',
    39: 'FASE Fomento Agrícola de Sergipe',
    40: 'IRGA Instituto Riograndense do Arroz',
    41: 'USIBA Usina Siderúrgica da Bahia',
    42: 'EMBRAPA Empresa Brasileira de Pesquisa Agropecuária',
    43: 'KLABIN Indústria Klabin de Celulose do Paraná',
    44: 'CLFSC Cia Luz e Força Santa Cruz',
    45: 'STEVENSON F . Stevenson e Companhia',
    46: 'DER-SP Departamento de Estrada de Rodagem do Estado de São Paulo',
    47: 'RFFSA Rede Ferroviária Federal S.A.',
    48: 'SAA-SP Secretaria de Estado da Agricultura e Abastecimento de São Paulo',
    49: 'CEESC Comissão de Energia Elétrica de Santa Catarina',
    50: 'FEPASA Ferrovia Paulista S.A.',
    51: 'SOPRS Secretaria de Obras Públicas e Saneamento do Estado do Rio Grande do Sul',
    52: 'SUDERHSA Superintendência de Recursos Hídricos e Saneamento Ambiental',
    53: 'CIA Centro Industrial de Aratú',
    54: 'COPASA Cia de Saneamento de Minas Gerais',
    55: 'ELETROBRÁS Centrais Elétricas Brasileiras S.A.',
    56: 'IDESP Instituto de Desenvolvimento Econômico e Social do Pará',
    57: 'DEPV Diretoria de Eletrônica e Proteção ao Vôo do Ministério da Aeronáutica',
    58: 'DNOCS Departamento Nacional de Obras Contra as Secas',
    59: 'FEEMA Fundação Estadual de Engenharia do Meio Ambiente - RJ',
    60: 'IAA Instituto do Açúcar e do Álcool',
    61: 'DHN Diretoria de Hidrografia e Navegação do Ministério da Marinha',
    62: 'CEPLAC Comissão Executiva do Plano de Recup. Econômica-Social da Lavoura Cacaueira',
    63: 'CLM Comissão da Lagoa Mirim',
    64: 'SUDAM Superintendência do Desenvolvimento da Amazônia',
    65: 'DEPRC Departamento Estadual de Portos, Rios e Canais do Rio Grande do Sul',
    66: 'DMAE Departamento Municipal de Águas e Esgoto - Porto Alegre / RS',
    67: 'IAPAR Instituto Agrônomo do Paraná',
    68: 'DAEE-MG Departamento de Águas e Energia Elétrica de Minas Gerais',
    69: 'FURNAS Furnas Centrais Elétricas S.A.',
    70: 'MMV Mineração Morro Velho S.A.',
    71: 'SABESP Cia de Saneamento Básico do Estado de São Paulo',
    72: 'GERAL Cia Geral de Eletricidade',
    73: 'EMBASA Empresa Baiana de Saneamento',
    74: 'CERB Cia de Engenharia Rural da Bahia',
    75: 'ELETRONORTE Centrais Elétricas do Norte do Brasil',
    76: 'SERLA Superintendência Estadual de Rios e Lagoas do Rio de Janeiro',
    77: 'CAESB Companhia de Saneamento Ambiental do Distrito Federal',
    78: 'PLANALSUCAR Programa Nacional de Melhoramento da Cana-de-Açúcar',
    79: 'ELETROSUL Centrais Elétricas do Sul do Brasil S.A.',
    80: 'CHESF Cia Hidrelétrica do São Francisco',
    81: 'CVRD Cia Vale do Rio Doce',
    82: 'CPRM Cia de Pesquisa de Recursos Minerais',
    83: 'CAGEPA Cia de Águas e Esgoto da Paraíba',
    84: 'ELETROPAULO Metropolitana Eletricidade de São Paulo S.A.',
    85: 'HIDROLOGIA Engenharia, Industria e Comércio S.A.',
    86: 'CNEC Consorcio Nacional de Engenheiros Consultores',
    87: 'HIDROSERVICE Engenharia de Projetos Ltda.',
    88: 'HIDROESB Saturnino de Brito S.A.',
    89: 'EMATER Empresa Estadual de Assistência Tec. e Ext. Rural',
    90: 'ITAIPU Itaipu - Binacional',
    91: 'SEMA-MT Secretaria do Estado de Meio Ambiente',
    92: 'LMRS-PB Laboratório de Met., Rec. Hid. e Sensoriamento Remoto da Paraíba',
    93: 'SIMEPAR Sistema Meteorológico do Paraná',
    94: 'EPAGRI Empresa de Pesquisa Agrícola de Santa Catarina',
    95: 'CELTINS Cia. Energia Elétrica do Estado do Tocantins',
    96: 'SEAMA Secretaria de Estado para A. do Meio Ambiente do Espírito Santo',
    97: 'EMPARN Empresa de Pesquisa Agropecuária do Rio Grande do Norte',
    98: 'SANEPAR Cia de Saneamento do Paraná',
    99: 'OUTRAS Outras',
    100: 'COHIDRO Consultoria, Estudos e Projetos',
    101: 'IGAM Instituto Mineiro de Gestão das Águas',
    102: 'SDM Secretaria de Estado de Desenvolvimento Urbano e Meio Ambiente',
    103: 'GERASUL Centrais Elétricas do Sul do Brasil',
    104: 'CPRH Companhia Pernambucana do Meio Ambiente',
    105: 'SEMA-AP Secretaria de Meio Ambiente do Estado do Amapá',
    106: 'COGERH Companhia de Gestão de Recursos Hídricos - Ceará',
    107: 'CRA Centro de Recursos Ambientais da Bahia',
    108: 'HYDROCONSULT Hydroconsult - Hidrométrica Comércio e Serviços Ltda.',
    109: 'SNIRH-MA Sistema Nacional de Informações sobre Recursos Hídricos - Maranhão',
    110: 'ANEEL Agência Nacional de Energia Elétrica',
    111: 'NATURATINS Instituto Natureza do Tocantins',
    112: 'TRACTEBEL Tractebel Energia S.A.',
    113: 'CETESB Companhia de Tecnologia de Saneamento Ambiental',
    114: 'SRH-BA Superintendência de Recursos Hídricos da Bahia',
    115: 'SEDAM Secretaria de Estado do Desenvolvimento Ambiental - RO',
    116: 'SEMA-MS Secretaria de Meio Ambiente / Estado do Mato Grosso do Sul',
    117: 'CASAN Companhia Catarinense de Águas e Saneamento de SC',
    118: 'RTK RTK Engenharia',
    119: 'DINFRA Departamento Nacional de Infra Estrutura',
    120: 'SEMARH-LUZ Secretaria Municipal do Meio Ambiente e dos Recursos Hídricos - Luziana',
    121: 'SEMARH-AL Secretaria do Meio Ambiente e Recursos Hídricos - AL',
    122: 'CELG Centrais Elétrica de Goiás',
    123: 'CEDAE Companhia Estadual de Águas e Esgotos',
    124: 'SIMEGO Sistema Meteorológico do Estado de Goiás',
    125: 'UFAM Universidade Federal do Estado do Amazonas',
    126: 'MANASA Madeireira Nacional S/A',
    127: 'INPE Instituto Nacional de Pesquisas Espaciais',
    128: 'UFSM Universidade Federal de Santa Maria - RS',
    129: 'ENERCAN Campos Novos Energia S.A.',
    130: 'ENERSUL Empresa Energética do Mato Grosso do Sul',
    131: 'DUKE Duke Energy',
    132: 'CERJ Companhia de Eletricidade do Rio de Janeiro',
    133: 'CEB Companhia de Eletricidade de Brasília',
    134: 'VITERBO Viterbo Machado Luz Mineração Ltda.',
    135: 'COOPERLUZ Cooperativa de Eletreficação e Desenvolvimento da Fronteira Noroeste Ltda',
    136: 'JAGUARI Jaguari Energética S/A',
    137: 'CBA Companhia Brasileira de Alumínio',
    138: 'ENGEP Engenharia e Pavimentação Ltda',
    139: 'CONSTRUSERV Construserv Serviços Gerais Ltda',
    140: 'UFBA Universidade Federal da Bahia',
    141: 'CAIUÁ Caiuá Serviços de Eletricidade S.A.',
    142: 'ALCAN Alcan Embalagens do Brasil',
    143: 'AES Companhia de Geração de Energia Elétrica',
    144: 'ADAMI Adami Madeiras S.A.',
    145: 'AGROROSSATO Agropecuária Rossato Ltda.',
    146: 'AMANARY Amanary Eletricidade Ltda.',
    147: 'APROVALE Associação de Produtores Rurais do Vale do Cedro',
    148: 'AMPER Amper Energia Ltda.',
    149: 'ARAPUCEL Araputama Centrais Elétricas S.A.',
    150: 'BAESA Energética Barra Grande S.A.',
    151: 'BELGO MINEIRA Companhia Siderúrgica Belgo Mineira',
    152: 'BONDESPACHENSE Companhia Industrial Aliança Bondespachense',
    153: 'BRAGAGNOLO Avelino Bragagnolo S/A Industria e Comércio',
    154: 'BRASCAN Brascan Energética',
    155: 'BONET Bonet Madeiras e Papéis Ltda.',
    156: 'BT GERADORA Bt Geradora de Energia Elétrica Ltda.',
    157: 'CAÇADOREN Caçador Energia',
    158: 'ELETROGOES S/A Hidrelétricas Cassol Ltda.',
    159: 'CASTAMAN Centrais Elétricas Ltda.',
    160: 'CDSA Centrais Elétricas Cachoeira Dourada S.A.',
    161: 'FIAÇÃO CEDRO Companhia Fiação Tecidos Cedro Cachoeira',
    162: 'CEESAM Cooperativa de Energia Elétrica Santa Maria Ltda.',
    163: 'CEJARAGUÁ Companhia Eletroquimica Jaraguá',
    164: 'IRANI Celulose Irani S.A.',
    165: 'CEM Companhia Energética Meridional',
    166: 'CERFOX Cooperativa de Energia e Desenvolvimento Rurais Fontoura Xavier Ltda.',
    167: 'CERILUZ Cooperativa Regional de Energia e Desenvolvimento Ijui Ltda.',
    168: 'CERMISSÕES Cooperativa Regional de Eletrificação Rural das Missões',
    169: 'CERTEL Cooperativa Regional de Eletrificação Teotonia Ltda.',
    170: 'CERTHIL Cooperativa de Energia e Desenvolvimento Rural Entre Rios Ltda.',
    171: 'CESA Castelo Energética S.A.',
    172: 'CFLCL Companhia Força e Luz Cataguases Leopoldina',
    173: 'ELETRAM Novo Mundo Energética',
    174: 'ITAÚ Cimento Itaú',
    175: 'CANDONGA Consórcio Candonga',
    176: 'COPREL Cooperativa de Energia e Desenvolvimento Rural Ltda.',
    177: 'CORUMBÁ Corumbá IV',
    178: 'COSTA RICA Costa Rica Energética',
    179: 'CRELUZ Cooperativa de Energia e Desenvolvimento Rural do Médio Uruguai',
    180: 'ELOI BRUNETTA Eloi Bruneta e Cia. Ltda.',
    181: 'ESCELSA Espírito Santo Centrais Elétricas S.A.',
    182: 'FAIXA AZUL Faixa Azul Industria de Móveis para Escritório Ltda.',
    183: 'FAXINAL Madeireira Faxinal Ltda.',
    184: 'GLOBAL Global Energia Elétrica S.A.',
    185: 'HEIDRICH Heidrich Geração Elétrica Ltda',
    186: 'IBEMA Ibema Companhia de Papel',
    187: 'INSAM Indústria de Madeiras Santa Maria Ltda.',
    188: 'ITAIQUARA Uhe Itaiquara',
    189: 'ITISA Itiquira Energética S.A.',
    191: 'LARROSA Larrosa Construmil',
    192: 'LASA Lago Azul Ltda.',
    193: 'MAFRAS Uhe Mafras',
    194: 'MANAUS ENERGIA Manaus Energia',
    195: 'RGE RGE',
    196: 'SAMARCO Samarco Mineração S.A.',
    197: 'TROMBINI Trombine Papel e Embalagens S.A.',
    198: 'TRAPICHE Usina Trapiche S.A.',
    199: 'VALESUL Valesul Alumínio S.A.',
    200: 'RECIMAP Recimap Indústria e Comércio Ltda.',
    201: 'ORSA Orsa Celulose, Papel e Embalagens S.A.',
    202: 'MORRO VELHO Mineração Morro Velho Ltda.',
    203: 'ITAMARATI Itamarati Norte S.A Agropecuária',
    204: 'CEC Companhia Energética Chapecó',
    205: 'FERTILIGAS Fertiligas Industria e Comércio Ltda.',
    206: 'ITAPEBI Itapebi Geração de Energia',
    207: 'PRIMO TEDESCO Fabrica de Papel Primo Tedesco S.A.',
    208: 'FLP Ferro Ligas Piracicaba Ltda.',
    209: 'QGE Queiros Galvão Elétrica S.A.',
    210: 'INVESTCO Investco S.A.',
    211: 'ELEKTRO Instituto Elektro',
    212: 'CER Centrais Elétricas de Roraima',
    213: 'CESC Colorado Energy Science Center',
    214: 'CHESP Companhia Hidroelétrica São Patrício',
    215: 'COTIPORÃ Cotiporã Energética',
    216: 'CLFSC Companhia Luz e Força Santa Cruz',
    217: 'HIDROPAN Hidroelétrica Panambi S.A.',
    218: 'CSPE Comissão de Serviços Públicos de Energia - SP',
    219: 'CODESP Companhia Docas do Estado de São Paulo',
    220: 'DEMEI Departamento Municipal de Energia de Ijui',
    221: 'ELETROCAR Centrais Elétricas de Carazinho S.A.',
    222: 'ENERCOOP Grupo Itaquerê',
    223: 'ENGECORPS Corpo de Engenheiros Consultores Ltda.',
    224: 'AGRO-MAGGI Maggi Energia S.A.',
    225: 'ALTO E Hidroelétrica Alto E Ltda.',
    226: 'CEP Companhia Energética Paulista S.A.',
    227: 'CIA MINAS Companhia Minas da Passagem',
    228: 'CJE Companhia Jaguari de Eletricidade',
    229: 'CPEE Companhia Paulista de Energia Elétrica',
    230: 'BARRA MANSA Barra Mansa Energia',
    231: 'EEVP Empresa de Eletricidade Vale do Paranapanema S.A.',
    232: 'DMEPC Departamento Municipal de Eletricidade de Poços de Caldas',
    233: 'ELETRON Eletron Eletricidade de Rondônia S.A.',
    234: 'ELFSM Empresa Luz e Força Santa Maria S.A.',
    235: 'FOCKINK Fockink Industrias Elétricas Ltda.',
    236: 'FORCEL Força e Luz Coronel Vivida Ltda.',
    237: 'HIDROBASA Hidrometria da Bahia Ltda.',
    238: 'HIDROTÉRMICA Hidrotérmica S.A.',
    239: 'HORIZONTE Horizonte Textil Ltda.',
    240: 'SÃO MARCOS Hidroelétrica Rio São Marcos',
    241: 'NADIRFIGUEIREDO Nadir Figueiredo Industria e Comércio S.A.',
    242: 'PESQUEIRO Pesqueiro Energia S.A.',
    243: 'PIRAPAMA Companhia Industrial Pirapama',
    244: 'PPESA Ponte de Pedra Energética S.A.',
    245: 'ROSAL Rosal Energia S.A.',
    246: 'SANTANENSE Companhia Tecidos Santanense',
    247: 'SULGIPE Companhia Sul Sergipana de Eletricidade',
    248: 'SÃO PEDRO Tecelagem São Pedro',
    249: 'UFRP Universidade Federal Rural de Pernambuco',
    250: 'BARRA MANSA Siderúrgica Barra Mansa S.A.',
    251: 'SEMESA Semesa S.A.',
    252: 'MARINGÁ Maringá S.A. Cimento e Ferro-Liga',
    253: 'IMBEL Industria de Material Bélico do Brasil',
    254: 'CLFC Companhia Força e Luz Mococa',
    255: 'CRB Cimento Rio Branco S.A.',
    256: 'CESLL Companhia Energética Salto do Lobo Ltda.',
    257: 'ERPSA Energética Rio Pedrinho S.A.',
    258: 'RMARTINS PCH Raimundo Martins',
    259: 'CONCREMAT Concremat Engenharia e Tecnologia',
    260: 'HIDRECON Energia Independente',
    261: 'ELTAN Eltan Energética',
    262: 'SENGES Senges Papel e Celulose Ltda.',
    263: 'CRISTO REI Industrias Reunidas Cristo Rei Ltda.',
    264: 'CERSAD Cooperativa de Energia Elétrica Rural Salto Donner',
    265: 'CURUÁ Curuá Energia S.A.',
    266: 'SEMA-RS Secretaria de Meio Ambiente do Estado do Rio Grande do Sul',
    267: 'MAGNA Magna Engenharia Ltda.',
    268: 'PRCPI Produtividade Rural Comércio de Peças de Irrigação Ltda.',
    269: 'UFPA Universidade Federal do Pará',
    270: 'INCAPER Instituto Capixaba de Pesquisa',
    271: 'WIMOR Wimor Empreendimentos e Participações',
    272: 'ROVENA Rovena - Veículos e Máquinas Ltda.',
    273: 'PAE Pouso Alto Energia S.A.',
    274: 'RSESA Rio do Sangue Energia S.A.',
    275: 'SEIVA SEIVA Engenharia e Projetos Ambientais Ltda.',
    276: 'INTERNATIONAL International Paper do Brasil',
    277: 'TAIRETÁ Tairetá Eletricidade Ltda.',
    278: 'ENERPEIXE UHE - Peixe Angical',
    279: 'CJE-SA CJ Energética S/A',
    280: 'VOTORANTIM Votorantim Metais Zinco S/A',
    281: 'HIDROTÉCNICA Hidrotécnica Serviços Técnicos Ltda',
    282: 'SEIVAL SEIVAL Usina Termelétrica Ltda',
    284: 'AESA Agência Executiva de Gestão das Águas do Estado da Paraíba',
    285: 'COSTA BARROS Costa Barros Engenharia',
    286: 'FEPI Fundação de Ensino e Pesquisa de Itajubá',
    287: 'JCTM JCTM Ltda.',
    288: 'ARROSSENSAL Arrossensal Agropecuária e Comercial S.A.',
    289: 'ELEJOR Elejor',
    290: 'ELETROPRIMAVERA Centrais Elétricas Primavera Ltda.',
    500: 'DESATIVADA Estação Desativada',
    901: 'URUGUAI Uruguai',
    902: 'ARGENTINA Argentina',
    903: 'PARAGUAI Paraguai',
    904: 'CHILE Chile',
    905: 'BOLIVIA Bolívia',
    906: 'PERU Peru',
    907: 'COLÔMBIA Colômbia',
    908: 'EQUADOR Equador',
    909: 'VENEZUELA Venezuela',
    910: 'GUIANA Guiana',
    911: 'SURINAME Suriname',
    912: 'GUIANA FRANCESA Guiana Francesa',
}

# Tabela HIDRO.dbo.Estado (Codigo interno da ANA/HIDRO -- NAO é o CodigoIBGE). Usada nos campos
# ResponsavelUnidade/OperadoraUnidade para indicar a UF (ou pais, no caso de bacias
# transfronteiriças) da entidade. Preenchimento é manual, sem relação automática com
# ResponsavelCodigo/OperadoraCodigo -- por isso vem numa tabela própria, não derivada.
UNIDADES_HIDRO = {
    1: 'RO Rondônia', 2: 'AC Acre', 3: 'AM Amazonas', 4: 'RR Roraima', 5: 'PA Pará',
    6: 'AP Amapá', 7: 'MA Maranhão', 8: 'PI Piauí', 9: 'CE Ceará', 10: 'RN Rio Grande do Norte',
    11: 'PB Paraíba', 12: 'PE Pernambuco', 13: 'AL Alagoas', 15: 'SE Sergipe', 16: 'BA Bahia',
    17: 'MG Minas Gerais', 18: 'ES Espírito Santo', 19: 'RJ Rio de Janeiro', 21: 'SP São Paulo',
    22: 'PR Paraná', 23: 'SC Santa Catarina', 24: 'RS Rio Grande do Sul', 25: 'MT Mato Grosso',
    26: 'GO Goiás', 27: 'DF Distrito Federal', 28: 'MS Mato Grosso do Sul', 29: 'TO Tocantins',
    61: 'UR Uruguai', 62: 'AR Argentina', 63: 'PG Paraguai', 64: 'CH Chile', 65: 'BO Bolívia',
    66: 'PU Peru', 67: 'CO Colômbia', 68: 'EQ Equador', 69: 'VE Venezuela', 70: 'GU Guiana',
    71: 'SU Suriname', 72: 'GF Guiana Francesa',
}


def resource_path(relative_path: str) -> str:
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)


def _valor_sql(valor, tipo_coluna: Optional[str] = None):
    """Converte valores vindos do GeoPandas/NumPy (int32, int64, float64...) para tipos nativos
    do Python -- o driver ODBC do Access rejeita tipos numpy como parâmetro de INSERT
    ('Tipo de dados incompatível na expressão de critério'). Também converte pra string
    quando a coluna real no Access é VARCHAR mas o valor calculado é numérico (o template
    oficial guarda até campos como Codigo/RegistroID como texto, não número)."""
    if pd.isna(valor):
        return None
    if isinstance(valor, np.generic):
        valor = valor.item()
    if tipo_coluna == 'VARCHAR' and not isinstance(valor, str):
        if isinstance(valor, float) and valor.is_integer():
            valor = int(valor)
        valor = str(valor)
    return valor


def montar_sql_conn_str() -> str:
    return (f"DRIVER={{{DRIVER_SQL_SERVER}}};SERVER={os.getenv('DB_HOST')};"
            f"DATABASE={os.getenv('DB_NAME')};UID={os.getenv('DB_USER')};"
            f"PWD={os.getenv('DB_PASSWORD')};")


def carregar_entidades_atualizadas() -> Dict[int, str]:
    """
    Busca a lista de entidades responsáveis/operadoras direto de HIDRO.dbo.Entidade (mais
    de 1300 registros, sempre atualizada). Se o banco não estiver acessível agora (sem
    VPN, por exemplo), cai no fallback estático ENTIDADES_RESPONSAVEIS (Tabela 4 do
    Inventário ANA/2009 — só ~300 entidades, mas melhor que uma lista vazia).
    """
    try:
        with pyodbc.connect(montar_sql_conn_str(), timeout=4) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT Codigo, Sigla, Nome FROM HIDRO.dbo.Entidade WHERE Removido = 0 ORDER BY Codigo")
            entidades = {r[0]: f"{r[1]} {r[2]}" for r in cursor.fetchall() if r[0] is not None}
            return entidades if entidades else ENTIDADES_RESPONSAVEIS
    except Exception:
        return ENTIDADES_RESPONSAVEIS


class ProcessamentoCancelado(Exception):
    """Levantada quando o usuário cancela o processamento em andamento."""
    pass


def traduzir_erro(exc: Exception) -> str:
    """Converte exceções técnicas comuns em mensagens compreensíveis para o usuário final."""
    texto = str(exc)
    texto_lower = texto.lower()

    if isinstance(exc, ProcessamentoCancelado):
        return "Processamento cancelado pelo usuário."
    if "login failed" in texto_lower or "server does not exist" in texto_lower or "sql server" in texto_lower or "network-related" in texto_lower:
        return ("Não foi possível conectar ao banco de dados SQL Server.\n"
                "Verifique sua conexão de rede/VPN e as credenciais configuradas no arquivo .env.\n\n"
                f"Detalhe técnico: {texto}")
    if "insumo" in texto_lower or isinstance(exc, FileNotFoundError):
        return ("Não foi possível encontrar um arquivo de insumo necessário (shapefile, GPKG ou "
                "template).\nVerifique se a pasta 'insumo' está no mesmo diretório do executável "
                "e contém todos os arquivos exigidos.\n\n"
                f"Detalhe técnico: {texto}")
    if "estacoes_novas" in texto_lower or ("table" in texto_lower and "not" in texto_lower):
        return ("O arquivo .mdb selecionado não contém a tabela 'Estacoes_Novas' esperada.\n"
                "Verifique se é o arquivo correto ou use o modo de cadastro manual.\n\n"
                f"Detalhe técnico: {texto}")
    return texto

class BaseManager:
    def __init__(self):
        self.sql_conn_str = montar_sql_conn_str()
        self.avisos_insumo: List[str] = []
        self.gdf_mun = self._carregar_shape(GPKG_MUNICIPIOS, "Malha de Municípios (IBGE)")
        self.gdf_sub = self._carregar_shape(GPKG_SUBBACIAS_DNAEE, "Sub-bacias DNAEE")
        self.next_reg_id = self._buscar_ultimo_reg_id()

    def _carregar_shape(self, path: str, nome_amigavel: str):
        full_path = resource_path(path)
        if not os.path.exists(full_path):
            self.avisos_insumo.append(
                f"{nome_amigavel}: arquivo não encontrado em '{full_path}'. "
                "Município/Estado/Bacia/Sub-bacia ficarão em branco nos resultados."
            )
            return None
        try:
            return gpd.read_file(full_path).to_crs(CRS_SIRGAS2000)
        except Exception as e:
            self.avisos_insumo.append(f"{nome_amigavel}: falha ao ler o arquivo ({e}).")
            return None

    def _get_access_engine(self, mdb_path: str):
        conn_str = f"DRIVER={{{DRIVER_ACCESS}}};DBQ={mdb_path};"
        return create_engine(f"access+pyodbc:///?odbc_connect={conn_str}")

    def carregar_df_de_mdb(self, caminho_arquivo: str) -> pd.DataFrame:
        """Lê as estações ainda sem Código da tabela Estacoes_Novas de um .mdb existente."""
        engine = self._get_access_engine(caminho_arquivo)
        return pd.read_sql(f"SELECT * FROM {TABELA_NOVAS_MDB} WHERE Codigo IS NULL", engine)

    @staticmethod
    def montar_df_de_linhas_manuais(linhas: List[Dict]) -> pd.DataFrame:
        """Monta um DataFrame no formato do template ANA a partir de estações cadastradas manualmente na GUI."""
        defaults = {
            'Importado': 0, 'Temporario': 0, 'Removido': 0, 'ImportadoRepetido': 0, 'Operando': 1,
            'TipoRedeBasica': 0, 'TipoRedeEnergetica': 0, 'TipoRedeNavegacao': 0, 'TipoRedeCursoDagua': 0,
            'TipoRedeEstrategica': 0, 'TipoRedeCaptacao': 0, 'TipoRedeSedimentos': 0, 'TipoRedeQualAgua': 0,
            'TipoRedeClasseVazao': 0,
        }
        linhas_completas = []
        for linha in linhas:
            reg = {col: None for col in COLUNAS_TEMPLATE_MDB}
            reg.update(defaults)
            reg.update({k: v for k, v in linha.items() if v is not None})
            linhas_completas.append(reg)
        return pd.DataFrame(linhas_completas)

    def _buscar_ultimo_reg_id(self) -> int:
        try:
            with pyodbc.connect(self.sql_conn_str) as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT MAX(RegistroID) FROM {TABELA_ESTACAO_SQL}")
                res = cursor.fetchone()[0]
                return int(res or 0) + 1
        except: return 1

    def preencher_geografico(self, reg: Dict, ponto: Point) -> Dict:
        p_gdf = gpd.GeoDataFrame(index=[0], geometry=[ponto], crs=CRS_SIRGAS2000)
        p_gdf = p_gdf.drop(columns=['index_right'], errors='ignore')

        if self.gdf_mun is not None:
            res_mun = gpd.sjoin(p_gdf, self.gdf_mun, how='left', predicate='intersects')
            if not res_mun.empty:
                municipio_codigo = res_mun.at[0, 'dbo__Mun_2']
                if pd.isna(reg.get('MunicipioCodigo')):
                    reg['MunicipioCodigo'] = municipio_codigo
                # EstadoCodigo (código HIDRO da UF, não a sigla) é o prefixo do MunicipioCodigo:
                # MunicipioCodigo = EstadoCodigo * 1_000_000 + sequencial (ex.: 27001000 -> UF 27 = DF).
                if pd.isna(reg.get('EstadoCodigo')) and pd.notna(municipio_codigo):
                    reg['EstadoCodigo'] = int(municipio_codigo) // 1_000_000
            p_gdf = p_gdf.drop(columns=['index_right'], errors='ignore')

        if self.gdf_sub is not None:
            res_sub = gpd.sjoin(p_gdf, self.gdf_sub, how='left', predicate='intersects')
            if not res_sub.empty:
                reg['BaciaCodigo'] = res_sub.at[0, 'DNS_DNB_CD']
                reg['SubBaciaCodigo'] = res_sub.at[0, COLUNA_SUBBACIA_DNAEE]
        return reg

    def exportar_resultados(self, dados: List[Dict], caminho_saida: str) -> None:
        if not dados: return
        df_bruto = pd.DataFrame(dados)
        colunas_ordenadas = [c for c in COLUNAS_TEMPLATE_MDB if c in df_bruto.columns]
        colunas_extras = [c for c in df_bruto.columns if c not in COLUNAS_TEMPLATE_MDB and c != 'geometry']
        df_final = df_bruto[colunas_ordenadas + colunas_extras]

        if caminho_saida.endswith('.mdb'):
            shutil.copy(resource_path(TEMPLATE_MDB), caminho_saida)
            with pyodbc.connect(f'DRIVER={{{DRIVER_ACCESS}}};DBQ={caminho_saida};') as conn:
                cursor = conn.cursor()
                # O template.mdb real pode ter menos colunas do que COLUNAS_TEMPLATE_MDB
                # (ex.: 'Operando', 'Descricao' não existem na tabela atual) -- inserir só as
                # que realmente existem evita erro de "coluna não encontrada" no INSERT. Os
                # tipos reais (VARCHAR/DOUBLE/DATETIME) também variam campo a campo -- usados
                # em _valor_sql pra converter corretamente (ex.: Codigo é VARCHAR no template).
                info_colunas = list(cursor.columns(table=TABELA_NOVAS_MDB))
                colunas_reais = {c.column_name for c in info_colunas}
                tipos_colunas = {c.column_name: c.type_name for c in info_colunas}
                colunas_insercao = [c for c in COLUNAS_TEMPLATE_MDB if c in colunas_reais]
                cols_sql = ",".join([f"[{c}]" for c in colunas_insercao])
                placeholders = ",".join(["?" for _ in colunas_insercao])
                for _, row in df_final.iterrows():
                    vals = [_valor_sql(row.get(c), tipos_colunas.get(c)) for c in colunas_insercao]
                    cursor.execute(f"INSERT INTO {TABELA_NOVAS_MDB} ({cols_sql}) VALUES ({placeholders})", tuple(vals))
                conn.commit()
        else:
            df_final.to_excel(caminho_saida, index=False)

class ManagerPluviometrica(BaseManager):
    """Codificação Pluviométrica: Incremento unitário (+1)"""
    def processar(self, df_input: pd.DataFrame, progress_callback: Optional[Callable[[int], None]] = None,
                  should_continue: Optional[Callable[[], bool]] = None) -> List[Dict]:
        resultados = []
        total = len(df_input)
        if total == 0:
            return resultados

        with pyodbc.connect(self.sql_conn_str) as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT CAST(Codigo AS BIGINT) FROM {TABELA_ESTACAO_SQL} WHERE TipoEstacao = {TIPO_ESTACAO_PLUVIOMETRICA}")
            codigos_existentes = {int(r[0]) for r in cursor.fetchall() if r[0]}

            for i, (_, row) in enumerate(df_input.iterrows()):
                if should_continue is not None and not should_continue():
                    raise ProcessamentoCancelado()

                reg = row.to_dict()
                ponto = Point(reg['Longitude'], reg['Latitude'])
                codigo_base = self._gerar_codigo_pluvio(conn, reg['Latitude'], reg['Longitude'])

                # Incremento de 1 em 1 para Pluviométrica
                while codigo_base in codigos_existentes:
                    codigo_base += INCREMENTO_PLUVIO

                reg['Codigo'] = codigo_base
                codigos_existentes.add(codigo_base)
                reg['TipoEstacao'] = TIPO_ESTACAO_PLUVIOMETRICA
                reg['RegistroID'] = self.next_reg_id
                reg['MetodoGeracao'] = "Determinístico"
                self.next_reg_id += 1
                resultados.append(self.preencher_geografico(reg, ponto))

                if progress_callback is not None:
                    progress_callback(10 + int((i + 1) / total * 85))
        return resultados

    def _gerar_codigo_pluvio(self, conn, lat, lon) -> int:
        lv = abs(int(lat)) if lat < 0 else 80 + int(lat)
        prefixo = f"0{lv:02d}{abs(int(lon)):02d}"
        inf, sup = int(f"{prefixo}000"), int(f"{prefixo}999")
        cursor = conn.cursor()
        query = f"SELECT MAX(CAST(Codigo AS BIGINT)) FROM {TABELA_ESTACAO_SQL} WHERE CAST(Codigo AS BIGINT) BETWEEN ? AND ? AND TipoEstacao = ?"
        cursor.execute(query, inf, sup, TIPO_ESTACAO_PLUVIOMETRICA)
        res = cursor.fetchone()[0]
        seq = (int(str(res)[-3:]) + 1) if res else 1
        return int(f"{prefixo}{seq:03d}")

class ManagerFluviometrica(BaseManager):
    """
    Codificação Fluviométrica (NT 05/2024):
    - Incremento de 10 em 10.
    - Filtro temporal estrito (ativas após 2000).
    """
    def __init__(self):
        super().__init__()
        self.path_bho = resource_path(GPKG_BHO_DRENAGEM)

    def processar(self, df_input: pd.DataFrame, progress_callback: Optional[Callable[[int], None]] = None,
                  should_continue: Optional[Callable[[], bool]] = None) -> List[Dict]:
        if df_input.empty: return []

        try:
            gdf_bho = gpd.read_file(self.path_bho, layer=CAMADA_BHO_TRECHO).to_crs(CRS_POLICONICA)
        except Exception as e:
            raise Exception(f"Erro Base BHO6: {e}")

        gdf_p = gpd.GeoDataFrame(df_input, geometry=gpd.points_from_xy(df_input.Longitude, df_input.Latitude), crs=CRS_SIRGAS2000).to_crs(CRS_POLICONICA)
        gdf_p = gdf_p.drop(columns=['index_right'], errors='ignore')
        
        gdf_vinculado = gpd.sjoin_nearest(gdf_p, gdf_bho[['geometry', 'cotrecho', 'cocursodag', 'nudistbact']],
                                          max_distance=BUFFER_SNAPPING_METROS, how='left', distance_col="offset_m")
        gdf_vinculado = gdf_vinculado.to_crs(CRS_SIRGAS2000)

        resultados = []
        total = len(gdf_vinculado)
        with pyodbc.connect(self.sql_conn_str) as conn:
            gdf_vinculado = self._atribuir_prefixo_dnaee(gdf_vinculado)
            gdf_referencias = self._carregar_referencias_modernas(conn, gdf_bho)
            todos_codigos_banco = self._obter_todos_codigos_banco(conn)

            for i, (_, row) in enumerate(gdf_vinculado.iterrows()):
                if should_continue is not None and not should_continue():
                    raise ProcessamentoCancelado()

                rio_local = row['cocursodag']
                dist_foz = row['nudistbact']

                rio_codigo_alvo = None

                if pd.isna(rio_local):
                    ultimo_sub = self._buscar_max_subbacia_oficial(conn, row['PrefixoDNAEE'])
                    codigo_candidato = ultimo_sub + INCREMENTO_PADRAO_FALLBACK
                    metodo_geracao = "Fallback (sub-bacia)"
                else:
                    # ANA (1) e SGB como Operadora (82)
                    oficiais = gdf_referencias[
                        (gdf_referencias['ResponsavelCodigo'] == 1) |
                        (gdf_referencias['OperadoraCodigo'] == 82)
                    ]

                    rio_codigo_alvo, origem_riocodigo = self._determinar_riocodigo(oficiais, rio_local, dist_foz, row)

                    if rio_codigo_alvo is None:
                        codigo_candidato = self._buscar_max_subbacia_oficial(conn, row['PrefixoDNAEE']) + INCREMENTO_PADRAO_FALLBACK
                        metodo_geracao = "Fallback (sub-bacia, RioCodigo desconhecido)"
                    else:
                        # Agrupamento pelo RioCodigo oficial (o mesmo curso d'água nomeado),
                        # não pelo cocursodag do trecho BHO6 — a ordenação montante/jusante
                        # continua vindo do nudistbact (distância à foz na malha).
                        grupo_rio = oficiais[oficiais['RioCodigo'] == rio_codigo_alvo]
                        montante = grupo_rio[grupo_rio['nudistbact'] > dist_foz].sort_values('nudistbact', ascending=True).head(1)
                        jusante = grupo_rio[grupo_rio['nudistbact'] < dist_foz].sort_values('nudistbact', ascending=False).head(1)

                        sufixo = {'confirmado': "RioCodigo confirmado",
                                   'herdado': "RioCodigo herdado do vizinho",
                                   'ambiguo': "RioCodigo ambíguo"}[origem_riocodigo]

                        if not montante.empty and not jusante.empty:
                            # Interpolação arredondada para a dezena
                            meio = (int(montante.iloc[0]['Codigo']) + int(jusante.iloc[0]['Codigo'])) // 2
                            codigo_candidato = (meio // 10) * 10
                            metodo_geracao = f"Interpolado ({sufixo})"
                        elif not montante.empty:
                            codigo_candidato = int(montante.iloc[0]['Codigo']) + INCREMENTO_PADRAO_FALLBACK
                            metodo_geracao = f"Extrapolado (só montante, {sufixo})"
                        elif not jusante.empty:
                            codigo_candidato = int(jusante.iloc[0]['Codigo']) - INCREMENTO_PADRAO_FALLBACK
                            metodo_geracao = f"Extrapolado (só jusante, {sufixo})"
                        else:
                            codigo_candidato = self._buscar_max_subbacia_oficial(conn, row['PrefixoDNAEE']) + INCREMENTO_PADRAO_FALLBACK
                            metodo_geracao = "Fallback (sub-bacia, RioCodigo sem outras estações)"

                # Resolução de conflitos de 10 em 10 para Fluviométrica
                novo_cod = self._resolver_conflitos_flu(codigo_candidato, todos_codigos_banco)
                todos_codigos_banco.add(novo_cod)

                reg = row.to_dict()
                reg['Codigo'] = novo_cod
                reg['RioCodigo'] = rio_codigo_alvo
                reg['RegistroID'] = self.next_reg_id
                reg['TipoEstacao'] = TIPO_ESTACAO_FLUVIOMETRICA
                reg['Info Auxiliar'] = f"Rio: {rio_local} | RioCodigo: {rio_codigo_alvo} | Km: {dist_foz:.1f}"
                reg['MetodoGeracao'] = metodo_geracao

                self.next_reg_id += 1
                resultados.append(self.preencher_geografico(reg, row.geometry))

                if progress_callback is not None and total > 0:
                    progress_callback(10 + int((i + 1) / total * 85))

        return resultados

    def _resolver_conflitos_flu(self, codigo: int, existentes: Set[int]) -> int:
        while codigo in existentes:
            codigo += INCREMENTO_FLU
        return codigo

    def _carregar_referencias_modernas(self, conn, gdf_bho):
        cursor = conn.cursor()
        query = f"""
            SELECT Codigo, RioCodigo, Latitude, Longitude, ResponsavelCodigo, OperadoraCodigo
            FROM {TABELA_ESTACAO_SQL}
            WHERE TipoEstacao = {TIPO_ESTACAO_FLUVIOMETRICA}
            AND (PeriodoEscalaFim IS NULL OR PeriodoEscalaFim >= '2000-01-01')
        """
        cursor.execute(query)
        data = [{'Codigo': r[0], 'RioCodigo': r[1], 'Lat': r[2], 'Lon': r[3],
                 'ResponsavelCodigo': r[4], 'OperadoraCodigo': r[5]} for r in cursor.fetchall()]
        if not data: return gpd.GeoDataFrame()
        gdf_ex = gpd.GeoDataFrame(data, geometry=gpd.points_from_xy([d['Lon'] for d in data], [d['Lat'] for d in data]), crs=CRS_SIRGAS2000)
        gdf_vinc = gpd.sjoin_nearest(gdf_ex.to_crs(CRS_POLICONICA), gdf_bho[['geometry', 'cocursodag', 'nudistbact']], how='left')
        gdf_vinc = gdf_vinc.to_crs(CRS_SIRGAS2000)
        return self._atribuir_prefixo_dnaee(gdf_vinc)

    def _determinar_riocodigo(self, oficiais: gpd.GeoDataFrame, cocursodag_alvo, dist_foz: float, row):
        """
        Descobre a qual RioCodigo (agrupamento oficial do curso d'água, não o trecho geométrico
        moderno) a estação nova pertence, usando as estações de referência já codificadas.
        Retorna (rio_codigo, origem), com origem em 'confirmado' | 'herdado' | 'ambiguo' | None.
        """
        mesmo_trecho = oficiais[oficiais['cocursodag'] == cocursodag_alvo]
        if not mesmo_trecho.empty:
            valores = mesmo_trecho['RioCodigo'].dropna().unique()
            if len(valores) == 1:
                return valores[0], 'confirmado'
            if len(valores) > 1:
                mais_proximo = mesmo_trecho.loc[(mesmo_trecho['nudistbact'] - dist_foz).abs().idxmin()]
                return mais_proximo['RioCodigo'], 'ambiguo'

        candidatos_regiao = oficiais[oficiais['PrefixoDNAEE'] == row['PrefixoDNAEE']]
        if not candidatos_regiao.empty:
            distancias = candidatos_regiao.geometry.distance(row.geometry)
            mais_proximo = candidatos_regiao.loc[distancias.idxmin()]
            return mais_proximo['RioCodigo'], 'herdado'

        return None, None

    def _obter_todos_codigos_banco(self, conn) -> Set[int]:
        cursor = conn.cursor()
        cursor.execute(f"SELECT CAST(Codigo AS BIGINT) FROM {TABELA_ESTACAO_SQL} WHERE Codigo IS NOT NULL")
        return {int(r[0]) for r in cursor.fetchall()}

    def _atribuir_prefixo_dnaee(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        gdf = gdf.drop(columns=['index_right'], errors='ignore')
        if self.gdf_sub is None: return gdf
        res = gpd.sjoin(gdf, self.gdf_sub, how='left', predicate='intersects')
        gdf['PrefixoDNAEE'] = res[COLUNA_SUBBACIA_DNAEE].fillna('00').astype(str).str[:2].str.replace('.', '', regex=False)
        return gdf

    def _buscar_max_subbacia_oficial(self, conn, prefixo: str) -> int:
        inf, sup = int(f"{int(prefixo):02d}000000"), int(f"{int(prefixo):02d}999999")
        cursor = conn.cursor()
        query = f"""
            SELECT MAX(CAST(Codigo AS BIGINT)) FROM {TABELA_ESTACAO_SQL} 
            WHERE CAST(Codigo AS BIGINT) BETWEEN ? AND ? 
            AND (ResponsavelCodigo = 1 OR OperadoraCodigo = 82)
            AND (PeriodoEscalaFim IS NULL OR PeriodoEscalaFim >= '2000-01-01')
        """
        cursor.execute(query, inf, sup)
        res = cursor.fetchone()[0]
        return int(res) if res else int(f"{int(prefixo):02d}000000")