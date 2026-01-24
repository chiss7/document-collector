from typing import Dict, Any
import re
import asyncio
from transformers import pipeline

import html
import unicodedata
from typing import Optional

from app.services.ia_utils import IA_REGEX


class ClassifierService:
    """Provide two classification methods:
    - `transformers_zero_shot`: uses a HuggingFace zero-shot pipeline
    - `regex`: uses the existing IA_REGEX from `dspace_service`
    """

    _hf_pipeline = None

    @classmethod
    async def transformers_zero_shot(cls, text: str) -> Dict[str, Any]:
        """Run zero-shot classification in a thread to avoid blocking event loop.

        Returns dict with `labels` and `scores` (same shape as pipeline output).
        """
        def _init_and_run(t: str):
            # lazy init in thread
            if cls._hf_pipeline is None:
                cls._hf_pipeline = pipeline("zero-shot-classification", model="MoritzLaurer/ModernBERT-large-zeroshot-v2.0")
            # candidate labels used by downstream code (Spanish, descriptive)
            return cls._hf_pipeline(
                t,
                candidate_labels=[
                    "el artículo discute inteligencia artificial, machine learning, deep learning, redes neuronales, aprendizaje automático o algoritmos de IA",
                    "el artículo NO menciona IA ni ML; trata de blockchain, smart contracts, cadena de suministro u otros temas sin componentes de aprendizaje automático",
                ],
            )

        result = await asyncio.to_thread(_init_and_run, text)
        return result

    @staticmethod
    def normalize_abstract(text: str | None, max_chars: int = 1000, lower: bool = True) -> str:
        if not text:
            return ""
        s = html.unescape(text)
        # remove tags
        s = re.sub(r"<[^>]+>", " ", s)
        # remove urls
        s = re.sub(r"http\S+|www\.\S+", " ", s)
        # remove common citation patterns like [1], (2019)
        s = re.sub(r"\[\d+\]|\(\s*\d{4}\s*\)", " ", s)
        s = unicodedata.normalize("NFKC", s)
        s = re.sub(r"[\r\n\t]+", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        if lower:
            s = s.lower()
        if len(s) > max_chars:
            return s[:max_chars].rsplit(" ", 1)[0]
        return s

    @classmethod
    def _get_stopwords(cls, lang: str = "es") -> set:
        # Minimal stopword sets for Spanish and English. Extend if needed.
        es = {
            "de","la","que","el","en","y","a","los","se","del","las","por","un","para",
            "con","no","una","su","al","es","lo","como","más","pero","sus","le","ya","o",
            "fue","este","ha","sí","porque","esta","entre","cuando","muy","sin","sobre","también",
            "me","hasta","hay","donde","quien","desde","todo","nos","durante","todos","uno","les",
            "ni","contra","otros","ese","eso","ante","ellos","e"}
        en = {
            "the","be","to","of","and","a","in","that","have","i","it","for","not","on","with",
            "he","as","you","do","at","this","but","his","by","from","they","we","say","her",
            "she","or","an","will","my","one","all","would","there","their"
        }
        return es if lang.startswith("es") else en

    @classmethod
    async def clean_and_remove_stopwords(cls, text: str, lang: str = "es") -> str:
        """Lowercase, remove punctuation and stopwords. Returns cleaned string."""
        if not text:
            return ""
        s = text.lower()
        # remove punctuation (keep letters, numbers and whitespace)
        s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
        tokens = s.split()
        stops = cls._get_stopwords(lang)
        filtered = [t for t in tokens if t not in stops]
        return " ".join(filtered)

    @classmethod
    async def prepare_text_for_transformer(
        cls, title: str, subjects: str, abstract: str, max_abstract_chars: int = 1000
    ) -> str:
        # normalize abstract
        norm = cls.normalize_abstract(abstract, max_chars=max_abstract_chars, lower=True)
        # clean: lowercase, remove punctuation and stopwords
        clean = await cls.clean_and_remove_stopwords(norm, lang="es")
        # assemble final text (abstract cleaned only)
        parts = [f"Title: {title}", f"Subjects: {subjects}", f"Abstract: {clean}"]
        return "\n".join(p for p in parts if p)

    @staticmethod
    async def regex(text: str) -> Dict[str, Any]:
        """Classify using the IA_REGEX. Return label and a boolean/match score.

        Result format mirrors a simplified transformer output.
        """
        # simple synchronous regex check
        match = IA_REGEX.search(text or "")
        if match:
            return {"sequence": text, "labels": ["inteligencia artificial", "no relacionado con IA"], "scores": [0.99, 0.01]}
        else:
            return {"sequence": text, "labels": ["inteligencia artificial", "no relacionado con IA"], "scores": [0.01, 0.99]}