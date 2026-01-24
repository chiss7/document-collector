from sentence_transformers import SentenceTransformer, util
import torch

# Configuración
device = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f"Usando: {device}")

# Cargar modelo (primera vez ~2.3 GB descarga)
model = SentenceTransformer('BAAI/bge-m3', device=device)

# Descripción fija de "IA" (ajusta o expande según tus tesis)
ai_description = (
    "tesis o artículo académico sobre inteligencia artificial, "
    "machine learning, aprendizaje automático, deep learning, "
    "aprendizaje profundo, redes neuronales, redes convolucionales, "
    "visión por computadora, procesamiento de lenguaje natural, "
    "PLN, NLP, modelos generativos, transformers, LLM, "
    "TensorFlow, PyTorch, clasificación de imágenes o videos con IA"
)

# Codificar una sola vez la descripción de IA
ai_embedding = model.encode(ai_description, normalize_embeddings=True)

def clasificar_ia_bge(
    titulo: str,
    abstract: str,
    subjects: list[str],
    umbral: float = 0.58
) -> dict:
    """
    Devuelve similitud y decisión.
    """
    # Combinar texto del artículo
    texto_completo = f"{titulo} {abstract} {' '.join(subjects)}".strip()
    
    if not texto_completo:
        return {"similitud": 0.0, "es_ia": False, "texto": texto_completo}
    
    # Codificar
    texto_embedding = model.encode(texto_completo, normalize_embeddings=True)
    
    # Similitud coseno (valores entre -1 y 1, pero con normalize_embeddings suele ser 0–1)
    similitud = util.cos_sim(ai_embedding, texto_embedding).item()
    
    return {
        "similitud": round(similitud, 4),
        "es_ia": similitud >= umbral,
        "texto": texto_completo[:150] + "..."  # para log
    }


# Ejemplos de uso
casos = [
    {
        "titulo": "Desarrollo de una aplicación para detección de patrones en imágenes mediante aprendizaje profundo",
        "abstract": "En los últimos años las aplicaciones de Deep Learning se están volviendo importantes... Tensorflow y dataset Youtube8M",
        "subjects": ["DEEP LEARNING", "CLASIFICACIÓN DE IMÁGENES", "MACHINE LEARNING"]
    },
    {
        "titulo": "Propuesta de un modelo de cadena de suministro basado en tecnología Blockchain",
        "abstract": "presente estudio propone modelo cadena suministro con blockchain y contratos inteligentes...",
        "subjects": ["CONTRATOS INTELIGENTES", "CADENA DE SUMINISTRO", "TRAZABILIDAD"]
    },
]

for caso in casos:
    resultado = clasificar_ia_bge(
        caso["titulo"],
        caso["abstract"],
        caso["subjects"],
        umbral=0.58
    )
    print("\nResultado:")
    print(f"Similitud: {resultado['similitud']}")
    print(f"¿Es sobre IA? {resultado['es_ia']}")
    print(f"Texto (resumido): {resultado['texto']}")