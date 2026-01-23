from transformers import pipeline

classifier = pipeline("zero-shot-classification", model="MoritzLaurer/ModernBERT-large-zeroshot-v2.0")
result = classifier(
    "Propuesta de modelo de redes neuronales para predicción en educación",
    candidate_labels=["inteligencia artificial", "no relacionado con IA"]
)

print(result)