from typing import Dict, Any
import re
import asyncio
import os

import html
import unicodedata
from typing import Optional

from app.services.ia_utils import IA_REGEX

# Determine whether to disable NLP heavy imports at runtime. This can be
# controlled by environment variables:
# - ENV=production  -> disables NLP
# - DISABLE_NLP=1/true/yes -> disables NLP
ENV = os.getenv("ENV", "").lower()
DISABLE_NLP = ENV == "production" or os.getenv("DISABLE_NLP", "").lower() in ("1", "true", "yes")

# Embeddings description used to represent the "IA" concept
_AI_DESCRIPTION = (
    "cualquier tesis, artículo o publicación que mencione, discuta, analice, aplique o haga referencia a "
    "inteligencia artificial, IA, artificial intelligence, AI, minería de datos, data mining, "
    "machine learning, aprendizaje automático, deep learning, "
    "aprendizaje profundo, redes neuronales, redes convolucionales, CNN, "
    "visión por computadora, computer vision, visión artificial, "
    "detección de objetos, detección de anomalías, reconocimiento de patrones en imágenes o videos, "
    "procesamiento de lenguaje natural, PLN, NLP, modelos generativos, transformers, LLM, ChatGPT, "
    "modelos predictivos, clasificación de imágenes o videos con IA, clasificación de sentimientos, modelos preentrenados, "
    "TensorFlow, PyTorch, Keras, OpenCV combinado con modelos de deep learning"
)


class ClassifierService:
    """Provide two classification methods:
    - `transformers_zero_shot`: uses a HuggingFace zero-shot pipeline
    - `regex`: uses the existing IA_REGEX from `dspace_service`
    """

    _hf_pipeline = None
    _emb_model = None
    _ai_embedding = None

    @classmethod
    async def transformers_zero_shot(cls, text: str) -> Dict[str, Any]:
        """Run zero-shot classification in a thread to avoid blocking event loop.

        Returns dict with `labels` and `scores` (same shape as pipeline output).
        """
        # If NLP is disabled in this environment, fall back to regex classifier
        if DISABLE_NLP:
            return await cls.regex(text)

        def _init_and_run(t: str):
            # lazy import to avoid heavy module load at startup
            try:
                from transformers import pipeline
            except Exception as e:
                # if import fails, fallback to regex
                return {
                    "sequence": t,
                    "labels": [
                        "el artículo discute inteligencia artificial, machine learning, deep learning, redes neuronales, aprendizaje automático o algoritmos de IA",
                        "el artículo NO menciona IA ni ML; trata de blockchain, smart contracts, cadena de suministro u otros temas sin componentes de aprendizaje automático",
                    ],
                    "scores": [0.01, 0.99],
                    "note": f"transformers import failed: {e}",
                }

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


    # BAAI/bge-m3, nomic-ai/nomic-embed-text-v1.5, 
    # BEST MODEL: intfloat/multilingual-e5-large with .83 threshold
    @classmethod
    async def embeddings(cls, title: str, abstract: str, subjects: list[str], threshold: float = 0.55) -> Dict[str, Any]:
        """Classify using sentence-transformers embeddings.

        Loads the model lazily in a background thread and returns a dict with
        `similitud` (float) and `es_ia` (bool).
        """
        # If NLP is disabled, return a safe default instead of loading models
        if DISABLE_NLP:
            return {"similitud": 0.0, "es_ia": False, "texto": "", "note": "nlp_disabled"}

        def _init_and_encode(titulo: str, abstract_text: str, subjects_list: list[str], thr: float):
            try:
                # lazy imports
                from sentence_transformers import SentenceTransformer, util
                import torch
            except Exception as e:
                return {"similitud": 0.0, "es_ia": False, "texto": "", "note": f"sentence_transformers import failed: {e}"}

            if cls._emb_model is None:
                device = 'cuda' if torch.cuda.is_available() else 'cpu'
                cls._emb_model = SentenceTransformer('intfloat/multilingual-e5-large', device=device)
                cls._ai_embedding = cls._emb_model.encode(_AI_DESCRIPTION, normalize_embeddings=True)

            texto = f"{titulo} {abstract_text} {' '.join(subjects_list)}".strip()
            if not texto:
                return {"similitud": 0.0, "es_ia": False, "texto": texto}

            texto_emb = cls._emb_model.encode(texto, normalize_embeddings=True)
            similitud = util.cos_sim(cls._ai_embedding, texto_emb).item()
            return {"similitud": round(similitud, 4), "es_ia": similitud >= thr, "texto": texto[:150] + "..."}

        result = await asyncio.to_thread(_init_and_encode, title, abstract or "", subjects or [], threshold)
        return result