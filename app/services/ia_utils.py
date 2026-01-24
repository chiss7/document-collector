import re

# Keywords para filtrar IA (case-insensitive, español/inglés).
# Use word boundaries for short tokens to avoid matching substrings (e.g. 'ia' inside other words).
IA_KEYWORDS = [
    r'\binteligencia artificial\b',
    r'\bartificial intelligence\b',
    r'\bmachine learning\b',
    r'\baprendizaje autom[aá]tico\b',
    r'\bdeep learning\b',
    r'\baprendizaje profundo\b',
    r'\bred neuronal\b',
    r'\bredes neuronales\b',
    r'\bneural network\b',
    # match the abbreviations AI / IA as whole words only
    r'\bAI\b',
    r'\bIA\b',
    # Additional keywords (Spanish / English and accents handled)
    r'\bminer[ií]a de datos\b',
    r'\bnlp\b',
    r'\bdata mining\b',
    r'\bmodelos predictivos\b',
    r'\bprocesamiento de lenguaje natural\b',
    r'\bvisi[oó]n por computador\b',
    r'\bcomputer vision\b',
]

IA_REGEX = re.compile('|'.join(IA_KEYWORDS), re.IGNORECASE)
