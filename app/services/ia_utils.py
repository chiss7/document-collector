import re

# Keywords para filtrar IA (case-insensitive, español/inglés).
# Use word boundaries for short tokens to avoid matching substrings (e.g. 'ia' inside other words).
IA_KEYWORDS = [
    r'\binteligencia artificial\b',
    r'\bartificial intelligence\b',
    r'\bmachine learning\b',
    r'\baprendizaje autom[aá]tico\b',
    r'\bdeep learning\b',
    r'\bred neuronal\b',
    r'\bAI\b',
    r'\bminer[ií]a de datos\b',
    r'\bprocesamiento de lenguaje natural\b',
    r'\bllm\b',
    r'\bmodelo estad[ií]stico\b',
    r'\bclasificaci[oó]n autom[aá]tica\b',
    r'\bbig data\b',
    r'\bregresi[oó]n log[ií]stica\b',
    r'\bmodelo de regresi[oó]n\b',
    r'\bmodelo de simulaci[oó]n\b',
]

IA_REGEX = re.compile('|'.join(IA_KEYWORDS), re.IGNORECASE)
