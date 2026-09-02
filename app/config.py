from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    key: str
    subject: str
    title: str
    url: str
    article_ranges: tuple[str, ...] = ()
    full_document: bool = False


SOURCES = (
    Source("cp", "Direito Penal", "Código Penal", "https://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm", ("293-305", "307", "308", "311-A", "312-317", "319-333", "336-337", "339-347", "357", "359")),
    Source("cpp", "Direito Processual Penal", "Código de Processo Penal", "https://www.planalto.gov.br/ccivil_03/decreto-lei/del3689compilado.htm", ("251-258", "261-267", "274", "351-372", "394-497", "531-538", "541-548", "574-667")),
    Source("lei9099-processual-penal", "Direito Processual Penal", "Lei nº 9.099/1995", "https://www.planalto.gov.br/ccivil_03/leis/l9099.htm", ("60-83", "88-89")),
    Source("cpc", "Direito Processual Civil", "Código de Processo Civil", "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm", ("144-155", "188-275", "294-311", "318-538", "994-1026")),
    Source("lei9099-processual-civil", "Direito Processual Civil", "Lei nº 9.099/1995", "https://www.planalto.gov.br/ccivil_03/leis/l9099.htm", ("3-19",)),
    Source("lei12153", "Direito Processual Civil", "Lei nº 12.153/2009", "https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2009/lei/l12153.htm", (), True),
    Source("cf", "Direito Constitucional", "Constituição da República Federativa do Brasil", "https://www.planalto.gov.br/ccivil_03/constituicao/constituicaocompilado.htm", ("5-17", "37-41", "92")),
    Source("lei10261", "Direito Administrativo", "Lei nº 10.261/1968 — Estatuto dos Funcionários Públicos Civis do Estado de São Paulo", "https://www.al.sp.gov.br/repositorio/legislacao/lei/1968/compilacao-lei-10261-28.10.1968.html", ("1-86", "171-175", "239-323")),
    Source("lei8429", "Direito Administrativo", "Lei nº 8.429/1992 — Lei de Improbidade Administrativa", "https://www.planalto.gov.br/ccivil_03/leis/l8429.htm", (), True),
)
